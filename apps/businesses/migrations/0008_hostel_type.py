from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("businesses", "0007_rent_a_car_type"),
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
                    ("hostel", "Hostel"),
                ],
                default="general",
                max_length=30,
            ),
        ),
    ]
