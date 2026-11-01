import pytest


@pytest.mark.django_db
def test_create_expense_requires_auth():
    """Without a token, you shouldn't be able to add an expense — should get a 401."""
    from rest_framework.test import APIClient

    client = APIClient()
    response = client.post("/api/expenses/", {"amount": 100, "category": 1})
    assert response.status_code == 401


@pytest.mark.django_db
def test_create_expense_authenticated(api_client):
    """A logged-in user should be able to add an expense and get a 201 back."""
    from expenses.models import Category

    category = Category.objects.create(name="Food")
    response = api_client.post(
        "/api/expenses/", {"amount": 100, "category": category.id}
    )
    assert response.status_code == 201


@pytest.mark.django_db
def test_user_cannot_see_other_users_expenses():
    """Users should only see their own expenses, never someone else's."""
    from django.contrib.auth.models import User
    from rest_framework.authtoken.models import Token
    from rest_framework.test import APIClient
    from expenses.models import Category, Expense

    user_a = User.objects.create_user(username="user_a", password="pass123")
    user_b = User.objects.create_user(username="user_b", password="pass123")
    token_a = Token.objects.create(user=user_a)
    token_b = Token.objects.create(user=user_b)

    category = Category.objects.create(name="Food")
    Expense.objects.create(user=user_a, amount=100, category=category)

    client_b = APIClient()
    client_b.credentials(HTTP_AUTHORIZATION=f"Token {token_b.key}")
    response = client_b.get("/api/expenses/")

    assert response.status_code == 200
    assert len(response.data) == 0


@pytest.mark.django_db
def test_stats_daily_limit(api_client, user):
    from expenses.models import Category, Expense, UserProfile, Income
    import calendar
    from datetime import datetime
    from decimal import ROUND_FLOOR, Decimal

    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.currency = "PLN"
    profile.savings_goal = 1000
    profile.save()

    category = Category.objects.create(name="Food")
    Expense.objects.create(user=user, amount=2000, category=category, currency="PLN")
    Income.objects.create(user=user, amount=6000, currency="PLN")
    response = api_client.get("/api/stats/")
    now = datetime.now()
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    remaining_days = days_in_month - now.day + 1
    expected_limit = (Decimal(6000 - 1000 - 2000) / remaining_days).quantize(
        Decimal("0.01"), rounding=ROUND_FLOOR
    )

    assert response.data["daily_limit"] == expected_limit


@pytest.mark.django_db
def test_set_savings_goal(api_client, user):
    from expenses.models import UserProfile

    response = api_client.post("/api/set-savings-goal/", {"savings_goal": 1500})
    assert response.status_code == 200
    profile = UserProfile.objects.get(user=user)
    assert profile.savings_goal == 1500


@pytest.mark.django_db
def test_regular_payment_invalid_day(api_client):
    from expenses.models import Category

    category = Category.objects.create(name="Bills")
    response = api_client.post(
        "/api/regular-payments/",
        {
            "name": "Internet",
            "amount": 65,
            "payment_day": 45,
            "category": category.id,
        },
    )
    assert response.status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize("amount", [0, -100])
@pytest.mark.parametrize("url", ["/api/expenses/", "/api/income/"])
def test_non_positive_amount_is_rejected(api_client, url, amount):
    from expenses.models import Category

    category = Category.objects.create(name="Food")
    response = api_client.post(url, {"amount": amount, "category": category.id})
    assert response.status_code == 400


@pytest.mark.django_db
def test_regular_payment_non_positive_amount_is_rejected(api_client):
    from expenses.models import Category

    category = Category.objects.create(name="Bills")
    response = api_client.post(
        "/api/regular-payments/",
        {"name": "Internet", "amount": 0, "payment_day": 5, "category": category.id},
    )
    assert response.status_code == 400
