from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0004_add_pack_pricing"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="generic_name",
            field=models.CharField(blank=True, max_length=180),
        ),
        migrations.AddField(
            model_name="product",
            name="strength",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="product",
            name="dosage_form",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="product",
            name="batch_no",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="product",
            name="expiry_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
