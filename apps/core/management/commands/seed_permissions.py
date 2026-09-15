from django.core.management.base import BaseCommand

from apps.businesses.models import Business
from apps.core.catalog import ROLE_TEMPLATES
from apps.core.services import ensure_permission_rows, seed_expense_categories, seed_loyalty, seed_units


class Command(BaseCommand):
    help = "Sync permissions, system roles, units, and expense categories."

    def handle(self, *args, **options):
        from apps.accounts.models import Role
        from apps.purchases.ledger import apply_supplier_ledger
        from apps.purchases.models import SupplierLedgerEntry, SupplierLedgerType, SupplierPayable

        rows = ensure_permission_rows()
        for business in Business.objects.all():
            seed_units(business)
            seed_expense_categories(business)
            seed_loyalty(business)
            for role_name, codes in ROLE_TEMPLATES.items():
                role = Role.objects.filter(business=business, name=role_name, is_system=True).first()
                if role:
                    role.permissions.set([rows[c] for c in codes if c in rows])

        for payable in SupplierPayable.objects.select_related("supplier", "goods_receipt"):
            exists = SupplierLedgerEntry.objects.filter(
                reference_type="goods_receipt",
                reference_id=payable.goods_receipt_id,
            ).exists()
            if exists:
                continue
            apply_supplier_ledger(
                supplier=payable.supplier,
                entry_type=SupplierLedgerType.PURCHASE,
                amount=payable.amount,
                reason=f"Goods received {payable.goods_receipt.number}",
                reference_type="goods_receipt",
                reference_id=payable.goods_receipt_id,
            )

        self.stdout.write(self.style.SUCCESS(f"Synced {len(rows)} permissions and finance defaults."))
