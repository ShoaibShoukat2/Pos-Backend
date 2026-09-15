from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_platform_admin",
            field=models.BooleanField(
                default=False,
                help_text="Software owner who can see every business on the platform.",
            ),
        ),
    ]
