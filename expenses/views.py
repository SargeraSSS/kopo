import calendar
from datetime import timedelta
from decimal import ROUND_FLOOR, Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
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


def month_range(day):
    last_day = calendar.monthrange(day.year, day.month)[1]
    return day.replace(day=1), day.replace(day=last_day)


class CategoryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = CategorySerializer

    def get_queryset(self):
        user = self.request.user
        if self.action == "retrieve":
            return Category.objects.filter(
                Q(user=user) | Q(user__isnull=True)
            ).annotate(
                expense_count=Count(
                    "expense", filter=Q(expense__user=user), distinct=True
                ),
                payment_count=Count(
                    "regularpayments",
                    filter=Q(regularpayments__user=user),
                    distinct=True,
                ),
            )
        if self.action == "list":
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
        serializer.save(
            user=self.request.user,
            currency=profile.currency,
            date=serializer.validated_data.get("date", profile.today()),
        )


class IncomeViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = IncomeSerializer

    def get_queryset(self):
        return Income.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        serializer.save(
            user=self.request.user, currency=profile.currency, date=profile.today()
        )


# User profile (currency, daily limit) - one per user
class UserProfileViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = UserProfileSerializer
    # profiles are created on registration, never through this endpoint
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        return UserProfile.objects.filter(user=self.request.user)


# Regular payments - each user manages their own
class RegularPaymentsViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = RegularPaymentsSerializer

    def get_queryset(self):
        return RegularPayments.objects.filter(user=self.request.user)

    # a day that has already passed counts as paid for the current month
    def perform_create(self, serializer):
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        today = profile.today()
        passed = serializer.validated_data["payment_day"] < today.day
        serializer.save(user=self.request.user, last_charged=today if passed else None)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def disable_notifications(request):
    telegram_id = request.data.get("telegram_id")
    if telegram_id is None:
        return Response({"error": "telegram_id is required"}, status=400)
    try:
        telegram_id = int(telegram_id)
    except (TypeError, ValueError):
        return Response({"error": "telegram_id given in a wrong form"}, status=400)
    tg_user = TelegramUser.objects.filter(telegram_id=telegram_id).first()
    if tg_user is not None:
        UserProfile.objects.filter(
            user__telegram_profile__telegram_id=telegram_id
        ).update(notification_status=False)
        return Response({"status": "Notifications disabled"}, status=200)
    return Response({"error": "Telegram user not found"}, status=404)


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
            UserProfile.objects.create(user=user)
            token, _ = Token.objects.get_or_create(user=user)
    except IntegrityError:
        # a parallel /start got there first - hand back the token it created
        tg_user = TelegramUser.objects.get(telegram_id=telegram_id)
        token, _ = Token.objects.get_or_create(user=tg_user.user)
        return Response({"token": token.key}, status=200)
    return Response({"token": token.key}, status=201)


@api_view(["POST"])
@permission_classes([IsAdminUser])
def process_regular_payments(request):
    """Charge due payments. Safe to repeat: the bot calls it every hour, because
    the local day starts at a different moment in every timezone."""
    description_length = Expense._meta.get_field("description").max_length
    # rows charged this month even in the zone furthest ahead need no look
    cutoff = (timezone.localdate() + timedelta(days=1)).replace(day=1)
    expenses = []
    charged = []
    with transaction.atomic():
        # "of" keeps the lock off the outer-joined profile, Postgres refuses that
        payments = (
            RegularPayments.objects.select_for_update(of=("self",))
            .select_related("user__userprofile")
            .filter(Q(last_charged__isnull=True) | Q(last_charged__lt=cutoff))
        )
        for payment in payments:
            profile = getattr(payment.user, "userprofile", None)
            today = profile.today() if profile else timezone.localdate()
            first_month_day, last_month_day = month_range(today)
            already_charged = (
                payment.last_charged is not None
                and payment.last_charged >= first_month_day
            )
            not_yet_due = payment.payment_day > today.day and today != last_month_day
            if already_charged or not_yet_due:
                continue
            expenses.append(
                Expense(
                    amount=payment.amount,
                    category_id=payment.category_id,
                    user=payment.user,
                    description=payment.name[:description_length],
                    currency=profile.currency if profile else "PLN",
                    date=min(
                        first_month_day + timedelta(days=payment.payment_day - 1),
                        last_month_day,
                    ),
                )
            )
            payment.last_charged = today
            charged.append(payment)
        Expense.objects.bulk_create(expenses)
        RegularPayments.objects.bulk_update(charged, ["last_charged"])
    return Response({"created": len(expenses)})


@api_view(["GET"])
@permission_classes([IsAdminUser])
def get_telegram_id(request):
    tg_user = TelegramUser.objects.all()
    ids = tg_user.values_list(
        "telegram_id",
        "user__userprofile__notification_status",
        "user__userprofile__timezone",
    )
    ids = [
        {"telegram_id": tid, "notification_status": status, "timezone": zone}
        for tid, status, zone in ids
    ]
    return Response(ids)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_monthly_stats(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    today = profile.today()
    month = month_range(today)
    expenses = (
        Expense.objects.filter(user=request.user, date__range=month)
        .values("category__name", "currency")
        .annotate(total=Sum("amount"))
    )
    income = (
        Income.objects.filter(user=request.user, date__range=month)
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

    remaining_days_in_month = month[1].day - today.day + 1
    income_total = total_with_income.get(profile.currency, 0)
    expenses_total = totals_by_currency.get(profile.currency, 0)
    savings_goal = profile.savings_goal or 0
    daily_limit = (
        Decimal(income_total - savings_goal - expenses_total) / remaining_days_in_month
    ).quantize(Decimal("0.01"), rounding=ROUND_FLOOR)
    currency_mismatch = any(
        currency != profile.currency for currency in total_with_income.keys()
    ) or any(currency != profile.currency for currency in totals_by_currency.keys())
    return Response(
        {
            "month": today.strftime("%B %Y"),
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
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    expenses = (
        Expense.objects.filter(
            user=request.user, date__range=month_range(profile.today())
        )
        .order_by("-date")
        .values("amount", "category__name", "date", "description", "currency")
    )
    return Response(list(expenses))


def update_profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    serializer = UserProfileSerializer(profile, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def notification_status(request):
    return update_profile(request)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def set_currency(request):
    return update_profile(request)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def set_timezone(request):
    return update_profile(request)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def set_savings_goal(request):
    return update_profile(request)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    return Response(UserProfileSerializer(profile).data)
