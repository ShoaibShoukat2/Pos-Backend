from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0005_product_pharmacy_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="productvariant",
            name="carton_barcode",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="productvariant",
            name="carton_price",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Price for one full carton. 0 = no carton pricing.",
                max_digits=14,
            ),
        ),
        migrations.AddField(
            model_name="productvariant",
            name="carton_quantity",
            field=models.DecimalField(
                decimal_places=3,
                default=0,
                help_text="Pieces in one carton (cotton). 0 = no carton pricing.",
                max_digits=14,
            ),
        ),
        migrations.AddField(
            model_name="productvariant",
            name="garment_type",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="productvariant",
            name="size",
            field=models.CharField(blank=True, max_length=8),
        ),
    ]
