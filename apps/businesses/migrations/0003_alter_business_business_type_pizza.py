from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("businesses", "0002_alter_business_business_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="business",
            name="business_type",
            field=models.CharField(
                choices=[
                    ("grocery", "Grocery"),
                    ("clothing", "Clothing"),
                    ("restaurant", "Restaurant"),
                    ("pharmacy", "Pharmacy"),
                    ("electronics", "Electronics"),
                    ("pizza", "Pizza shop"),
                    ("general", "General Retail"),
                ],
                default="general",
                max_length=30,
            ),
        ),
    ]
