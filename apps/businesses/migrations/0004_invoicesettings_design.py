from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("businesses", "0003_alter_business_business_type_pizza"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoicesettings",
            name="design",
            field=models.CharField(
                choices=[
                    ("classic", "Classic"),
                    ("compact", "Compact"),
                    ("bold", "Bold"),
                    ("formal", "Formal"),
                ],
                default="classic",
                max_length=16,
            ),
        ),
    ]
