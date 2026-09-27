from rest_framework import serializers

from .models import (
    Category,
    Expense,
    Income,
    RegularPayments,
    TelegramUser,
    UserProfile,
)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        read_only_fields = ["user"]
        fields = ["user", "id", "name"]


class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        read_only_fields = ["user", "date", "currency"]
        fields = ["user", "date", "id", "amount", "category", "description", "currency"]


class IncomeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Income
        read_only_fields = ["user", "date", "currency"]
        fields = ["user", "date", "id", "amount", "description", "currency"]


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        read_only_fields = ["user"]
        fields = ["user", "currency", "savings_goal", "notification_status"]


class RegularPaymentsSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = RegularPayments
        read_only_fields = ["user"]
        fields = [
            "id",
            "amount",
            "name",
            "category",
            "payment_day",
            "user",
            "category_name",
        ]


class TelegramUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramUser
        read_only_fields = ["user"]
        fields = ["user", "telegram_id"]
