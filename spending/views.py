import calendar
import json
from collections import defaultdict
from datetime import date
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .ai import AIConfigurationError, AIRequestError, generate_monthly_summary
from .forms import SpendingForm
from .models import Spending


def _parse_year_month(request):
    today = timezone.localdate()
    try:
        year = int(request.GET.get('year', today.year))
        month = int(request.GET.get('month', today.month))
        if not (1 <= month <= 12):
            raise ValueError
        date(year, month, 1)
    except (TypeError, ValueError):
        year, month = today.year, today.month
    return year, month


def _month_bounds(year, month):
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _parse_iso_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _parse_date_range(request, year, month):
    default_start, default_end = _month_bounds(year, month)
    start = _parse_iso_date(request.GET.get('start_date'))
    end = _parse_iso_date(request.GET.get('end_date'))

    if start is None and end is None:
        return default_start, default_end

    if start is None:
        start = default_start
    if end is None:
        end = default_end
    if start > end:
        start, end = end, start

    return start, end


def _home_url(year, month, start_date, end_date, tags=None):
    url = (
        f'{reverse("home")}?year={year}&month={month}'
        f'&start_date={start_date.isoformat()}&end_date={end_date.isoformat()}'
    )
    for tag in tags or []:
        url += f'&tag={quote(tag)}'
    return url


def _user_tags(user):
    return (
        Spending.objects.filter(user=user)
        .exclude(tag='')
        .values_list('tag', flat=True)
        .distinct()
        .order_by('tag')
    )


def _parse_selected_tags(request):
    return [t.strip() for t in request.GET.getlist('tag') if t.strip()]


def _redirect_home(request, year, month):
    start_date, end_date = _parse_date_range(request, year, month)
    selected_tags = _parse_selected_tags(request)
    return redirect(_home_url(year, month, start_date, end_date, selected_tags))


def _redirect_home_after_post(request, year, month):
    filter_start = _parse_iso_date(request.POST.get('filter_start_date'))
    filter_end = _parse_iso_date(request.POST.get('filter_end_date'))
    filter_tags = [t.strip() for t in request.POST.getlist('filter_tag') if t.strip()]
    if filter_start and filter_end:
        if filter_start > filter_end:
            filter_start, filter_end = filter_end, filter_start
        return redirect(_home_url(year, month, filter_start, filter_end, filter_tags))
    return _redirect_home(request, year, month)


def _month_totals(user, year, month):
    totals = (
        Spending.objects.filter(user=user, date__year=year, date__month=month)
        .values('currency')
        .annotate(total=Sum('amount'))
        .order_by('currency')
    )
    return [
        {
            'currency': row['currency'],
            'total': row['total'],
            'formatted_total': f"{row['currency']} {row['total']:.2f}",
        }
        for row in totals
        if row['total'] and row['total'] > 0
    ]


def _build_calendar_weeks(year, month, spendings_by_day):
    cal = calendar.Calendar(firstweekday=6)
    weeks = []
    for week in cal.monthdatescalendar(year, month):
        weeks.append([
            {
                'date': day,
                'day': day.day,
                'in_month': day.month == month,
                'spendings': spendings_by_day.get(day.day, []) if day.month == month else [],
            }
            for day in week
        ])
    return weeks


@login_required
def home(request):
    year, month = _parse_year_month(request)
    start_date, end_date = _parse_date_range(request, year, month)
    selected_tags = _parse_selected_tags(request)
    user_tags = list(_user_tags(request.user))

    calendar_spendings = Spending.objects.filter(
        user=request.user,
        date__year=year,
        date__month=month,
    )
    spendings_by_day = defaultdict(list)
    for spending in calendar_spendings:
        spendings_by_day[spending.date.day].append(spending)

    list_spendings = Spending.objects.filter(
        user=request.user,
        date__range=[start_date, end_date],
    ).order_by('-date', '-created_at')
    if selected_tags:
        list_spendings = list_spendings.filter(tag__in=selected_tags)

    weeks = _build_calendar_weeks(year, month, dict(spendings_by_day))

    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    today = timezone.localdate()

    context = {
        'year': year,
        'month': month,
        'month_name': calendar.month_name[month],
        'weeks': weeks,
        'list_spendings': list_spendings,
        'start_date': start_date,
        'end_date': end_date,
        'selected_tags': selected_tags,
        'user_tags': user_tags,
        'month_totals': _month_totals(request.user, year, month),
        'prev_month_url': _home_url(prev_year, prev_month, start_date, end_date, selected_tags),
        'next_month_url': _home_url(next_year, next_month, start_date, end_date, selected_tags),
        'today_url': _home_url(today.year, today.month, start_date, end_date, selected_tags),
    }
    return render(request, 'home.html', context)


@login_required
@require_POST
def add_spending(request):
    form = SpendingForm(request.POST)
    if form.is_valid():
        spending = form.save(commit=False)
        spending.user = request.user
        spending.save()
        messages.success(request, 'Spending added.', extra_tags='auto-dismiss')
        return _redirect_home_after_post(request, spending.date.year, spending.date.month)

    messages.error(request, 'Could not add spending. Please check your input.')
    year, month = _parse_year_month(request)
    if form.data.get('date'):
        spending_date = _parse_iso_date(form.data['date'])
        if spending_date:
            year, month = spending_date.year, spending_date.month
    return _redirect_home_after_post(request, year, month)


def _get_user_spending(request, pk):
    return get_object_or_404(Spending, pk=pk, user=request.user)


@login_required
@require_POST
def edit_spending(request, pk):
    spending = _get_user_spending(request, pk)
    form = SpendingForm(request.POST, instance=spending)
    if form.is_valid():
        spending = form.save(commit=False)
        spending.user = request.user
        spending.save()
        messages.success(request, 'Spending updated.', extra_tags='auto-dismiss')
        return _redirect_home_after_post(request, spending.date.year, spending.date.month)

    messages.error(request, 'Could not update spending. Please check your input.')
    return _redirect_home_after_post(request, spending.date.year, spending.date.month)


@login_required
@require_POST
def delete_spending(request, pk):
    spending = _get_user_spending(request, pk)
    year, month = spending.date.year, spending.date.month
    spending.delete()
    messages.error(request, 'Spending deleted.', extra_tags='auto-dismiss')
    return _redirect_home_after_post(request, year, month)


def _parse_ai_summary_period(request):
    today = timezone.localdate()
    try:
        if request.content_type == 'application/json':
            body = json.loads(request.body.decode('utf-8') or '{}')
        else:
            body = {}
        year = int(body.get('year', today.year))
        month = int(body.get('month', today.month))
        if not (1 <= month <= 12):
            raise ValueError
        date(year, month, 1)
    except (TypeError, ValueError, json.JSONDecodeError):
        year, month = today.year, today.month
    return year, month


@login_required
@require_POST
def ai_summary(request):
    year, month = _parse_ai_summary_period(request)

    has_spendings = Spending.objects.filter(
        user=request.user,
        date__year=year,
        date__month=month,
    ).exists()
    if not has_spendings:
        return JsonResponse(
            {'error': 'No spendings for this month.'},
            status=400,
        )

    try:
        summary = generate_monthly_summary(request.user, year, month)
    except AIConfigurationError as exc:
        return JsonResponse({'error': str(exc)}, status=503)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except AIRequestError as exc:
        return JsonResponse({'error': str(exc)}, status=502)

    return JsonResponse({'summary': summary})
