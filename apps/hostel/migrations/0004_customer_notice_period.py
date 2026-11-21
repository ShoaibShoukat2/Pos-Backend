from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hostel", "0003_branch_manager_and_seat_furnishing"),
    ]

    operations = [
        migrations.AddField(
            model_name="hostelcustomer",
            name="notice_given_on",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="hostelcustomer",
            name="notice_leave_on",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="hostelcustomer",
            name="notice_note",
            field=models.CharField(blank=True, max_length=400),
        ),
    ]
