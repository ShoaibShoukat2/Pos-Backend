from datetime import timedelta

from django.db import migrations, models
from django.utils import timezone


def grant_current_month(apps, schema_editor):
    Business = apps.get_model("businesses", "Business")
    end = timezone.localdate() + timedelta(days=30)
    Business.objects.filter(subscription_ends_on__isnull=True).update(subscription_ends_on=end)


class Migration(migrations.Migration):

    dependencies = [
        ("businesses", "0008_hostel_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="business",
            name="subscription_ends_on",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.RunPython(grant_current_month, migrations.RunPython.noop),
    ]
