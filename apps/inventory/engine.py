"""
Single write path for on-hand stock.

Rules:
- Never update StockLevel outside this module.
- Every change inserts an append-only StockMovement.
- Quantity on the ledger is signed: purchase/return/in = +, sale/damage/out = −.
- Transfers lock both branch rows in a stable order to avoid deadlocks.
- Sale / sale_return are implemented here so POS can call them later.
"""

from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.inventory.models import (
    INBOUND_TYPES,
    OUTBOUND_TYPES,
    MovementType,
    StockLevel,
    StockMovement,
)

ZERO = Decimal("0")


def signed_delta(movement_type: str, quantity: Decimal, *, current=None, counted=None) -> Decimal:
    qty = Decimal(quantity)
    if movement_type == MovementType.COUNT:
        if counted is None or current is None:
            raise ValidationError("Stock count requires current and counted quantities.")
        return Decimal(counted) - Decimal(current)
    if movement_type == MovementType.ADJUSTMENT:
        if qty == ZERO:
            raise ValidationError("Adjustment quantity cannot be zero.")
        return qty
    if qty <= ZERO:
        raise ValidationError("Quantity must be greater than zero.")
    if movement_type in INBOUND_TYPES:
        return qty
    if movement_type in OUTBOUND_TYPES:
        return -qty
    raise ValidationError(f"Unknown movement type: {movement_type}")


def _lock_level(variant, branch):
    level, _ = StockLevel.objects.select_for_update().get_or_create(
        business=variant.business,
        variant=variant,
        branch=branch,
        defaults={"quantity": ZERO},
    )
    return level


@transaction.atomic
def apply_movement(
    *,
    variant,
    branch,
    movement_type: str,
    quantity: Decimal,
    user=None,
    reason: str = "",
    reference_type: str = "",
    reference_id=None,
    idempotency_key: str | None = None,
    counted_quantity=None,
    allow_negative: bool = False,
) -> StockMovement:
    if not variant.product.track_stock:
        raise ValidationError(f"{variant.display_name} is not a stock-tracked item.")
    if variant.business_id != branch.business_id:
        raise ValidationError("Variant and branch belong to different businesses.")
    if idempotency_key:
        existing = StockMovement.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing

    level = _lock_level(variant, branch)
    delta = signed_delta(
        movement_type,
        quantity,
        current=level.quantity,
        counted=counted_quantity,
    )
    if delta == ZERO:
        raise ValidationError("Movement would not change stock.")

    new_qty = level.quantity + delta
    if new_qty < ZERO and not allow_negative:
        raise ValidationError(
            f"Insufficient stock for {variant.display_name} at {branch.name}. "
            f"On hand {level.quantity}, change {delta}."
        )

    movement = StockMovement.objects.create(
        business=variant.business,
        variant=variant,
        branch=branch,
        movement_type=movement_type,
        quantity=delta,
        balance_after=new_qty,
        reason=reason,
        reference_type=reference_type,
        reference_id=reference_id,
        idempotency_key=idempotency_key,
        created_by=user,
    )
    level.quantity = new_qty
    level.save(update_fields=["quantity", "updated_at"])
    return movement


@transaction.atomic
def apply_transfer(*, variant, from_branch, to_branch, quantity, user=None, reason="", reference_id=None):
    if from_branch.pk == to_branch.pk:
        raise ValidationError("Cannot transfer to the same branch.")
    qty = Decimal(quantity)
    if qty <= ZERO:
        raise ValidationError("Transfer quantity must be greater than zero.")

    # Lock both levels in a stable order.
    first, second = sorted(
        [(from_branch.pk, from_branch), (to_branch.pk, to_branch)],
        key=lambda item: str(item[0]),
    )
    _lock_level(variant, first[1])
    _lock_level(variant, second[1])

    out_move = apply_movement(
        variant=variant,
        branch=from_branch,
        movement_type=MovementType.TRANSFER_OUT,
        quantity=qty,
        user=user,
        reason=reason,
        reference_type="stock_transfer",
        reference_id=reference_id,
        idempotency_key=f"transfer-out:{reference_id}:{variant.pk}" if reference_id else None,
    )
    in_move = apply_movement(
        variant=variant,
        branch=to_branch,
        movement_type=MovementType.TRANSFER_IN,
        quantity=qty,
        user=user,
        reason=reason,
        reference_type="stock_transfer",
        reference_id=reference_id,
        idempotency_key=f"transfer-in:{reference_id}:{variant.pk}" if reference_id else None,
    )
    return out_move, in_move


def record_sale(*, variant, branch, quantity, user=None, reference_id=None, reason="Sale"):
    return apply_movement(
        variant=variant,
        branch=branch,
        movement_type=MovementType.SALE,
        quantity=quantity,
        user=user,
        reason=reason,
        reference_type="sale",
        reference_id=reference_id,
    )


def record_sale_return(*, variant, branch, quantity, user=None, reference_id=None, reason="Sale return"):
    return apply_movement(
        variant=variant,
        branch=branch,
        movement_type=MovementType.SALE_RETURN,
        quantity=quantity,
        user=user,
        reason=reason,
        reference_type="sale_return",
        reference_id=reference_id,
    )


def on_hand(variant, branch) -> Decimal:
    level = StockLevel.objects.filter(variant=variant, branch=branch).first()
    return level.quantity if level else ZERO
