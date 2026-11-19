import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("businesses", "0007_rent_a_car_type"),
        ("rental", "0002_carrental_cnic_back_carrental_cnic_front_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="RentalTerms",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(blank=True, max_length=160)),
                ("clauses", models.JSONField(blank=True, default=list)),
                ("footer", models.CharField(blank=True, default="دستخط / انگوٹھا", max_length=120)),
                (
                    "business",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rental_terms",
                        to="businesses.business",
                    ),
                ),
            ],
            options={
                "verbose_name": "rental terms",
            },
        ),
    ]
