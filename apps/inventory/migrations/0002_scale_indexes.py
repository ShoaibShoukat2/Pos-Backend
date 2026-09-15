from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="stocklevel",
            index=models.Index(fields=["business", "branch"], name="stk_biz_branch_idx"),
        ),
        migrations.AddIndex(
            model_name="stocklevel",
            index=models.Index(fields=["business", "variant"], name="stk_biz_var_idx"),
        ),
        migrations.AddIndex(
            model_name="stockmovement",
            index=models.Index(fields=["business", "created_at"], name="mov_biz_created_idx"),
        ),
        migrations.AddIndex(
            model_name="stockmovement",
            index=models.Index(fields=["business", "movement_type", "created_at"], name="mov_biz_type_dt_idx"),
        ),
        migrations.AddIndex(
            model_name="stockmovement",
            index=models.Index(fields=["variant", "created_at"], name="mov_var_created_idx"),
        ),
    ]
