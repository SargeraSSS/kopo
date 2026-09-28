"""Чужа категорія через ForeignKey.

`CategoryViewSet` віддає юзеру тільки його власні та спільні категорії, але
`ExpenseSerializer.category` і `RegularPaymentsSerializer.category` —
`PrimaryKeyRelatedField` по ВСІХ Category. Юзер B може підсунути id категорії
юзера A, і чужа назва вилізе в його ж `/api/stats/` та `/api/history/`.

Тут же — ізоляція списків для categories / income / regular-payments
(на expenses вона вже покрита в test_expenses_api.py).
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from expenses.models import Category, Expense, Income, RegularPayments


def make_client(username):
    user = User.objects.create_user(username=username, password="pass123")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}")
    return user, client


@pytest.fixture
def two_users(db):
    """A з власною категорією, B — порожній, плюс спільна категорія без власника."""
    user_a, client_a = make_client("user_a")
    user_b, client_b = make_client("user_b")
    private = Category.objects.create(name="Секретна категорія A", user=user_a)
    shared = Category.objects.create(name="Food", user=None)
    return {
        "user_a": user_a,
        "client_a": client_a,
        "user_b": user_b,
        "client_b": client_b,
        "private_a": private,
        "shared": shared,
    }


# --- expenses -----------------------------------------------------------


@pytest.mark.django_db
def test_expense_with_other_users_category_is_rejected(two_users):
    response = two_users["client_b"].post(
        "/api/expenses/",
        {"amount": 100, "category": two_users["private_a"].id},
        format="json",
    )

    assert response.status_code == 400
    assert Expense.objects.count() == 0


@pytest.mark.django_db
def test_expense_error_does_not_leak_the_category(two_users):
    """Текст помилки не повинен підтверджувати, що такий id існує, ані палити назву."""
    response = two_users["client_b"].post(
        "/api/expenses/",
        {"amount": 100, "category": two_users["private_a"].id},
        format="json",
    )

    assert "Секретна" not in str(response.data)
    assert "user_a" not in str(response.data)


@pytest.mark.django_db
def test_expense_with_own_category_still_works(two_users):
    own = Category.objects.create(name="Транспорт", user=two_users["user_b"])
    response = two_users["client_b"].post(
        "/api/expenses/", {"amount": 100, "category": own.id}, format="json"
    )

    assert response.status_code == 201


@pytest.mark.django_db
def test_expense_with_shared_category_still_works(two_users):
    """Спільні категорії (user=None) мають лишитись доступними всім."""
    response = two_users["client_b"].post(
        "/api/expenses/",
        {"amount": 100, "category": two_users["shared"].id},
        format="json",
    )

    assert response.status_code == 201


@pytest.mark.django_db
def test_expense_cannot_be_moved_to_other_users_category(two_users):
    """Підміна не через create, а через PATCH уже створеної своєї витрати."""
    expense = Expense.objects.create(
        user=two_users["user_b"], amount=100, category=two_users["shared"]
    )

    response = two_users["client_b"].patch(
        f"/api/expenses/{expense.id}/",
        {"category": two_users["private_a"].id},
        format="json",
    )

    assert response.status_code == 400
    expense.refresh_from_db()
    assert expense.category == two_users["shared"]


@pytest.mark.django_db
def test_other_users_category_never_reaches_stats(two_users):
    """Наскрізна перевірка: чужа назва не має вилізти у звіті юзера B."""
    two_users["client_b"].post(
        "/api/expenses/",
        {"amount": 100, "category": two_users["private_a"].id},
        format="json",
    )

    stats = two_users["client_b"].get("/api/stats/")
    assert "Секретна категорія A" not in str(stats.data)


# --- regular payments ---------------------------------------------------


@pytest.mark.django_db
def test_regular_payment_with_other_users_category_is_rejected(two_users):
    response = two_users["client_b"].post(
        "/api/regular-payments/",
        {
            "name": "Інтернет",
            "amount": 65,
            "payment_day": 10,
            "category": two_users["private_a"].id,
        },
        format="json",
    )

    assert response.status_code == 400
    assert RegularPayments.objects.count() == 0


@pytest.mark.django_db
def test_regular_payment_with_shared_category_still_works(two_users):
    response = two_users["client_b"].post(
        "/api/regular-payments/",
        {
            "name": "Інтернет",
            "amount": 65,
            "payment_day": 10,
            "category": two_users["shared"].id,
        },
        format="json",
    )

    assert response.status_code == 201


# --- ізоляція списків ---------------------------------------------------


@pytest.mark.django_db
def test_categories_list_hides_other_users_categories(two_users):
    response = two_users["client_b"].get("/api/categories/")

    assert response.status_code == 200
    names = [item["name"] for item in response.data]
    assert "Секретна категорія A" not in names
    assert "Food" in names  # спільна — має бути видно


@pytest.mark.django_db
def test_income_list_hides_other_users_income(two_users):
    Income.objects.create(user=two_users["user_a"], amount=5000)

    response = two_users["client_b"].get("/api/income/")

    assert response.status_code == 200
    assert len(response.data) == 0


@pytest.mark.django_db
def test_regular_payments_list_hides_other_users_payments(two_users):
    RegularPayments.objects.create(
        user=two_users["user_a"],
        name="Оренда A",
        amount=2000,
        payment_day=1,
        category=two_users["private_a"],
    )

    response = two_users["client_b"].get("/api/regular-payments/")

    assert response.status_code == 200
    assert len(response.data) == 0
