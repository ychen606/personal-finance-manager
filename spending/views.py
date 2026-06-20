import calendar
from collections import defaultdict
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

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


def _month_url(year, month):
    return f'{reverse("home")}?year={year}&month={month}'


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
    spendings = Spending.objects.filter(
        user=request.user,
        date__year=year,
        date__month=month,
    )
    spendings_by_day = defaultdict(list)
    for spending in spendings:
        spendings_by_day[spending.date.day].append(spending)

    weeks = _build_calendar_weeks(year, month, dict(spendings_by_day))

    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    context = {
        'year': year,
        'month': month,
        'month_name': calendar.month_name[month],
        'weeks': weeks,
        'prev_month_url': _month_url(prev_year, prev_month),
        'next_month_url': _month_url(next_year, next_month),
        'today_url': reverse('home'),
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
        return redirect(_month_url(spending.date.year, spending.date.month))

    messages.error(request, 'Could not add spending. Please check your input.')
    year, month = _parse_year_month(request)
    if form.data.get('date'):
        try:
            spending_date = date.fromisoformat(form.data['date'])
            year, month = spending_date.year, spending_date.month
        except ValueError:
            pass
    return redirect(_month_url(year, month))


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
        return redirect(_month_url(spending.date.year, spending.date.month))

    messages.error(request, 'Could not update spending. Please check your input.')
    return redirect(_month_url(spending.date.year, spending.date.month))


@login_required
@require_POST
def delete_spending(request, pk):
    spending = _get_user_spending(request, pk)
    year, month = spending.date.year, spending.date.month
    spending.delete()
    messages.error(request, 'Spending deleted.', extra_tags='auto-dismiss')
    return redirect(_month_url(year, month))
