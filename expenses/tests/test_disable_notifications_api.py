"""/api/disable-notifications/ - called by the daily reminder job when Telegram
answers Forbidden, i.e. the user blocked the bot.

It runs under the admin token held by the bot process and is addressed by
telegram_id, so the checks here are about who may call it, that it only ever
touches the one user it was asked about, and that bad input is not a 500.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from expenses.models import TelegramUser, UserProfile

URL = "/api/disable-notifications/"
TELEGRAM_ID = 123456789
OTHER_TELEGRAM_ID = 987654321


def make_tg_user(telegram_id, notification_status=True):
    user = User.objects.create_user(username=f"tg_{telegram_id}")
    TelegramUser.objects.create(user=user, telegram_id=telegram_id)
    UserProfile.objects.create(user=user, notification_status=notification_status)
    return user


def notifications_of(user):
    return UserProfile.objects.get(user=user).notification_status


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_user(username="bot_admin", password="pass123", is_staff=True)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=admin).key}")
    return client


@pytest.mark.django_db
def test_blocked_user_gets_notifications_turned_off(admin_client):
    user = make_tg_user(TELEGRAM_ID)

    response = admin_client.post(URL, {"telegram_id": TELEGRAM_ID}, format="json")

    assert response.status_code == 200
    assert notifications_of(user) is False


@pytest.mark.django_db
def test_other_users_keep_their_notifications(admin_client):
    """The filter is by telegram_id - a wrong lookup here would silence everyone."""
    make_tg_user(TELEGRAM_ID)
    bystander = make_tg_user(OTHER_TELEGRAM_ID)

    admin_client.post(URL, {"telegram_id": TELEGRAM_ID}, format="json")

    assert notifications_of(bystander) is True


@pytest.mark.django_db
def test_disabling_twice_is_harmless(admin_client):
    """The job may hit the same blocked user again before the flag is read."""
    user = make_tg_user(TELEGRAM_ID, notification_status=False)

    response = admin_client.post(URL, {"telegram_id": TELEGRAM_ID}, format="json")

    assert response.status_code == 200
    assert notifications_of(user) is False


@pytest.mark.django_db
def test_user_without_profile_does_not_500(admin_client):
    """UserProfile is created lazily, so a user who only pressed /start has none."""
    user = User.objects.create_user(username=f"tg_{TELEGRAM_ID}")
    TelegramUser.objects.create(user=user, telegram_id=TELEGRAM_ID)

    response = admin_client.post(URL, {"telegram_id": TELEGRAM_ID}, format="json")

    assert response.status_code == 200


@pytest.mark.django_db
def test_unknown_telegram_id_is_404(admin_client):
    bystander = make_tg_user(OTHER_TELEGRAM_ID)

    response = admin_client.post(URL, {"telegram_id": TELEGRAM_ID}, format="json")

    assert response.status_code == 404
    assert notifications_of(bystander) is True


@pytest.mark.django_db
@pytest.mark.parametrize("payload", [{}, {"telegram_id": None}, {"telegram_id": "abc"}])
def test_bad_telegram_id_is_rejected(admin_client, payload):
    response = admin_client.post(URL, payload, format="json")

    assert response.status_code == 400


@pytest.mark.django_db
def test_regular_user_cannot_disable_notifications(api_client):
    """A user token must not be able to switch off someone else's reminders."""
    victim = make_tg_user(TELEGRAM_ID)

    response = api_client.post(URL, {"telegram_id": TELEGRAM_ID}, format="json")

    assert response.status_code == 403
    assert notifications_of(victim) is True


@pytest.mark.django_db
def test_anonymous_cannot_disable_notifications():
    victim = make_tg_user(TELEGRAM_ID)

    response = APIClient().post(URL, {"telegram_id": TELEGRAM_ID}, format="json")

    assert response.status_code == 401
    assert notifications_of(victim) is True
