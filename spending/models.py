from django.conf import settings
from django.db import models


class Spending(models.Model):
    class Currency(models.TextChoices):
        USD = 'USD', 'USD'
        CAD = 'CAD', 'CAD'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='spendings',
    )
    date = models.DateField()
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        default=Currency.USD,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.description} — {self.formatted_amount}'

    @property
    def formatted_amount(self):
        return f'{self.currency} {self.amount:.2f}'
