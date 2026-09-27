"""Profile settings endpoints, exercised the way the bot actually calls them.

The bot sends JSON bodies (httpx `json=`), so every request here uses
format="json" too — form-encoded input coerces types differently.
"""

import pytest
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from expenses.models import UserProfile


def profile_of(user):
    return UserProfile.objects.get(user=user)


# --- savings goal -----------------------------------------------------------


@pytest.mark.django_db
def test_savings_goal_is_stored(api_client, user):
    """The normal path: user types 1500 in the goal prompt."""
    response = api_client.post(
        "/api/set-savings-goal/", {"savings_goal": 1500}, format="json"
    )
    assert response.status_code == 200
    assert profile_of(user).savings_goal == Decimal("1500.00")


@pytest.mark.django_db
def test_savings_goal_too_large_is_rejected(api_client, user):
    """A user typing a huge number used to hit numeric(8,2) overflow -> 500."""
    api_client.post("/api/set-savings-goal/", {"savings_goal": 1500}, format="json")

    response = api_client.post(
        "/api/set-savings-goal/", {"savings_goal": 999999999}, format="json"
    )

    assert response.status_code == 400
    assert profile_of(user).savings_goal == Decimal("1500.00")


@pytest.mark.django_db
def test_negative_savings_goal_is_rejected(api_client, user):
    """A negative goal used to be stored silently and inflate the daily limit."""
    api_client.post("/api/set-savings-goal/", {"savings_goal": 1500}, format="json")

    response = api_client.post(
        "/api/set-savings-goal/", {"savings_goal": -5000}, format="json"
    )

    assert response.status_code == 400
    assert profile_of(user).savings_goal == Decimal("1500.00")


@pytest.mark.django_db
def test_savings_goal_is_cleared_by_null(api_client, user):
    """What the "🗑 Remove goal" button sends."""
    api_client.post("/api/set-savings-goal/", {"savings_goal": 1500}, format="json")

    response = api_client.post(
        "/api/set-savings-goal/", {"savings_goal": None}, format="json"
    )

    assert response.status_code == 200
    assert profile_of(user).savings_goal is None


@pytest.mark.django_db
def test_stats_works_without_a_savings_goal(api_client, user):
    """Clearing the goal must not break the /stats screen."""
    api_client.post("/api/set-savings-goal/", {"savings_goal": None}, format="json")

    response = api_client.get("/api/stats/")

    assert response.status_code == 200


# --- currency ---------------------------------------------------------------


@pytest.mark.django_db
def test_currency_is_stored(api_client, user):
    """Sent by the currency buttons, which carry the code in callback_data."""
    response = api_client.post("/api/set-currency/", {"currency": "UAH"}, format="json")

    assert response.status_code == 200
    assert profile_of(user).currency == "UAH"


@pytest.mark.django_db
def test_unknown_currency_is_rejected(api_client, user):
    """An unlisted code fits varchar(3) and used to be stored, breaking /stats."""
    api_client.post("/api/set-currency/", {"currency": "UAH"}, format="json")

    response = api_client.post("/api/set-currency/", {"currency": "XYZ"}, format="json")

    assert response.status_code == 400
    assert profile_of(user).currency == "UAH"


@pytest.mark.django_db
def test_overlong_currency_is_rejected(api_client, user):
    """Longer than the column: used to reach Postgres and raise DataError -> 500."""
    response = api_client.post(
        "/api/set-currency/", {"currency": "dollars"}, format="json"
    )

    assert response.status_code == 400


# --- notifications ----------------------------------------------------------


@pytest.mark.django_db
def test_notification_toggle_round_trip(api_client, user):
    """The toggle flow from bot.py: read the profile, invert, send it back."""
    current = api_client.get("/api/get-profile/").data["notification_status"]
    assert current is True

    response = api_client.post(
        "/api/notification-status/", {"notification_status": not current}, format="json"
    )

    assert response.status_code == 200
    assert profile_of(user).notification_status is False
    assert api_client.get("/api/get-profile/").data["notification_status"] is False


@pytest.mark.django_db
def test_string_false_turns_notifications_off(api_client, user):
    """A client sending "false" as a string used to switch notifications ON."""
    response = api_client.post(
        "/api/notification-status/", {"notification_status": "false"}, format="json"
    )

    assert response.status_code == 200
    assert profile_of(user).notification_status is False


@pytest.mark.django_db
def test_non_boolean_notification_status_is_rejected(api_client, user):
    response = api_client.post(
        "/api/notification-status/", {"notification_status": "maybe"}, format="json"
    )

    assert response.status_code == 400
    assert profile_of(user).notification_status is True


# --- ownership and auth -----------------------------------------------------


@pytest.mark.django_db
def test_settings_do_not_leak_between_users(api_client, user):
    """Each token writes to its own profile only."""
    other = User.objects.create_user(username="other", password="pass123")
    other_client = APIClient()
    other_client.credentials(
        HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=other).key}"
    )

    api_client.post("/api/set-currency/", {"currency": "UAH"}, format="json")
    other_client.post("/api/set-currency/", {"currency": "EUR"}, format="json")

    assert profile_of(user).currency == "UAH"
    assert profile_of(other).currency == "EUR"


@pytest.mark.django_db
def test_settings_require_auth():
    anonymous = APIClient()

    assert anonymous.post("/api/set-currency/", {"currency": "UAH"}).status_code == 401
    assert anonymous.post("/api/set-savings-goal/", {"savings_goal": 1}).status_code == 401
    assert (
        anonymous.post("/api/notification-status/", {"notification_status": True}).status_code
        == 401
    )
