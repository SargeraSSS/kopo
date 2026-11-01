from django.db import migrations


def create_missing_profiles(apps, schema_editor):
    """Users registered before /start created a profile never got reminders."""
    TelegramUser = apps.get_model("expenses", "TelegramUser")
    UserProfile = apps.get_model("expenses", "UserProfile")
    users = TelegramUser.objects.filter(user__userprofile__isnull=True)
    UserProfile.objects.bulk_create(
        UserProfile(user_id=user_id) for user_id in users.values_list("user_id", flat=True)
    )


class Migration(migrations.Migration):
    dependencies = [
        ("expenses", "0020_dates_follow_user_timezone"),
    ]

    operations = [
        migrations.RunPython(create_missing_profiles, migrations.RunPython.noop),
    ]
