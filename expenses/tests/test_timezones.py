"""is_reminder_hour - decides who gets the daily reminder on each hourly run."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from expenses.timezones import TIME_ZONE_CHOICES, is_reminder_hour


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "zone, now, expected",
    [
        # Kyiv is UTC+3 in summer, UTC+2 in winter
        ("Europe/Kyiv", utc(2026, 7, 1, 16), True),
        ("Europe/Kyiv", utc(2026, 7, 1, 17), False),
        ("Europe/Kyiv", utc(2026, 1, 15, 17), True),
        # New York is UTC-4 in summer
        ("America/New_York", utc(2026, 7, 1, 23), True),
        ("America/New_York", utc(2026, 7, 1, 19), False),
        ("UTC", utc(2026, 7, 1, 19), True),
    ],
)
def test_reminder_hour_follows_the_zone(zone, now, expected):
    assert is_reminder_hour(zone, now) is expected


def test_missing_zone_falls_back_to_utc():
    """A user without a profile comes back from the API with timezone=None."""
    assert is_reminder_hour(None, utc(2026, 7, 1, 19)) is True
    assert is_reminder_hour(None, utc(2026, 7, 1, 16)) is False


@pytest.mark.parametrize("zone", [zone for zone, _ in TIME_ZONE_CHOICES])
def test_every_offered_zone_is_on_a_whole_hour(zone):
    """The job runs at :00 only; a +5:30 zone would never hit 19:00."""
    winter = utc(2026, 1, 15, 12).astimezone(ZoneInfo(zone))
    summer = utc(2026, 7, 1, 12).astimezone(ZoneInfo(zone))
    assert winter.minute == 0 and summer.minute == 0
