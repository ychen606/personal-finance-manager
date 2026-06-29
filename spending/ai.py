import calendar
import json
from collections import defaultdict
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from .models import Spending


class AIConfigurationError(Exception):
    pass


class AIRequestError(Exception):
    pass


def _month_spendings(user, year, month):
    return Spending.objects.filter(
        user=user,
        date__year=year,
        date__month=month,
    ).order_by('date', 'created_at')


def build_spending_context(user, year, month):
    spendings = list(_month_spendings(user, year, month))
    if not spendings:
        return ''

    currency_totals = defaultdict(Decimal)
    tag_totals = defaultdict(lambda: defaultdict(Decimal))

    for spending in spendings:
        currency_totals[spending.currency] += spending.amount
        tag = spending.tag.strip() or '(untagged)'
        tag_totals[tag][spending.currency] += spending.amount

    lines = [
        f'Month: {calendar.month_name[month]} {year}',
        '',
        'Totals by currency:',
    ]
    for currency in sorted(currency_totals):
        lines.append(f'  {currency} {currency_totals[currency]:.2f}')

    lines.extend(['', 'Totals by tag:'])
    for tag in sorted(tag_totals):
        parts = [
            f'{currency} {tag_totals[tag][currency]:.2f}'
            for currency in sorted(tag_totals[tag])
        ]
        lines.append(f'  {tag}: {", ".join(parts)}')

    lines.extend(['', 'Transactions:'])
    for spending in spendings:
        tag = spending.tag.strip() or '(untagged)'
        lines.append(
            f'  {spending.date.isoformat()} | {spending.description} | '
            f'{spending.currency} {spending.amount:.2f} | {tag}'
        )

    return '\n'.join(lines)


def generate_monthly_summary(user, year, month):
    if not settings.OPENAI_API_KEY:
        raise AIConfigurationError('OPENAI_API_KEY is not configured.')

    context = build_spending_context(user, year, month)
    if not context:
        raise ValueError('No spendings for this month.')

    month_name = calendar.month_name[month]
    payload = {
        'model': settings.OPENAI_MODEL,
        'messages': [
            {
                'role': 'system',
                'content': (
                    'You are a personal finance assistant. Analyze spending data '
                    'and provide a concise summary, key insights, and practical '
                    'suggestions to help the user manage their money better.'
                ),
            },
            {
                'role': 'user',
                'content': (
                    f'Here are my spendings for {month_name} {year}:\n\n'
                    f'{context}\n\n'
                    'Please provide a summary with analysis and suggestions.'
                ),
            },
        ],
    }

    url = f'{settings.OPENAI_API_URL}/chat/completions'
    data = json.dumps(payload).encode('utf-8')
    request = Request(
        url,
        data=data,
        headers={
            'Authorization': f'Bearer {settings.OPENAI_API_KEY}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )

    try:
        with urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        error_body = exc.read().decode('utf-8', errors='replace')
        raise AIRequestError(f'AI API returned HTTP {exc.code}: {error_body}') from exc
    except URLError as exc:
        raise AIRequestError(f'Could not reach AI API: {exc.reason}') from exc
    except json.JSONDecodeError as exc:
        raise AIRequestError('AI API returned invalid JSON.') from exc

    try:
        return body['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError) as exc:
        raise AIRequestError('AI API response had an unexpected format.') from exc
