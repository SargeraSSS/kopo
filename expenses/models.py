from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

CURRENCY_CHOICES = [
    ("PLN", "PLN zł"),
    ("UAH", "UAH ₴"),
    ("EUR", "EUR €"),
    ("USD", "USD $"),
]
TIME_ZONES = TIME_ZONE_CHOICES = [
    # Europe
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
    # America
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
    # Other
    ("UTC", "UTC"),
]


class Category(models.Model):
    name = models.CharField(max_length=50)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="categories", null=True, blank=True
    )

    def __str__(self):
        return self.name


class Expense(models.Model):
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    date = models.DateField(auto_now_add=True)
    description = models.CharField(max_length=50, blank=True, null=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="PLN")


class Income(models.Model):
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField(auto_now_add=True)
    description = models.CharField(max_length=50, blank=True, null=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="PLN")


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="PLN")
    notification_status = models.BooleanField(default=True)
    savings_goal = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(0)],
    )
    timezone = models.CharField(max_length=64, default="UTC")


class TelegramUser(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="telegram_profile"
    )
    telegram_id = models.BigIntegerField(unique=True, verbose_name="Telegram User ID")


class RegularPayments(models.Model):
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    name = models.CharField(max_length=100)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    payment_day = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(31)]
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    last_charged = models.DateField(blank=True, null=True)
