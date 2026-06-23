from django.contrib import admin

from .models import Spending


@admin.register(Spending)
class SpendingAdmin(admin.ModelAdmin):
    list_display = ['description', 'amount', 'currency', 'tag', 'date', 'user']
    list_filter = ['currency', 'tag', 'date']
    search_fields = ['description']
