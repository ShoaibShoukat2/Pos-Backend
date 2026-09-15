from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["business", "is_active"], name="prd_biz_active_idx"),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["business", "name"], name="prd_biz_name_idx"),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["barcode"], name="prd_barcode_idx"),
        ),
        migrations.AddIndex(
            model_name="productvariant",
            index=models.Index(fields=["business", "is_active"], name="var_biz_active_idx"),
        ),
        migrations.AddIndex(
            model_name="productvariant",
            index=models.Index(fields=["barcode"], name="var_barcode_idx"),
        ),
        migrations.AddIndex(
            model_name="productvariant",
            index=models.Index(fields=["product", "is_active"], name="var_prd_active_idx"),
        ),
    ]
