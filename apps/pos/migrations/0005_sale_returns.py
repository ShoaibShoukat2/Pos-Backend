import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_net_total(apps, schema_editor):
    Sale = apps.get_model("pos", "Sale")
    Sale.objects.update(net_total=models.F("total"))


class Migration(migrations.Migration):
    dependencies = [
        ("businesses", "0001_initial"),
        ("catalog", "0001_initial"),
        ("pos", "0004_scale_indexes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="sale",
            name="loyalty_returned",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="sale",
            name="net_total",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="sale",
            name="refunded_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="sale",
            name="returned_total",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="saleline",
            name="returned_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="saleline",
            name="returned_qty",
            field=models.DecimalField(decimal_places=3, default=0, max_digits=14),
        ),
        migrations.AlterField(
            model_name="sale",
            name="status",
            field=models.CharField(
                choices=[
                    ("completed", "Completed"),
                    ("partial", "Partial return"),
                    ("returned", "Returned"),
                    ("void", "Void"),
                ],
                default="completed",
                max_length=12,
            ),
        ),
        migrations.CreateModel(
            name="SaleReturn",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("number", models.CharField(max_length=30)),
                ("refund_amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("credit_reduced", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("cash_refunded", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                (
                    "refund_method",
                    models.CharField(
                        choices=[("cash", "Cash"), ("card", "Card"), ("bank", "Bank"), ("wallet", "Wallet")],
                        default="cash",
                        max_length=12,
                    ),
                ),
                ("reason", models.CharField(blank=True, max_length=255)),
                (
                    "branch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="pos_sale_returns",
                        to="businesses.branch",
                    ),
                ),
                (
                    "business",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pos_sale_returns",
                        to="businesses.business",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="pos_sale_returns",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "sale",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="returns",
                        to="pos.sale",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "unique_together": {("business", "number")},
            },
        ),
        migrations.CreateModel(
            name="SaleReturnLine",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=14)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                (
                    "business",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pos_sale_return_lines",
                        to="businesses.business",
                    ),
                ),
                (
                    "sale_line",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="return_lines",
                        to="pos.saleline",
                    ),
                ),
                (
                    "sale_return",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lines",
                        to="pos.salereturn",
                    ),
                ),
                (
                    "variant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="pos_sale_return_lines",
                        to="catalog.productvariant",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
        migrations.RunPython(backfill_net_total, migrations.RunPython.noop),
    ]
