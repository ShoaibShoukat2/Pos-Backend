from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pos", "0003_scanner_sessions"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="sale",
            index=models.Index(fields=["business", "status", "created_at"], name="sale_biz_st_dt_idx"),
        ),
        migrations.AddIndex(
            model_name="sale",
            index=models.Index(fields=["branch", "created_at"], name="sale_br_created_idx"),
        ),
    ]
