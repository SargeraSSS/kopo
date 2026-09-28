from django.urls import path
from rest_framework import routers

from . import views
from .views import (
    CategoryViewSet,
    ExpenseViewSet,
    IncomeViewSet,
    RegularPaymentsViewSet,
    UserProfileViewSet,
)

router = routers.DefaultRouter()
router.register("expenses", ExpenseViewSet, basename="expense")
router.register("income", IncomeViewSet, basename="income")
router.register("categories", CategoryViewSet, basename="category")
router.register("user-profile", UserProfileViewSet, basename="user-profile")
router.register("regular-payments", RegularPaymentsViewSet, basename="regular-payments")

urlpatterns = router.urls + [
    path("register-telegram/", views.register_telegram_user),
    path("stats/", views.get_monthly_stats),
    path("history/", views.get_history),
    path("set-currency/", views.set_currency),
    path("set-savings-goal/", views.set_savings_goal),
    path("get-profile/", views.get_profile),
    path("all-telegram-ids/", views.get_telegram_id),
    path("process-regular-payments/", views.regular_payment_automization),
    path("notification-status/", views.notification_status),
]
