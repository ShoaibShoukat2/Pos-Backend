from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("showroom", "0002_invoice_signatures_payments"),
    ]

    operations = [
        migrations.AddField(
            model_name="carsale",
            name="customer_photo",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="carsale",
            name="customer_thumbprint",
            field=models.TextField(blank=True),
        ),
    ]
