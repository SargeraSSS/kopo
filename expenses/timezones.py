"""Timezone choices, kept free of Django imports so bot.py can use them too."""

from zoneinfo import ZoneInfo

REMINDER_HOUR = 19

TIME_ZONE_GROUPS = {
    "Europe": [
        ("Europe/Kyiv", "Kyiv"),
        ("Europe/Warsaw", "Warsaw"),
        ("Europe/Berlin", "Berlin"),
        ("Europe/Paris", "Paris"),
        ("Europe/Madrid", "Madrid"),
        ("Europe/Rome", "Rome"),
        ("Europe/Amsterdam", "Amsterdam"),
        ("Europe/Brussels", "Brussels"),
        ("Europe/Vienna", "Vienna"),
        ("Europe/Prague", "Prague"),
        ("Europe/Stockholm", "Stockholm"),
        ("Europe/Helsinki", "Helsinki"),
        ("Europe/Athens", "Athens"),
        ("Europe/Bucharest", "Bucharest"),
        ("Europe/Lisbon", "Lisbon"),
        ("Europe/London", "London"),
        ("Europe/Dublin", "Dublin"),
        ("Europe/Istanbul", "Istanbul"),
    ],
    "America": [
        ("America/New_York", "New York"),
        ("America/Chicago", "Chicago"),
        ("America/Denver", "Denver"),
        ("America/Los_Angeles", "Los Angeles"),
        ("America/Anchorage", "Anchorage"),
        ("America/Toronto", "Toronto"),
        ("America/Vancouver", "Vancouver"),
        ("America/Mexico_City", "Mexico City"),
        ("America/Bogota", "Bogota"),
        ("America/Lima", "Lima"),
        ("America/Santiago", "Santiago"),
        ("America/Sao_Paulo", "Sao Paulo"),
        ("America/Argentina/Buenos_Aires", "Buenos Aires"),
    ],
}
TIME_ZONE_CHOICES = [
    zone for zones in TIME_ZONE_GROUPS.values() for zone in zones
] + [("UTC", "UTC")]


def is_reminder_hour(zone_name, now_utc):
    """True if it is REMINDER_HOUR o'clock in zone_name at now_utc.

    The reminder job runs hourly, which is enough because every zone above has
    a whole-hour offset. A +5:30 zone would need a run at :30 too.
    A missing zone (user without a profile) falls back to UTC.
    """
    return now_utc.astimezone(ZoneInfo(zone_name or "UTC")).hour == REMINDER_HOUR
