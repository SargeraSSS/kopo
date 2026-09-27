from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

CURRENCY_CHOICES = [
    ("PLN", "PLN zł"),
    ("UAH", "UAH ₴"),
    ("EUR", "EUR €"),
    ("USD", "USD $"),
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
