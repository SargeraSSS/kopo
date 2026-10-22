"""Timezone choices, kept free of Django imports so bot.py can use them too."""

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
