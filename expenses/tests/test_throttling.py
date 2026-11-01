"""Rates are read once, at import, into SimpleRateThrottle.THROTTLE_RATES, so
override_settings has no effect: the tests patch that attribute instead."""

from unittest import mock

import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from expenses.models import TelegramUser


def rates(**values):
    return mock.patch.object(SimpleRateThrottle, "THROTTLE_RATES", values)


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_user(username="bot_admin", is_staff=True)
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=admin).key}"
    )
    return client


def client_for(username):
    user = User.objects.create_user(username=username)
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}"
    )
    return client


@pytest.mark.django_db
def test_user_over_the_limit_gets_429_with_retry_after(api_client):
    with rates(user="2/minute"):
        statuses = [api_client.get("/api/stats/").status_code for _ in range(3)]
        response = api_client.get("/api/stats/")

    assert statuses == [200, 200, 429]
    assert int(response.headers["Retry-After"]) > 0


@pytest.mark.django_db
def test_one_users_limit_does_not_touch_another():
    first, second = client_for("first"), client_for("second")

    with rates(user="1/minute"):
        first.get("/api/stats/")
        assert first.get("/api/stats/").status_code == 429
        assert second.get("/api/stats/").status_code == 200


@pytest.mark.django_db
def test_registration_is_limited_per_telegram_id(admin_client):
    def register(telegram_id):
        return admin_client.post(
            "/api/register-telegram/", {"telegram_id": telegram_id}
        ).status_code

    with rates(registration="1/minute"):
        assert register(1) == 201
        assert register(1) == 429
        assert register(2) == 201


@pytest.mark.django_db
def test_bad_telegram_ids_share_one_limit(admin_client):
    def register(telegram_id):
        return admin_client.post(
            "/api/register-telegram/", {"telegram_id": telegram_id}
        ).status_code

    with rates(registration="1/minute"):
        assert register("abc") == 400
        assert register("def") == 429


@pytest.mark.django_db
@pytest.mark.parametrize(
    "method, url, payload",
    [
        ("get", "/api/all-telegram-ids/", None),
        ("post", "/api/process-regular-payments/", None),
        ("post", "/api/disable-notifications/", {"telegram_id": 1}),
    ],
)
def test_the_bots_own_jobs_are_never_throttled(admin_client, method, url, payload):
    user = User.objects.create_user(username="tg_1")
    TelegramUser.objects.create(user=user, telegram_id=1)

    with rates(user="1/minute"):
        statuses = [
            getattr(admin_client, method)(url, payload).status_code for _ in range(5)
        ]

    assert statuses == [200] * 5


@pytest.mark.django_db
def test_password_login_endpoint_is_gone():
    response = APIClient().post(
        "/api/token/", {"username": "admin", "password": "secret"}
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_api_answers_only_in_json(api_client):
    response = api_client.get("/api/stats/", HTTP_ACCEPT="text/html")

    assert response.status_code == 406
