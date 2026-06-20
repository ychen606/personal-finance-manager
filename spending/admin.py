from django.contrib import admin

from .models import Spending


@admin.register(Spending)
class SpendingAdmin(admin.ModelAdmin):
    list_display = ['description', 'amount', 'currency', 'date', 'user']
    list_filter = ['currency', 'date']
    search_fields = ['description']
