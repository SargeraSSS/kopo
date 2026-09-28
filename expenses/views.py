import calendar
from datetime import datetime

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from rest_framework import viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from .models import (
    Category,
    Expense,
    Income,
    RegularPayments,
    TelegramUser,
    UserProfile,
)
from .serializers import (
    CategorySerializer,
    ExpenseSerializer,
    IncomeSerializer,
    RegularPaymentsSerializer,
    UserProfileSerializer,
)


class CategoryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = CategorySerializer

    def get_queryset(self):
        user = self.request.user
        if self.action in ("list", "retrieve"):
            return Category.objects.filter(Q(user=user) | Q(user__isnull=True))
        return Category.objects.filter(user=user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_destroy(self, instance):
        if instance.user is None:
            raise PermissionDenied("Access denied")
        instance.delete()


# Expenses - each user sees only their own
class ExpenseViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ExpenseSerializer

    # returns only expenses belonging to the current user
    def get_queryset(self):
        return Expense.objects.filter(user=self.request.user)

    # automatically assigns the current user on creation
    def perform_create(self, serializer):
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        serializer.save(user=self.request.user, currency=profile.currency)


class IncomeViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = IncomeSerializer

    def get_queryset(self):
        return Income.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        serializer.save(user=self.request.user, currency=profile.currency)


# User profile (currency, daily limit) - one per user
class UserProfileViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = UserProfileSerializer

    def get_queryset(self):
        return UserProfile.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


# Regular payments - each user manages their own
class RegularPaymentsViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = RegularPaymentsSerializer

    def get_queryset(self):
        return RegularPayments.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def register_telegram_user(request):
    telegram_id = request.data.get("telegram_id")
    if telegram_id is None:
        return Response({"error": "telegram_id is required"}, status=400)
    try:
        telegram_id = int(telegram_id)
    except (TypeError, ValueError):
        return Response({"error": "telegram_id given in a wrong form"}, status=400)

    tg_user = TelegramUser.objects.filter(telegram_id=telegram_id).first()
    if tg_user is not None:
        token, _ = Token.objects.get_or_create(user=tg_user.user)
        return Response({"token": token.key}, status=200)
    try:
        with transaction.atomic():
            user = User.objects.create_user(username=f"tg_{telegram_id}")
            TelegramUser.objects.create(user=user, telegram_id=telegram_id)
            token, _ = Token.objects.get_or_create(user=user)
    except IntegrityError:
        # a parallel /start got there first - hand back the token it created
        tg_user = TelegramUser.objects.get(telegram_id=telegram_id)
        token, _ = Token.objects.get_or_create(user=tg_user.user)
        return Response({"token": token.key}, status=200)
    return Response({"token": token.key}, status=201)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def regular_payment_automization(request):
    payments = RegularPayments.objects.all()
    for payment in payments:
        Expense.objects.create(
            amount=payment.amount,
            category=payment.category,
            user=payment.user,
            description=payment.name,
        )
    return Response({"created": len(payments)})


@api_view(["GET"])
@permission_classes([IsAdminUser])
def get_telegram_id(request):
    tg_user = TelegramUser.objects.all()
    ids = tg_user.values_list("telegram_id", "user__userprofile__notification_status")
    ids = [{"telegram_id": tid, "notification_status": status} for tid, status in ids]
    return Response(ids)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_monthly_stats(request):
    now = datetime.now()
    expenses = (
        Expense.objects.filter(
            user=request.user, date__month=now.month, date__year=now.year
        )
        .values("category__name", "currency")
        .annotate(total=Sum("amount"))
    )
    income = (
        Income.objects.filter(
            user=request.user, date__month=now.month, date__year=now.year
        )
        .values("currency")
        .annotate(total=Sum("amount"))
    )
    totals_by_currency = {}
    for item in expenses:
        currency = item["currency"]
        totals_by_currency[currency] = (
            totals_by_currency.get(currency, 0) + item["total"]
        )
    total_with_income = {}
    for item in income:
        currency = item["currency"]
        total_with_income[currency] = total_with_income.get(currency, 0) + item["total"]

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    remaining_days_in_month = days_in_month - now.day + 1
    income_total = total_with_income.get(profile.currency, 0)
    expenses_total = totals_by_currency.get(profile.currency, 0)
    savings_goal = profile.savings_goal or 0
    daily_limit = (
        income_total - savings_goal - expenses_total
    ) // remaining_days_in_month
    currency_mismatch = any(
        currency != profile.currency for currency in total_with_income.keys()
    ) or any(currency != profile.currency for currency in totals_by_currency.keys())
    return Response(
        {
            "month": now.strftime("%B %Y"),
            "categories": list(expenses),
            "total": totals_by_currency,
            "income": total_with_income,
            "daily_limit": daily_limit,
            "currency": profile.currency,
            "currency_mismatch": currency_mismatch,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_history(request):
    now = datetime.now()
    expenses = (
        Expense.objects.filter(
            user=request.user, date__month=now.month, date__year=now.year
        )
        .order_by("-date")
        .values("amount", "category__name", "date", "description", "currency")
    )
    return Response(list(expenses))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def notification_status(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    serializer = UserProfileSerializer(profile, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def set_currency(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    serializer = UserProfileSerializer(profile, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def set_savings_goal(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    serializer = UserProfileSerializer(profile, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    return Response(
        {
            "currency": profile.currency,
            "savings_goal": profile.savings_goal,
            "notification_status": profile.notification_status,
        }
    )
