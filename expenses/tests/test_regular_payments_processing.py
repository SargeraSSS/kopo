"""/api/process-regular-payments/ - turns due regular payments into expenses.

The bot's scheduler calls it, and the scheduler is not reliable: the bot can be
down on the payment day, or call twice after a restart. So the endpoint has to
be safe to call any number of times, on any day.

"Today" is frozen by patching django.utils.timezone.now, so the view must take
the current date from timezone.localdate(), not date.today().
"""

from datetime import date, datetime, timezone
from unittest import mock

import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from expenses.models import Category, Expense, RegularPayments

URL = "/api/process-regular-payments/"


def on(year, month, day):
    """Freeze the server date. Noon UTC keeps the local date the same anywhere."""
    moment = datetime(year, month, day, 12, 0, tzinfo=timezone.utc)
    return mock.patch("django.utils.timezone.now", return_value=moment)


def make_payment(user, payment_day, last_charged=None):
    category = Category.objects.create(name="Rent", user=user)
    return RegularPayments.objects.create(
        amount=1000,
        name="Flat",
        category=category,
        payment_day=payment_day,
        user=user,
        last_charged=last_charged,
    )


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_user(username="bot_admin", password="pass123", is_staff=True)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=admin).key}")
    return client


@pytest.mark.django_db
def test_repeated_call_does_not_duplicate(admin_client, user):
    """A restart on the payment day, then the normal run the day after."""
    make_payment(user, payment_day=10)

    with on(2026, 3, 10):
        admin_client.post(URL)
        admin_client.post(URL)
    with on(2026, 3, 11):
        admin_client.post(URL)

    assert Expense.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_payment_with_a_future_day_is_not_created(admin_client, user):
    payment = make_payment(user, payment_day=15)

    with on(2026, 3, 10):
        response = admin_client.post(URL)

    assert response.status_code == 200
    assert Expense.objects.count() == 0
    payment.refresh_from_db()
    assert payment.last_charged is None


@pytest.mark.django_db
def test_missed_day_is_caught_up_by_the_next_call(admin_client, user):
    """The bot was down on the 5th; the first call after it comes back pays."""
    payment = make_payment(user, payment_day=5)

    with on(2026, 3, 20):
        admin_client.post(URL)

    expense = Expense.objects.get(user=user)
    assert expense.amount == payment.amount
    assert expense.category == payment.category
    payment.refresh_from_db()
    assert payment.last_charged == date(2026, 3, 20)


@pytest.mark.django_db
def test_payment_is_charged_again_next_month(admin_client, user):
    """Guards against "never duplicate" turning into "charge once, ever"."""
    make_payment(user, payment_day=10, last_charged=date(2026, 2, 10))

    with on(2026, 3, 10):
        admin_client.post(URL)

    assert Expense.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_day_31_is_charged_on_the_last_day_of_a_short_month(admin_client, user):
    make_payment(user, payment_day=31)

    with on(2026, 2, 27):
        admin_client.post(URL)
    assert Expense.objects.count() == 0

    with on(2026, 2, 28):
        admin_client.post(URL)
    assert Expense.objects.count() == 1
