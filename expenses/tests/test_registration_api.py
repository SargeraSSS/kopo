"""/api/register-telegram/ - the endpoint the bot calls on every /start.

It runs under the admin token held by the bot process, so the checks here are
about who may call it and what happens when the same telegram_id arrives twice.
"""

from unittest import mock

import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from expenses.models import TelegramUser

TELEGRAM_ID = 123456789


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_user(username="bot_admin", password="pass123", is_staff=True)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=admin).key}")
    return client


@pytest.mark.django_db
def test_first_start_creates_user(admin_client):
    response = admin_client.post(
        "/api/register-telegram/", {"telegram_id": TELEGRAM_ID}, format="json"
    )

    assert response.status_code == 201
    assert response.data["token"]
    assert TelegramUser.objects.filter(telegram_id=TELEGRAM_ID).count() == 1


@pytest.mark.django_db
def test_second_start_returns_the_same_token(admin_client):
    """/start pressed again must not create a second user or rotate the token."""
    first = admin_client.post(
        "/api/register-telegram/", {"telegram_id": TELEGRAM_ID}, format="json"
    )

    second = admin_client.post(
        "/api/register-telegram/", {"telegram_id": TELEGRAM_ID}, format="json"
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.data["token"] == first.data["token"]
    assert TelegramUser.objects.filter(telegram_id=TELEGRAM_ID).count() == 1
    assert User.objects.filter(username=f"tg_{TELEGRAM_ID}").count() == 1


@pytest.mark.django_db
def test_simultaneous_start_does_not_500(admin_client):
    """Two /start in parallel: both miss the lookup, one loses on the unique index.

    The lookup is forced to miss so the view takes the create path for a
    telegram_id that already exists - what the losing request sees.
    """
    first = admin_client.post(
        "/api/register-telegram/", {"telegram_id": TELEGRAM_ID}, format="json"
    )

    with mock.patch.object(TelegramUser.objects, "filter") as lookup:
        lookup.return_value.first.return_value = None
        response = admin_client.post(
            "/api/register-telegram/", {"telegram_id": TELEGRAM_ID}, format="json"
        )

    assert response.status_code == 200
    assert response.data["token"] == first.data["token"]
    assert TelegramUser.objects.filter(telegram_id=TELEGRAM_ID).count() == 1


@pytest.mark.django_db
def test_regular_user_cannot_register(api_client):
    """A plain user token must not be able to mint accounts."""
    response = api_client.post(
        "/api/register-telegram/", {"telegram_id": TELEGRAM_ID}, format="json"
    )

    assert response.status_code == 403
    assert not TelegramUser.objects.filter(telegram_id=TELEGRAM_ID).exists()


@pytest.mark.django_db
def test_anonymous_cannot_register():
    response = APIClient().post(
        "/api/register-telegram/", {"telegram_id": TELEGRAM_ID}, format="json"
    )

    assert response.status_code == 401


@pytest.mark.django_db
@pytest.mark.parametrize("payload", [{}, {"telegram_id": None}, {"telegram_id": "abc"}])
def test_bad_telegram_id_is_rejected(admin_client, payload):
    response = admin_client.post("/api/register-telegram/", payload, format="json")

    assert response.status_code == 400


@pytest.mark.django_db
def test_token_lookup_endpoint_is_gone(admin_client):
    """/api/get-token/<telegram_id>/ used to hand out any user's token by their
    telegram_id. Nothing called it, so it was removed rather than kept as an
    admin-only convenience: a leaked ADMIN_TOKEN would have turned it into a
    way into every account. This pins that decision."""
    response = admin_client.get(f"/api/get-token/{TELEGRAM_ID}/")

    assert response.status_code == 404
