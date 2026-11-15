from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("businesses", "0006_add_price_checker"),
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
                    ("car_showroom", "Car Showroom"),
                    ("rent_a_car", "Rent a Car"),
                ],
                default="general",
                max_length=30,
            ),
        ),
    ]
