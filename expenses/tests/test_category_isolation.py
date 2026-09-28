"""Another user's category through the ForeignKey.

`CategoryViewSet` only hands a user their own and the shared categories, but
`ExpenseSerializer.category` and `RegularPaymentsSerializer.category` are
`PrimaryKeyRelatedField`s over ALL categories. User B could pass user A's
category id, and A's category name would surface in B's own /api/stats/
and /api/history/.

Also covers list isolation for categories / income / regular-payments
(expenses are already covered in test_expenses_api.py).
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
    """A owns a private category, B owns nothing, plus one shared category."""
    user_a, client_a = make_client("user_a")
    user_b, client_b = make_client("user_b")
    private = Category.objects.create(name="Private category of A", user=user_a)
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
    """The error must not confirm the id exists, nor echo the category name."""
    response = two_users["client_b"].post(
        "/api/expenses/",
        {"amount": 100, "category": two_users["private_a"].id},
        format="json",
    )

    assert "Private category of A" not in str(response.data)
    assert "user_a" not in str(response.data)


@pytest.mark.django_db
def test_expense_with_own_category_still_works(two_users):
    own = Category.objects.create(name="Transport", user=two_users["user_b"])
    response = two_users["client_b"].post(
        "/api/expenses/", {"amount": 100, "category": own.id}, format="json"
    )

    assert response.status_code == 201


@pytest.mark.django_db
def test_expense_with_shared_category_still_works(two_users):
    """Shared categories (user=None) must stay available to everyone."""
    response = two_users["client_b"].post(
        "/api/expenses/",
        {"amount": 100, "category": two_users["shared"].id},
        format="json",
    )

    assert response.status_code == 201


@pytest.mark.django_db
def test_expense_cannot_be_moved_to_other_users_category(two_users):
    """Not through create, but by PATCHing an expense the user already owns."""
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
    """End to end: A's category name must never show up in B's report."""
    two_users["client_b"].post(
        "/api/expenses/",
        {"amount": 100, "category": two_users["private_a"].id},
        format="json",
    )

    stats = two_users["client_b"].get("/api/stats/")
    assert "Private category of A" not in str(stats.data)


# --- regular payments ---------------------------------------------------


@pytest.mark.django_db
def test_regular_payment_with_other_users_category_is_rejected(two_users):
    response = two_users["client_b"].post(
        "/api/regular-payments/",
        {
            "name": "Internet",
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
            "name": "Internet",
            "amount": 65,
            "payment_day": 10,
            "category": two_users["shared"].id,
        },
        format="json",
    )

    assert response.status_code == 201


# --- list isolation -----------------------------------------------------


@pytest.mark.django_db
def test_categories_list_hides_other_users_categories(two_users):
    response = two_users["client_b"].get("/api/categories/")

    assert response.status_code == 200
    names = [item["name"] for item in response.data]
    assert "Private category of A" not in names
    assert "Food" in names  # shared one must stay visible


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
        name="Rent of A",
        amount=2000,
        payment_day=1,
        category=two_users["private_a"],
    )

    response = two_users["client_b"].get("/api/regular-payments/")

    assert response.status_code == 200
    assert len(response.data) == 0
