import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hostel", "0002_alter_hostelemployee_email"),
    ]

    operations = [
        migrations.AddField(
            model_name="hostelbed",
            name="furnishing",
            field=models.CharField(
                choices=[("bed", "Bed"), ("mattress", "Mattress")],
                default="bed",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="hostelroom",
            name="mattress_rent",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="hostelbranch",
            name="manager",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="managed_branch",
                to="hostel.hostelemployee",
            ),
        ),
    ]
