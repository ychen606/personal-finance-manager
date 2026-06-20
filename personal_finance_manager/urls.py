"""
URL configuration for personal_finance_manager project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path

from spending import views as spending_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('spending/add/', spending_views.add_spending, name='add_spending'),
    path('spending/<int:pk>/edit/', spending_views.edit_spending, name='edit_spending'),
    path('spending/<int:pk>/delete/', spending_views.delete_spending, name='delete_spending'),
    path('', spending_views.home, name='home'),
]
