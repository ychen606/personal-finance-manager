from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from spending.ai import build_spending_context
from spending.models import Spending


def home_url(year, month, start, end, tags=None):
    url = (
        f'/?year={year}&month={month}'
        f'&start_date={start.isoformat()}&end_date={end.isoformat()}'
    )
    if tags:
        from urllib.parse import quote
        for tag in tags:
            url += f'&tag={quote(tag)}'
    return url


class CalendarSpendingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='alice', password='pass12345')
        self.other = User.objects.create_user(username='bob', password='pass12345')
        self.client = Client()

    def test_home_requires_login(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_home_shows_current_month(self):
        self.client.login(username='alice', password='pass12345')
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        today = date.today()
        self.assertContains(response, today.strftime('%B'))
        self.assertContains(response, str(today.year))

    def test_month_navigation(self):
        self.client.login(username='alice', password='pass12345')
        response = self.client.get(reverse('home'), {'year': 2026, 'month': 3})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'March')
        self.assertContains(response, '2026')

    def test_add_spending(self):
        self.client.login(username='alice', password='pass12345')
        response = self.client.post(reverse('add_spending'), {
            'date': '2026-06-15',
            'description': 'Groceries',
            'amount': '42.50',
            'currency': 'USD',
        })
        self.assertRedirects(
            response,
            home_url(2026, 6, date(2026, 6, 1), date(2026, 6, 30)),
        )
        spending = Spending.objects.get(user=self.user)
        self.assertEqual(spending.description, 'Groceries')
        self.assertEqual(spending.amount, Decimal('42.50'))
        self.assertEqual(spending.currency, 'USD')
        self.assertEqual(spending.formatted_amount, 'USD 42.50')

    def test_spending_display_on_calendar(self):
        Spending.objects.create(
            user=self.user,
            date=date(2026, 6, 15),
            description='Coffee',
            amount=Decimal('5.00'),
            currency='CAD',
        )
        self.client.login(username='alice', password='pass12345')
        response = self.client.get(reverse('home'), {'year': 2026, 'month': 6})
        self.assertContains(response, 'Coffee')
        self.assertContains(response, 'CAD 5.00')

    def test_user_scoping(self):
        Spending.objects.create(
            user=self.other,
            date=date(2026, 6, 15),
            description='Secret purchase',
            amount=Decimal('100.00'),
            currency='USD',
        )
        self.client.login(username='alice', password='pass12345')
        response = self.client.get(reverse('home'), {'year': 2026, 'month': 6})
        self.assertNotContains(response, 'Secret purchase')

    def test_edit_spending(self):
        spending = Spending.objects.create(
            user=self.user,
            date=date(2026, 6, 15),
            description='Coffee',
            amount=Decimal('5.00'),
            currency='CAD',
        )
        self.client.login(username='alice', password='pass12345')
        response = self.client.post(reverse('edit_spending', args=[spending.pk]), {
            'date': '2026-06-16',
            'description': 'Lunch',
            'amount': '12.00',
            'currency': 'USD',
        })
        self.assertRedirects(
            response,
            home_url(2026, 6, date(2026, 6, 1), date(2026, 6, 30)),
        )
        spending.refresh_from_db()
        self.assertEqual(spending.description, 'Lunch')
        self.assertEqual(spending.amount, Decimal('12.00'))
        self.assertEqual(spending.currency, 'USD')
        self.assertEqual(spending.date, date(2026, 6, 16))

    def test_delete_spending(self):
        spending = Spending.objects.create(
            user=self.user,
            date=date(2026, 6, 15),
            description='Coffee',
            amount=Decimal('5.00'),
            currency='CAD',
        )
        self.client.login(username='alice', password='pass12345')
        response = self.client.post(reverse('delete_spending', args=[spending.pk]))
        self.assertRedirects(
            response,
            home_url(2026, 6, date(2026, 6, 1), date(2026, 6, 30)),
        )
        self.assertFalse(Spending.objects.filter(pk=spending.pk).exists())

    def test_cannot_edit_other_users_spending(self):
        spending = Spending.objects.create(
            user=self.other,
            date=date(2026, 6, 15),
            description='Secret',
            amount=Decimal('5.00'),
            currency='USD',
        )
        self.client.login(username='alice', password='pass12345')
        response = self.client.post(reverse('edit_spending', args=[spending.pk]), {
            'date': '2026-06-15',
            'description': 'Hacked',
            'amount': '1.00',
            'currency': 'USD',
        })
        self.assertEqual(response.status_code, 404)
        spending.refresh_from_db()
        self.assertEqual(spending.description, 'Secret')

    def test_cannot_delete_other_users_spending(self):
        spending = Spending.objects.create(
            user=self.other,
            date=date(2026, 6, 15),
            description='Secret',
            amount=Decimal('5.00'),
            currency='USD',
        )
        self.client.login(username='alice', password='pass12345')
        response = self.client.post(reverse('delete_spending', args=[spending.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Spending.objects.filter(pk=spending.pk).exists())

    def test_list_defaults_to_calendar_month(self):
        Spending.objects.create(
            user=self.user,
            date=date(2026, 6, 10),
            description='In range',
            amount=Decimal('10.00'),
            currency='USD',
        )
        Spending.objects.create(
            user=self.user,
            date=date(2026, 7, 5),
            description='Out of range',
            amount=Decimal('20.00'),
            currency='USD',
        )
        self.client.login(username='alice', password='pass12345')
        response = self.client.get(reverse('home'), {'year': 2026, 'month': 6})
        self.assertContains(response, 'In range')
        self.assertNotContains(response, 'Out of range')

    def test_list_custom_date_range(self):
        Spending.objects.create(
            user=self.user,
            date=date(2026, 6, 10),
            description='June item',
            amount=Decimal('10.00'),
            currency='USD',
        )
        Spending.objects.create(
            user=self.user,
            date=date(2026, 7, 5),
            description='July item',
            amount=Decimal('20.00'),
            currency='USD',
        )
        self.client.login(username='alice', password='pass12345')
        response = self.client.get(reverse('home'), {
            'year': 2026,
            'month': 6,
            'start_date': '2026-06-01',
            'end_date': '2026-07-31',
        })
        self.assertContains(response, 'June item')
        self.assertContains(response, 'July item')

    def test_list_newest_first(self):
        Spending.objects.create(
            user=self.user,
            date=date(2026, 6, 10),
            description='Older',
            amount=Decimal('10.00'),
            currency='USD',
        )
        Spending.objects.create(
            user=self.user,
            date=date(2026, 6, 20),
            description='Newer',
            amount=Decimal('20.00'),
            currency='USD',
        )
        self.client.login(username='alice', password='pass12345')
        response = self.client.get(reverse('home'), {'year': 2026, 'month': 6})
        self.assertLess(response.content.index(b'Newer'), response.content.index(b'Older'))

    def test_calendar_nav_preserves_date_filter(self):
        self.client.login(username='alice', password='pass12345')
        response = self.client.get(reverse('home'), {
            'year': 2026,
            'month': 6,
            'start_date': '2026-05-01',
            'end_date': '2026-07-31',
        })
        self.assertContains(response, 'start_date=2026-05-01')
        self.assertContains(response, 'end_date=2026-07-31')
        self.assertContains(response, 'year=2026&amp;month=5')
        self.assertContains(response, 'year=2026&amp;month=7')

    def test_month_totals_by_currency(self):
        Spending.objects.create(
            user=self.user,
            date=date(2026, 6, 10),
            description='USD one',
            amount=Decimal('10.00'),
            currency='USD',
        )
        Spending.objects.create(
            user=self.user,
            date=date(2026, 6, 15),
            description='USD two',
            amount=Decimal('5.50'),
            currency='USD',
        )
        Spending.objects.create(
            user=self.user,
            date=date(2026, 6, 20),
            description='CAD one',
            amount=Decimal('8.00'),
            currency='CAD',
        )
        self.client.login(username='alice', password='pass12345')
        response = self.client.get(reverse('home'), {'year': 2026, 'month': 6})
        self.assertContains(response, 'USD 15.50')
        self.assertContains(response, 'CAD 8.00')

    def test_month_totals_omit_zero_currencies(self):
        Spending.objects.create(
            user=self.user,
            date=date(2026, 6, 10),
            description='USD only',
            amount=Decimal('10.00'),
            currency='USD',
        )
        self.client.login(username='alice', password='pass12345')
        response = self.client.get(reverse('home'), {'year': 2026, 'month': 6})
        self.assertContains(response, 'USD 10.00')
        self.assertNotContains(response, 'CAD 0.00')

    def test_list_and_totals_user_scoped(self):
        Spending.objects.create(
            user=self.other,
            date=date(2026, 6, 10),
            description='Other user item',
            amount=Decimal('99.00'),
            currency='USD',
        )
        self.client.login(username='alice', password='pass12345')
        response = self.client.get(reverse('home'), {'year': 2026, 'month': 6})
        self.assertNotContains(response, 'Other user item')
        self.assertContains(response, 'No spendings this month.')

    def test_list_filter_by_single_tag(self):
        Spending.objects.create(
            user=self.user,
            date=date(2026, 6, 10),
            description='Lunch',
            amount=Decimal('10.00'),
            currency='USD',
            tag='food',
        )
        Spending.objects.create(
            user=self.user,
            date=date(2026, 6, 11),
            description='Bus',
            amount=Decimal('5.00'),
            currency='USD',
            tag='transport',
        )
        Spending.objects.create(
            user=self.user,
            date=date(2026, 6, 12),
            description='Dinner',
            amount=Decimal('15.00'),
            currency='USD',
            tag='food',
        )
        self.client.login(username='alice', password='pass12345')
        response = self.client.get(reverse('home'), {
            'year': 2026,
            'month': 6,
            'tag': 'food',
        })
        descriptions = list(
            response.context['list_spendings'].values_list('description', flat=True)
        )
        self.assertEqual(descriptions, ['Dinner', 'Lunch'])

    def test_list_filter_by_multiple_tags(self):
        Spending.objects.create(
            user=self.user,
            date=date(2026, 6, 10),
            description='Lunch',
            amount=Decimal('10.00'),
            currency='USD',
            tag='food',
        )
        Spending.objects.create(
            user=self.user,
            date=date(2026, 6, 11),
            description='Bus',
            amount=Decimal('5.00'),
            currency='USD',
            tag='transport',
        )
        Spending.objects.create(
            user=self.user,
            date=date(2026, 6, 12),
            description='Movie',
            amount=Decimal('15.00'),
            currency='USD',
            tag='entertainment',
        )
        self.client.login(username='alice', password='pass12345')
        response = self.client.get(reverse('home'), [
            ('year', 2026),
            ('month', 6),
            ('tag', 'food'),
            ('tag', 'transport'),
        ])
        descriptions = set(
            response.context['list_spendings'].values_list('description', flat=True)
        )
        self.assertEqual(descriptions, {'Lunch', 'Bus'})

    def test_list_filter_no_tags_selected(self):
        Spending.objects.create(
            user=self.user,
            date=date(2026, 6, 10),
            description='Lunch',
            amount=Decimal('10.00'),
            currency='USD',
            tag='food',
        )
        Spending.objects.create(
            user=self.user,
            date=date(2026, 6, 11),
            description='Bus',
            amount=Decimal('5.00'),
            currency='USD',
            tag='transport',
        )
        self.client.login(username='alice', password='pass12345')
        response = self.client.get(reverse('home'), {'year': 2026, 'month': 6})
        self.assertContains(response, 'Lunch')
        self.assertContains(response, 'Bus')

    def test_tag_filter_preserves_date_range(self):
        Spending.objects.create(
            user=self.user,
            date=date(2026, 6, 10),
            description='June food',
            amount=Decimal('10.00'),
            currency='USD',
            tag='food',
        )
        Spending.objects.create(
            user=self.user,
            date=date(2026, 7, 5),
            description='July food',
            amount=Decimal('20.00'),
            currency='USD',
            tag='food',
        )
        self.client.login(username='alice', password='pass12345')
        response = self.client.get(reverse('home'), {
            'year': 2026,
            'month': 6,
            'start_date': '2026-06-01',
            'end_date': '2026-06-30',
            'tag': 'food',
        })
        self.assertContains(response, 'June food')
        self.assertNotContains(response, 'July food')

    def test_calendar_nav_preserves_tag_filter(self):
        self.client.login(username='alice', password='pass12345')
        response = self.client.get(reverse('home'), [
            ('year', 2026),
            ('month', 6),
            ('start_date', '2026-05-01'),
            ('end_date', '2026-07-31'),
            ('tag', 'food'),
            ('tag', 'transport'),
        ])
        self.assertContains(response, 'tag=food')
        self.assertContains(response, 'tag=transport')
        self.assertContains(response, 'start_date=2026-05-01')
        self.assertContains(response, 'end_date=2026-07-31')

    def test_add_spending_with_tag(self):
        self.client.login(username='alice', password='pass12345')
        response = self.client.post(reverse('add_spending'), {
            'date': '2026-06-15',
            'description': 'Groceries',
            'amount': '42.50',
            'currency': 'USD',
            'tag': 'food',
        })
        self.assertRedirects(
            response,
            home_url(2026, 6, date(2026, 6, 1), date(2026, 6, 30)),
        )
        spending = Spending.objects.get(user=self.user)
        self.assertEqual(spending.tag, 'food')

    def test_edit_spending_tag(self):
        spending = Spending.objects.create(
            user=self.user,
            date=date(2026, 6, 15),
            description='Coffee',
            amount=Decimal('5.00'),
            currency='CAD',
            tag='food',
        )
        self.client.login(username='alice', password='pass12345')
        response = self.client.post(reverse('edit_spending', args=[spending.pk]), {
            'date': '2026-06-16',
            'description': 'Lunch',
            'amount': '12.00',
            'currency': 'USD',
            'tag': 'transport',
        })
        self.assertRedirects(
            response,
            home_url(2026, 6, date(2026, 6, 1), date(2026, 6, 30)),
        )
        spending.refresh_from_db()
        self.assertEqual(spending.tag, 'transport')

    def test_filter_preserved_after_add(self):
        self.client.login(username='alice', password='pass12345')
        response = self.client.post(reverse('add_spending'), {
            'date': '2026-06-15',
            'description': 'Groceries',
            'amount': '42.50',
            'currency': 'USD',
            'tag': 'food',
            'filter_start_date': '2026-05-01',
            'filter_end_date': '2026-07-31',
            'filter_tag': ['food', 'transport'],
        })
        self.assertRedirects(
            response,
            home_url(
                2026, 6,
                date(2026, 5, 1),
                date(2026, 7, 31),
                tags=['food', 'transport'],
            ),
        )


class AISummaryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='alice', password='pass12345')
        self.other = User.objects.create_user(username='bob', password='pass12345')
        self.client = Client()

    def test_ai_summary_requires_login(self):
        response = self.client.post(
            reverse('ai_summary'),
            data='{"year": 2026, "month": 6}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_ai_summary_requires_post(self):
        self.client.login(username='alice', password='pass12345')
        response = self.client.get(reverse('ai_summary'))
        self.assertEqual(response.status_code, 405)

    def test_ai_summary_no_spendings(self):
        self.client.login(username='alice', password='pass12345')
        response = self.client.post(
            reverse('ai_summary'),
            data='{"year": 2026, "month": 6}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()['error'],
            'No spendings for this month.',
        )

    @override_settings(OPENAI_API_KEY='test-key')
    @patch('spending.views.generate_monthly_summary')
    def test_ai_summary_success(self, mock_generate):
        mock_generate.return_value = 'You spent mostly on food this month.'
        Spending.objects.create(
            user=self.user,
            date=date(2026, 6, 15),
            description='Groceries',
            amount=Decimal('42.50'),
            currency='USD',
            tag='food',
        )
        Spending.objects.create(
            user=self.other,
            date=date(2026, 6, 16),
            description='Secret',
            amount=Decimal('99.00'),
            currency='USD',
        )
        self.client.login(username='alice', password='pass12345')
        response = self.client.post(
            reverse('ai_summary'),
            data='{"year": 2026, "month": 6}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['summary'],
            'You spent mostly on food this month.',
        )
        mock_generate.assert_called_once_with(self.user, 2026, 6)

        context = build_spending_context(self.user, 2026, 6)
        self.assertIn('Groceries', context)
        self.assertNotIn('Secret', context)
