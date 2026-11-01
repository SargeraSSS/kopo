"""Dates follow the user's timezone, not the server's (UTC).

The freezing moments sit near midnight UTC on purpose: there the two
disagree about which day, and even which month, it is.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from expenses.models import Category, Expense, Income, RegularPayments, UserProfile


def at(*moment):
    frozen = datetime(*moment, tzinfo=timezone.utc)
    return mock.patch("django.utils.timezone.now", return_value=frozen)


@pytest.fixture
def category(db):
    return Category.objects.create(name="Food")


@pytest.fixture
def kyiv_user(user):
    UserProfile.objects.create(user=user, timezone="Europe/Kyiv")
    return user


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_user(username="bot_admin", is_staff=True)
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=admin).key}"
    )
    return client


def make_payment(user, category, payment_day, **fields):
    return RegularPayments.objects.create(
        amount=100,
        name="Flat",
        category=category,
        payment_day=payment_day,
        user=user,
        **fields,
    )


@pytest.mark.django_db
def test_expense_is_dated_by_the_users_day(api_client, kyiv_user, category):
    # 22:30 UTC on the 10th is already 00:30 on the 11th in Kyiv
    with at(2026, 3, 10, 22, 30):
        response = api_client.post(
            "/api/expenses/", {"amount": 10, "category": category.id}
        )

    assert response.data["date"] == "2026-03-11"


@pytest.mark.django_db
def test_income_is_dated_by_the_users_day(api_client, kyiv_user):
    with at(2026, 3, 10, 22, 30):
        response = api_client.post("/api/income/", {"amount": 10})

    assert response.data["date"] == "2026-03-11"


@pytest.mark.django_db
def test_expense_date_can_be_set_to_the_past(api_client, kyiv_user, category):
    with at(2026, 3, 10, 12, 0):
        response = api_client.post(
            "/api/expenses/",
            {"amount": 10, "category": category.id, "date": "2026-03-01"},
        )

    assert response.status_code == 201
    assert response.data["date"] == "2026-03-01"


@pytest.mark.django_db
def test_expense_date_cannot_be_in_the_users_future(api_client, kyiv_user, category):
    with at(2026, 3, 10, 12, 0):
        rejected = api_client.post(
            "/api/expenses/",
            {"amount": 10, "category": category.id, "date": "2026-03-11"},
        )
    with at(2026, 3, 10, 22, 30):
        accepted = api_client.post(
            "/api/expenses/",
            {"amount": 10, "category": category.id, "date": "2026-03-11"},
        )

    assert rejected.status_code == 400
    assert accepted.status_code == 201


@pytest.mark.django_db
def test_stats_and_history_use_the_users_month(api_client, kyiv_user, category):
    Expense.objects.create(
        user=kyiv_user, amount=10, category=category, date=date(2026, 3, 31)
    )
    Expense.objects.create(
        user=kyiv_user, amount=20, category=category, date=date(2026, 4, 1)
    )

    # 22:30 UTC on 31 March is already April in Kyiv
    with at(2026, 3, 31, 22, 30):
        stats = api_client.get("/api/stats/")
        history = api_client.get("/api/history/")

    assert stats.data["month"] == "April 2026"
    assert stats.data["total"] == {"PLN": Decimal("20.00")}
    assert [item["amount"] for item in history.data] == [Decimal("20.00")]


@pytest.mark.django_db
def test_daily_limit_keeps_cents_and_rounds_down(api_client, user):
    UserProfile.objects.create(user=user)
    Income.objects.create(user=user, amount=100, date=date(2026, 3, 1))

    # 29, 30 and 31 March remain
    with at(2026, 3, 29, 12, 0):
        response = api_client.get("/api/stats/")

    assert response.data["daily_limit"] == Decimal("33.33")


@pytest.mark.django_db
def test_daily_limit_is_negative_when_overspent(api_client, user, category):
    UserProfile.objects.create(user=user)
    Expense.objects.create(
        user=user, amount=10, category=category, date=date(2026, 3, 1)
    )

    with at(2026, 3, 29, 12, 0):
        response = api_client.get("/api/stats/")

    assert response.data["daily_limit"] == Decimal("-3.34")


@pytest.mark.django_db
def test_payment_is_charged_on_the_users_day(admin_client, kyiv_user, category):
    make_payment(kyiv_user, category, payment_day=11)

    with at(2026, 3, 10, 21, 30):  # 23:30 in Kyiv
        admin_client.post("/api/process-regular-payments/")
    assert Expense.objects.count() == 0

    with at(2026, 3, 10, 22, 30):  # 00:30 on the 11th in Kyiv
        admin_client.post("/api/process-regular-payments/")
    assert Expense.objects.get().date == date(2026, 3, 11)


@pytest.mark.django_db
def test_caught_up_payment_is_dated_by_its_payment_day(admin_client, user, category):
    make_payment(user, category, payment_day=5)

    with at(2026, 3, 20, 12, 0):
        admin_client.post("/api/process-regular-payments/")

    assert Expense.objects.get().date == date(2026, 3, 5)


@pytest.mark.django_db
def test_day_31_in_a_short_month_is_dated_by_its_last_day(admin_client, user, category):
    make_payment(user, category, payment_day=31)

    with at(2026, 2, 28, 12, 0):
        admin_client.post("/api/process-regular-payments/")

    assert Expense.objects.get().date == date(2026, 2, 28)


@pytest.mark.django_db
def test_user_without_a_profile_counts_as_utc(admin_client, user, category):
    make_payment(user, category, payment_day=11)

    with at(2026, 3, 11, 0, 30):
        admin_client.post("/api/process-regular-payments/")

    assert Expense.objects.get().date == date(2026, 3, 11)


@pytest.mark.django_db
def test_new_payment_with_a_passed_day_starts_next_month(
    api_client, admin_client, user, category
):
    payload = {
        "name": "Rent",
        "amount": 100,
        "payment_day": 1,
        "category": category.id,
    }
    with at(2026, 3, 20, 12, 0):
        api_client.post("/api/regular-payments/", payload)
        admin_client.post("/api/process-regular-payments/")
    assert Expense.objects.count() == 0

    with at(2026, 4, 1, 12, 0):
        admin_client.post("/api/process-regular-payments/")
    assert Expense.objects.count() == 1


@pytest.mark.django_db
def test_new_payment_due_today_is_charged_this_month(
    api_client, admin_client, user, category
):
    payload = {
        "name": "Rent",
        "amount": 100,
        "payment_day": 20,
        "category": category.id,
    }
    with at(2026, 3, 20, 12, 0):
        api_client.post("/api/regular-payments/", payload)
        admin_client.post("/api/process-regular-payments/")

    assert Expense.objects.count() == 1
