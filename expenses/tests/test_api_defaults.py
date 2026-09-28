"""DRF defaults in settings.py.

Default permissions are a safety net: if a new view forgets its own
`permission_classes`, it should stay closed instead of opening to the world.
These tests pin the intent, so the key can't quietly disappear the next time
someone edits settings.
"""

import pytest
from django.conf import settings
from rest_framework.test import APIClient


def test_default_permission_is_authenticated():
    permissions = settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]
    assert "rest_framework.permissions.IsAuthenticated" in permissions


def test_default_authentication_is_token():
    """Right next to it, because this is the key most easily clobbered
    while adding permissions."""
    authentication = settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]
    assert "rest_framework.authentication.TokenAuthentication" in authentication


@pytest.mark.django_db
def test_anonymous_request_is_rejected():
    """The default must actually apply, not just sit in settings."""
    response = APIClient().get("/api/stats/")
    assert response.status_code == 401
