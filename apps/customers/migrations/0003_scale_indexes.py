from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0002_phase6_saas"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="customer",
            index=models.Index(fields=["business", "is_active"], name="cust_biz_active_idx"),
        ),
        migrations.AddIndex(
            model_name="customer",
            index=models.Index(fields=["business", "name"], name="cust_biz_name_idx"),
        ),
        migrations.AddIndex(
            model_name="customer",
            index=models.Index(fields=["phone"], name="cust_phone_idx"),
        ),
    ]
