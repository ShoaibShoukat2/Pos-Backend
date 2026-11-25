from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pos", "0005_sale_returns"),
    ]

    operations = [
        migrations.AddField(
            model_name="saleline",
            name="sale_unit",
            field=models.CharField(default="piece", max_length=12),
        ),
    ]
