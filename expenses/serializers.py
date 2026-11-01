from rest_framework import serializers

from .models import (
    TIME_ZONE_CHOICES,
    Category,
    Expense,
    Income,
    RegularPayments,
    UserProfile,
)


class CategorySerializer(serializers.ModelSerializer):
    # filled only on retrieve, see CategoryViewSet.get_queryset
    expense_count = serializers.IntegerField(read_only=True)
    payment_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        read_only_fields = ["user"]
        fields = ["user", "id", "name", "expense_count", "payment_count"]


class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        read_only_fields = ["user", "currency"]
        fields = ["user", "date", "id", "amount", "category", "description", "currency"]

    def validate_category(self, value):
        if value.user is None:
            return value

        request = self.context.get("request")
        if request and value.user != request.user:
            raise serializers.ValidationError("Invalid category.")

        return value

    def validate_date(self, value):
        profile, _ = UserProfile.objects.get_or_create(user=self.context["request"].user)
        if value > profile.today():
            raise serializers.ValidationError("Date cannot be in the future.")
        return value


class IncomeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Income
        read_only_fields = ["user", "date", "currency"]
        fields = ["user", "date", "id", "amount", "description", "currency"]


class UserProfileSerializer(serializers.ModelSerializer):
    timezone = serializers.ChoiceField(choices=TIME_ZONE_CHOICES, required=False)

    class Meta:
        model = UserProfile
        read_only_fields = ["user"]
        fields = [
            "user",
            "currency",
            "savings_goal",
            "notification_status",
            "timezone",
        ]


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

    def validate_category(self, value):
        if value.user is None:
            return value
        request = self.context.get("request")
        if request and value.user != request.user:
            raise serializers.ValidationError("Invalid category")

        return value
