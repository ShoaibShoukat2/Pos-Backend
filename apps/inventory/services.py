from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.numbering import allocate_number
from apps.inventory.engine import apply_movement, apply_transfer
from apps.inventory.models import (
    MovementType,
    StockOperation,
    StockOperationLine,
    StockTransfer,
    StockTransferLine,
)

KIND_TO_MOVEMENT = {
    StockOperation.Kind.ADJUSTMENT: MovementType.ADJUSTMENT,
    StockOperation.Kind.STOCK_IN: MovementType.STOCK_IN,
    StockOperation.Kind.STOCK_OUT: MovementType.STOCK_OUT,
    StockOperation.Kind.DAMAGE: MovementType.DAMAGE,
    StockOperation.Kind.EXPIRED: MovementType.EXPIRED,
    StockOperation.Kind.COUNT: MovementType.COUNT,
}


@transaction.atomic
def create_and_post_operation(*, business, user, kind, branch, reason="", lines):
    if branch.business_id != business.id:
        raise ValidationError("Branch does not belong to this business.")
    op = StockOperation.objects.create(
        business=business,
        number=allocate_number(business, "STO", "STO"),
        kind=kind,
        branch=branch,
        reason=reason,
        created_by=user,
        status=StockOperation.Status.POSTED,
        posted_at=timezone.now(),
    )
    movement_type = KIND_TO_MOVEMENT[kind]
    for row in lines:
        variant = row["variant"]
        if variant.business_id != business.id:
            raise ValidationError("Variant does not belong to this business.")
        line = StockOperationLine.objects.create(
            operation=op,
            variant=variant,
            quantity=row.get("quantity") or 0,
            counted_quantity=row.get("counted_quantity"),
        )
        apply_movement(
            variant=variant,
            branch=branch,
            movement_type=movement_type,
            quantity=line.quantity,
            counted_quantity=line.counted_quantity,
            user=user,
            reason=reason or op.get_kind_display(),
            reference_type="stock_operation",
            reference_id=op.id,
            idempotency_key=f"sto:{op.id}:{line.id}",
        )
    return op


@transaction.atomic
def create_and_post_transfer(*, business, user, from_branch, to_branch, reason="", lines):
    if from_branch.business_id != business.id or to_branch.business_id != business.id:
        raise ValidationError("Branches must belong to this business.")
    transfer = StockTransfer.objects.create(
        business=business,
        number=allocate_number(business, "TRN", "TRN"),
        from_branch=from_branch,
        to_branch=to_branch,
        reason=reason,
        created_by=user,
        status=StockTransfer.Status.POSTED,
        posted_at=timezone.now(),
    )
    for row in lines:
        variant = row["variant"]
        line = StockTransferLine.objects.create(
            transfer=transfer,
            variant=variant,
            quantity=row["quantity"],
        )
        apply_transfer(
            variant=variant,
            from_branch=from_branch,
            to_branch=to_branch,
            quantity=line.quantity,
            user=user,
            reason=reason or "Branch transfer",
            reference_id=transfer.id,
        )
    return transfer
