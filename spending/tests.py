from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from spending.models import Spending


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
        self.assertRedirects(response, '/?year=2026&month=6')
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
