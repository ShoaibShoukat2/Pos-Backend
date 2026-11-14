from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


def backfill_invoice_numbers(apps, schema_editor):
    CarSale = apps.get_model("showroom", "CarSale")
    DocumentSequence = apps.get_model("core", "DocumentSequence")
    counters = {}
    for sale in CarSale.objects.all().order_by("business_id", "created_at"):
        n = counters.get(sale.business_id, 0) + 1
        counters[sale.business_id] = n
        sale.invoice_number = f"SR-{n:05d}"
        sale.save(update_fields=["invoice_number"])
    for business_id, n in counters.items():
        DocumentSequence.objects.update_or_create(
            business_id=business_id,
            key="car_sale",
            defaults={"prefix": "SR", "padding": 5, "next_number": n + 1},
        )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("businesses", "0006_add_price_checker"),
        ("core", "0001_initial"),
        ("showroom", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="carsale",
            name="invoice_number",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="carsale",
            name="customer_signature",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="carsale",
            name="dealer_signature",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="carsale",
            name="signed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterUniqueTogether(
            name="carsale",
            unique_together={("business", "invoice_number")},
        ),
        migrations.CreateModel(
            name="CarSalePayment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("payment_date", models.DateField()),
                ("payment_method", models.CharField(choices=[("cash", "Cash"), ("bank", "Bank Transfer"), ("card", "Card"), ("jazzcash", "JazzCash"), ("easypaisa", "Easypaisa")], default="cash", max_length=12)),
                ("notes", models.CharField(blank=True, max_length=200)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="car_sale_payments", to="businesses.business")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("sale", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="payments", to="showroom.carsale")),
            ],
            options={"ordering": ["payment_date", "created_at"]},
        ),
        migrations.RunPython(backfill_invoice_numbers, migrations.RunPython.noop),
    ]
