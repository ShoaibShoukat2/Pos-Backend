from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Abs, TruncDate, TruncMonth, TruncWeek
from django.utils import timezone

from apps.customers.models import Customer, CustomerSale
from apps.finance.models import Expense
from apps.inventory.models import MovementType, StockLevel, StockMovement
from apps.pos.models import OPEN_SALE_STATUSES, Sale, SaleLine
from apps.purchases.models import SupplierPayable

ZERO = Decimal("0")
MONEY = DecimalField(max_digits=18, decimal_places=2)
REPORT_ROW_CAP = 50


def money(value) -> str:
    if value is None:
        return "0.00"
    return f"{Decimal(value):.2f}"


def _scope(qs, branch_ids, field="branch_id"):
    if branch_ids is None:
        return qs
    return qs.filter(**{f"{field}__in": branch_ids})


def _pos_sales(business, start, end, branch_ids=None):
    return _scope(
        Sale.objects.filter(
            business=business,
            status__in=OPEN_SALE_STATUSES,
            created_at__gte=start,
            created_at__lte=end,
        ),
        branch_ids,
    )


def _legacy_sales(business, start, end, branch_ids=None):
    return _scope(
        CustomerSale.objects.filter(
            business=business,
            created_at__gte=start,
            created_at__lte=end,
            pos_sale__isnull=True,
        ),
        branch_ids,
    )


def _sale_movements(business, start, end, branch_ids=None):
    return _scope(
        StockMovement.objects.filter(
            business=business,
            movement_type__in=[MovementType.SALE, MovementType.SALE_RETURN],
            created_at__gte=start,
            created_at__lte=end,
        ).select_related("variant__product__category"),
        branch_ids,
    )


def cogs_for(business, start, end, branch_ids=None) -> Decimal:
    sold = ZERO
    returned = ZERO
    for row in (
        _sale_movements(business, start, end, branch_ids)
        .values("movement_type")
        .annotate(total=Sum(ExpressionWrapper(Abs(F("quantity")) * F("variant__cost_price"), output_field=MONEY)))
    ):
        if row["movement_type"] == MovementType.SALE_RETURN:
            returned += row["total"] or ZERO
        else:
            sold += row["total"] or ZERO
    services = (
        SaleLine.objects.filter(
            sale__in=_pos_sales(business, start, end, branch_ids),
            variant__product__item_kind="service",
        ).aggregate(
            total=Sum(
                ExpressionWrapper(
                    (F("quantity") - F("returned_qty")) * F("variant__cost_price"),
                    output_field=MONEY,
                )
            )
        )["total"]
        or ZERO
    )
    return sold - returned + services


def revenue_for(business, start, end, branch_ids=None) -> Decimal:
    pos = _pos_sales(business, start, end, branch_ids).aggregate(total=Sum("net_total"))["total"] or ZERO
    legacy = _legacy_sales(business, start, end, branch_ids).aggregate(total=Sum("total"))["total"] or ZERO
    return pos + legacy


def expenses_for(business, start, end, branch_ids=None) -> Decimal:
    return (
        _scope(
            Expense.objects.filter(business=business, created_at__gte=start, created_at__lte=end),
            branch_ids,
        ).aggregate(total=Sum("amount"))["total"]
        or ZERO
    )


def _trunc(kind):
    tz = timezone.get_current_timezone()
    if kind == "daily":
        return TruncDate("created_at", tzinfo=tz)
    if kind == "weekly":
        return TruncWeek("created_at", tzinfo=tz)
    return TruncMonth("created_at", tzinfo=tz)


def _series_from_qs(querysets, kind, amount_field="total"):
    buckets = defaultdict(lambda: {"total": ZERO, "orders": 0})
    trunc = _trunc(kind)
    for qs in querysets:
        field = "net_total" if getattr(qs.model, "__name__", "") == "Sale" else amount_field
        for row in qs.annotate(bucket=trunc).values("bucket").annotate(total=Sum(field), orders=Count("id")):
            if not row["bucket"]:
                continue
            key = row["bucket"].date() if hasattr(row["bucket"], "date") else row["bucket"]
            buckets[key]["total"] += row["total"] or ZERO
            buckets[key]["orders"] += row["orders"] or 0
    return [
        {"date": key.isoformat(), "total": money(val["total"]), "orders": val["orders"]}
        for key, val in sorted(buckets.items())
    ]


def _order_stats(business, start, end, branch_ids=None):
    pos = _pos_sales(business, start, end, branch_ids).aggregate(total=Sum("net_total"), orders=Count("id"))
    legacy = _legacy_sales(business, start, end, branch_ids).aggregate(total=Sum("total"), orders=Count("id"))
    return (pos["total"] or ZERO) + (legacy["total"] or ZERO), (pos["orders"] or 0) + (legacy["orders"] or 0)


def _payables_total(business) -> Decimal:
    return (
        SupplierPayable.objects.filter(business=business)
        .exclude(status="paid")
        .aggregate(total=Sum(ExpressionWrapper(F("amount") - F("paid_amount"), output_field=MONEY)))["total"]
        or ZERO
    )


def dashboard(business, start, end, period: str, branch_ids=None) -> dict:
    revenue, orders = _order_stats(business, start, end, branch_ids)
    cost = cogs_for(business, start, end, branch_ids)
    expenses = expenses_for(business, start, end, branch_ids)
    gross = revenue - cost
    net = gross - expenses
    levels = _scope(
        StockLevel.objects.filter(
            business=business,
            variant__product__item_kind="product",
            variant__product__track_stock=True,
        ),
        branch_ids,
    )
    low = levels.filter(quantity__lt=F("variant__min_stock")).count()
    receivables = Customer.objects.filter(business=business, is_active=True).aggregate(
        total=Sum("receivable_balance")
    )["total"] or ZERO
    return {
        "period": period,
        "from": timezone.localtime(start).date().isoformat(),
        "to": timezone.localtime(end).date().isoformat(),
        "today_sales": money(revenue),
        "today_profit": money(net),
        "gross_profit": money(gross),
        "orders": orders,
        "customers": Customer.objects.filter(business=business, is_active=True).count(),
        "low_stock": low,
        "outstanding": money(receivables),
        "payables": money(_payables_total(business)),
        "expenses": money(expenses),
        "revenue": money(revenue),
        "cost": money(cost),
    }


def sales_report(business, start, end, period: str, branch_ids=None) -> dict:
    pos_qs = _pos_sales(business, start, end, branch_ids)
    legacy_qs = _legacy_sales(business, start, end, branch_ids)
    revenue, orders = _order_stats(business, start, end, branch_ids)

    cashiers = defaultdict(lambda: {"name": "Unassigned", "total": ZERO, "orders": 0})
    cashier_rows = list(
        pos_qs.values("created_by_id", "created_by__first_name", "created_by__last_name").annotate(
            total=Sum("net_total"), orders=Count("id")
        )
    ) + list(
        legacy_qs.values("created_by_id", "created_by__first_name", "created_by__last_name").annotate(
            total=Sum("total"), orders=Count("id")
        )
    )
    for row in cashier_rows:
        key = str(row["created_by_id"] or "none")
        name = " ".join(filter(None, [row.get("created_by__first_name"), row.get("created_by__last_name")])).strip()
        cashiers[key]["name"] = name or "Unassigned"
        cashiers[key]["total"] += row["total"] or ZERO
        cashiers[key]["orders"] += row["orders"] or 0

    product_rows = defaultdict(
        lambda: {"product": "", "category": "Uncategorized", "qty": ZERO, "revenue": ZERO}
    )
    line_rows = (
        SaleLine.objects.filter(sale__in=pos_qs, variant__product__item_kind="product")
        .values("variant__product_id", "variant__product__name", "variant__product__category__name")
        .annotate(qty=Sum(F("quantity") - F("returned_qty")), revenue=Sum(F("line_total") - F("returned_amount")))
        .order_by("-revenue")[:REPORT_ROW_CAP]
    )
    for row in line_rows:
        key = str(row["variant__product_id"])
        product_rows[key]["product"] = row["variant__product__name"]
        product_rows[key]["category"] = row["variant__product__category__name"] or "Uncategorized"
        product_rows[key]["qty"] += row["qty"] or ZERO
        product_rows[key]["revenue"] += row["revenue"] or ZERO

    if not product_rows:
        move_rows = (
            _sale_movements(business, start, end, branch_ids)
            .values("variant__product_id", "variant__product__name", "variant__product__category__name")
            .annotate(
                qty=Sum(Abs(F("quantity"))),
                revenue=Sum(
                    ExpressionWrapper(Abs(F("quantity")) * F("variant__selling_price"), output_field=MONEY)
                ),
            )
            .order_by("-revenue")[:REPORT_ROW_CAP]
        )
        for row in move_rows:
            key = str(row["variant__product_id"])
            product_rows[key]["product"] = row["variant__product__name"]
            product_rows[key]["category"] = row["variant__product__category__name"] or "Uncategorized"
            product_rows[key]["qty"] += row["qty"] or ZERO
            product_rows[key]["revenue"] += row["revenue"] or ZERO

    category_rows = defaultdict(lambda: {"category": "", "qty": ZERO, "revenue": ZERO})
    for row in product_rows.values():
        cat = row["category"]
        category_rows[cat]["category"] = cat
        category_rows[cat]["qty"] += row["qty"]
        category_rows[cat]["revenue"] += row["revenue"]

    return {
        "period": period,
        "from": timezone.localtime(start).date().isoformat(),
        "to": timezone.localtime(end).date().isoformat(),
        "totals": {"revenue": money(revenue), "orders": orders},
        "daily": _series_from_qs([pos_qs, legacy_qs], "daily"),
        "weekly": _series_from_qs([pos_qs, legacy_qs], "weekly"),
        "monthly": _series_from_qs([pos_qs, legacy_qs], "monthly"),
        "cashiers": [
            {"name": row["name"], "total": money(row["total"]), "orders": row["orders"]}
            for row in sorted(cashiers.values(), key=lambda r: r["total"], reverse=True)[:REPORT_ROW_CAP]
        ],
        "products": [
            {
                "product": row["product"],
                "category": row["category"],
                "qty": f"{row['qty']:.3f}",
                "revenue": money(row["revenue"]),
            }
            for row in sorted(product_rows.values(), key=lambda r: r["revenue"], reverse=True)[:REPORT_ROW_CAP]
        ],
        "categories": [
            {"category": row["category"], "qty": f"{row['qty']:.3f}", "revenue": money(row["revenue"])}
            for row in sorted(category_rows.values(), key=lambda r: r["revenue"], reverse=True)[:REPORT_ROW_CAP]
        ],
    }


def _stock_item(row):
    value = row.quantity * row.variant.cost_price
    return {
        "product": row.variant.product.name,
        "variant": row.variant.display_name,
        "sku": row.variant.sku,
        "branch": row.branch.name,
        "qty": f"{row.quantity:.3f}",
        "cost": money(row.variant.cost_price),
        "value": money(value),
        "min_stock": f"{row.variant.min_stock:.3f}",
        "is_low": row.quantity < row.variant.min_stock,
    }


def inventory_report(business, start, end, branch_ids=None) -> dict:
    levels = _scope(
        StockLevel.objects.filter(
            business=business,
            variant__product__item_kind="product",
            variant__product__track_stock=True,
        ),
        branch_ids,
    )
    stats = levels.aggregate(
        valuation=Sum(ExpressionWrapper(F("quantity") * F("variant__cost_price"), output_field=MONEY)),
        sku_locations=Count("id"),
        low_count=Count("id", filter=Q(quantity__lt=F("variant__min_stock"))),
    )
    preview = list(
        levels.select_related("variant__product", "branch").order_by("-quantity")[:REPORT_ROW_CAP]
    )
    low_qs = (
        levels.filter(quantity__lt=F("variant__min_stock"))
        .select_related("variant__product", "branch")
        .order_by("quantity")[:REPORT_ROW_CAP]
    )

    sold_rows = list(
        _sale_movements(business, start, end, branch_ids)
        .values("variant__product_id", "variant__product__name")
        .annotate(sold=Sum(Abs(F("quantity"))))
        .order_by("-sold")[:10]
    )
    sold_ids = [row["variant__product_id"] for row in sold_rows]
    on_hand_map = {
        row["variant__product_id"]: row["on_hand"] or ZERO
        for row in levels.filter(variant__product_id__in=sold_ids)
        .values("variant__product_id")
        .annotate(on_hand=Sum("quantity"))
    } if sold_ids else {}
    fast = [
        {
            "product": row["variant__product__name"],
            "on_hand": on_hand_map.get(row["variant__product_id"], ZERO),
            "sold": row["sold"] or ZERO,
        }
        for row in sold_rows
    ]
    sold_id_set = set(sold_ids)
    slow_qs = (
        levels.values("variant__product_id", "variant__product__name")
        .annotate(on_hand=Sum("quantity"))
        .filter(on_hand__gt=0)
        .order_by("-on_hand")[:40]
    )
    slow = [
        {"product": row["variant__product__name"], "on_hand": row["on_hand"] or ZERO, "sold": ZERO}
        for row in slow_qs
        if row["variant__product_id"] not in sold_id_set
    ][:10]

    def product_row(row):
        return {
            "product": row["product"],
            "on_hand": f"{row['on_hand']:.3f}",
            "sold": f"{row['sold']:.3f}",
        }

    return {
        "from": timezone.localtime(start).date().isoformat(),
        "to": timezone.localtime(end).date().isoformat(),
        "valuation": money(stats["valuation"]),
        "sku_locations": stats["sku_locations"] or 0,
        "low_count": stats["low_count"] or 0,
        "current": [_stock_item(row) for row in preview],
        "low_stock": [_stock_item(row) for row in low_qs],
        "fast_moving": [product_row(r) for r in fast],
        "slow_moving": [product_row(r) for r in slow],
    }


def financial_report(business, start, end, period: str, branch_ids=None) -> dict:
    revenue = revenue_for(business, start, end, branch_ids)
    cost = cogs_for(business, start, end, branch_ids)
    gross = revenue - cost
    expenses = expenses_for(business, start, end, branch_ids)
    net = gross - expenses
    expense_rows = (
        _scope(
            Expense.objects.filter(business=business, created_at__gte=start, created_at__lte=end),
            branch_ids,
        )
        .values("category__name")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )
    receivables = Customer.objects.filter(business=business, is_active=True).aggregate(
        total=Sum("receivable_balance")
    )["total"] or ZERO
    payables = _payables_total(business)
    return {
        "period": period,
        "from": timezone.localtime(start).date().isoformat(),
        "to": timezone.localtime(end).date().isoformat(),
        "revenue": money(revenue),
        "cost": money(cost),
        "gross_profit": money(gross),
        "expenses": money(expenses),
        "net_profit": money(net),
        "receivables": money(receivables),
        "payables": money(payables),
        "expense_breakdown": [
            {"category": row["category__name"] or "Uncategorized", "total": money(row["total"])}
            for row in expense_rows
        ],
        "cogs_note": "Cost is sold units × current cost price from inventory sale movements posted by the POS.",
    }


def _qty(value) -> str:
    if value is None:
        return "0"
    return f"{Decimal(value):.3f}".rstrip("0").rstrip(".")


def _product_card(product, *, action, detail, at, stock_map, variant=None):
    sku = (variant.sku if variant else None) or getattr(product, "sku", "") or ""
    barcode = (variant.barcode if variant else None) or getattr(product, "barcode", "") or ""
    price = (variant.selling_price if variant else None) or product.selling_price
    cost = (variant.cost_price if variant else None) or product.cost_price
    return {
        "id": str(product.id),
        "name": product.name,
        "sku": sku,
        "barcode": barcode,
        "category": product.category.name if product.category_id else "",
        "selling_price": money(price),
        "cost_price": money(cost),
        "qty": _qty(stock_map.get(product.id, 0)),
        "action": action,
        "detail": detail,
        "at": at.isoformat() if at else "",
    }


def live_board(business, branch_ids=None) -> dict:
    from apps.catalog.models import Product
    from apps.purchases.models import GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine

    stock_map = {
        row["variant__product_id"]: row["qty"]
        for row in _scope(StockLevel.objects.filter(business=business), branch_ids)
        .values("variant__product_id")
        .annotate(qty=Sum("quantity"))
    }

    sale_lines = (
        _scope(
            SaleLine.objects.filter(business=business, sale__status__in=OPEN_SALE_STATUSES),
            branch_ids,
            field="sale__branch_id",
        )
        .select_related("variant", "variant__product", "variant__product__category", "sale")
        .order_by("-created_at")[:30]
    )
    receipt_lines = (
        _scope(
            GoodsReceiptLine.objects.filter(
                receipt__business=business,
                receipt__status=GoodsReceipt.Status.POSTED,
            ),
            branch_ids,
            field="receipt__branch_id",
        )
        .select_related(
            "variant",
            "variant__product",
            "variant__product__category",
            "receipt",
            "receipt__supplier",
        )
        .order_by("-created_at")[:20]
    )
    po_lines = (
        _scope(
            PurchaseOrderLine.objects.filter(
                order__business=business,
            ).exclude(order__status__in=[PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.CANCELLED]),
            branch_ids,
            field="order__branch_id",
        )
        .select_related(
            "variant",
            "variant__product",
            "variant__product__category",
            "order",
            "order__supplier",
        )
        .order_by("-updated_at")[:20]
    )
    catalog = list(
        Product.objects.filter(business=business, is_active=True, item_kind=Product.ItemKind.PRODUCT)
        .select_related("category")
        .prefetch_related("variants")
        .order_by("name")[:80]
    )
    added_products = list(
        Product.objects.filter(business=business, item_kind=Product.ItemKind.PRODUCT)
        .select_related("category")
        .prefetch_related("variants")
        .order_by("-created_at")[:12]
    )
    updated_products = list(
        Product.objects.filter(business=business, item_kind=Product.ItemKind.PRODUCT)
        .select_related("category")
        .prefetch_related("variants")
        .order_by("-updated_at")[:16]
    )

    cards = {}
    activity = []

    def variant_of(product):
        rows = list(product.variants.all())
        return next((row for row in rows if row.is_default), None) or (rows[0] if rows else None)

    priority = {"sold": 4, "purchased": 3, "added": 2, "updated": 1, "catalog": 0}

    def put(card, event):
        current = cards.get(card["id"])
        if (
            not current
            or priority.get(card["action"], 0) > priority.get(current["action"], 0)
            or (
                card["action"] == current["action"]
                and (card["at"] or "") >= (current["at"] or "")
            )
        ):
            cards[card["id"]] = card
        activity.append(event)

    for product in catalog:
        cards[str(product.id)] = _product_card(
            product,
            action="catalog",
            detail="In catalog",
            at=product.updated_at,
            stock_map=stock_map,
            variant=variant_of(product),
        )

    for line in sale_lines:
        product = line.variant.product
        if product.item_kind != Product.ItemKind.PRODUCT:
            continue
        at = line.created_at
        detail = f"{_qty(line.quantity)} sold · {line.sale.number}"
        put(
            _product_card(product, action="sold", detail=detail, at=at, stock_map=stock_map, variant=line.variant),
            {
                "kind": "sold",
                "title": product.name,
                "detail": detail,
                "at": at.isoformat(),
                "href": "/pos",
            },
        )

    for line in receipt_lines:
        product = line.variant.product
        if product.item_kind != Product.ItemKind.PRODUCT:
            continue
        at = line.created_at
        supplier = line.receipt.supplier.name if line.receipt.supplier_id else "Supplier"
        detail = f"{_qty(line.quantity)} received from {supplier}"
        put(
            _product_card(product, action="purchased", detail=detail, at=at, stock_map=stock_map, variant=line.variant),
            {
                "kind": "purchased",
                "title": product.name,
                "detail": detail,
                "at": at.isoformat(),
                "href": "/purchases",
            },
        )

    for line in po_lines:
        product = line.variant.product
        if product.item_kind != Product.ItemKind.PRODUCT:
            continue
        at = line.updated_at or line.created_at
        supplier = line.order.supplier.name if line.order.supplier_id else "Supplier"
        detail = f"{_qty(line.quantity)} on PO {line.order.number} · {supplier}"
        put(
            _product_card(product, action="purchased", detail=detail, at=at, stock_map=stock_map, variant=line.variant),
            {
                "kind": "purchased",
                "title": product.name,
                "detail": detail,
                "at": at.isoformat(),
                "href": "/purchases",
            },
        )

    for product in added_products:
        detail = "New product added to catalog"
        put(
            _product_card(
                product,
                action="added",
                detail=detail,
                at=product.created_at,
                stock_map=stock_map,
                variant=variant_of(product),
            ),
            {
                "kind": "added",
                "title": product.name,
                "detail": detail,
                "at": product.created_at.isoformat(),
                "href": f"/products/{product.id}",
            },
        )

    for product in updated_products:
        if (product.updated_at - product.created_at).total_seconds() < 3:
            continue
        detail = "Product details updated"
        put(
            _product_card(
                product,
                action="updated",
                detail=detail,
                at=product.updated_at,
                stock_map=stock_map,
                variant=variant_of(product),
            ),
            {
                "kind": "updated",
                "title": product.name,
                "detail": detail,
                "at": product.updated_at.isoformat(),
                "href": f"/products/{product.id}",
            },
        )

    moving = [row for row in cards.values() if row["action"] != "catalog"]
    rest = [row for row in cards.values() if row["action"] == "catalog"]
    moving.sort(key=lambda row: row["at"] or "", reverse=True)
    rest.sort(key=lambda row: row["name"].lower())
    live_products = (moving + rest)[:80]
    activity = sorted(activity, key=lambda row: row["at"] or "", reverse=True)[:30]
    counts = {
        "sold": sum(1 for row in moving if row["action"] == "sold"),
        "purchased": sum(1 for row in moving if row["action"] == "purchased"),
        "added": sum(1 for row in moving if row["action"] == "added"),
        "updated": sum(1 for row in moving if row["action"] == "updated"),
        "total": len(moving),
    }
    return {"live_products": live_products, "activity": activity, "live_counts": counts}


def owner_overview(business, start, end, period: str, branch_ids=None) -> dict:
    from apps.accounts.models import User
    from apps.businesses.models import Branch
    from apps.catalog.models import Product, ProductVariant
    from apps.finance.models import CashSession
    from apps.purchases.models import Supplier

    base = dashboard(business, start, end, period, branch_ids)
    levels = _scope(
        StockLevel.objects.filter(
            business=business,
            variant__product__item_kind="product",
            variant__product__track_stock=True,
        ),
        branch_ids,
    )
    stock_value = levels.aggregate(
        total=Sum(ExpressionWrapper(F("quantity") * F("variant__cost_price"), output_field=MONEY))
    )["total"] or ZERO
    users = User.objects.filter(business=business)
    open_shifts = list(
        CashSession.objects.filter(business=business, status=CashSession.Status.OPEN)
        .select_related("branch", "opened_by")
        .order_by("-created_at")[:8]
    )
    recent_sales = list(
        _scope(Sale.objects.filter(business=business, status__in=OPEN_SALE_STATUSES), branch_ids)
        .select_related("customer", "branch", "created_by")
        .order_by("-created_at")[:8]
    )
    top_products = (
        SaleLine.objects.filter(
            sale__in=_pos_sales(business, start, end, branch_ids),
            variant__product__item_kind="product",
        )
        .values("variant__product__name")
        .annotate(qty=Sum(F("quantity") - F("returned_qty")), revenue=Sum(F("line_total") - F("returned_amount")))
        .order_by("-revenue")[:6]
    )
    daily = _series_from_qs(
        [_pos_sales(business, start, end, branch_ids), _legacy_sales(business, start, end, branch_ids)],
        "daily",
    )
    alerts = []
    if base["low_stock"]:
        alerts.append(
            {
                "tone": "warn",
                "title": f"{base['low_stock']} items below minimum stock",
                "detail": "Restock before the next rush.",
                "href": "/stock",
            }
        )
    if not open_shifts:
        alerts.append(
            {
                "tone": "warn",
                "title": "No cash drawer is open",
                "detail": "Open a shift before taking cash sales.",
                "href": "/cash",
            }
        )
    if Decimal(base["outstanding"]) > 0:
        alerts.append(
            {
                "tone": "copper",
                "title": "Customers still owe money",
                "detail": f"Outstanding {money(base['outstanding'])}",
                "href": "/customers",
            }
        )
    if Decimal(base["payables"]) > 0:
        alerts.append(
            {
                "tone": "copper",
                "title": "Supplier bills are unpaid",
                "detail": f"Payables {money(base['payables'])}",
                "href": "/purchases",
            }
        )

    return {
        **base,
        "stock_value": money(stock_value),
        "sku_locations": levels.count(),
        "products": Product.objects.filter(
            business=business, is_active=True, item_kind=Product.ItemKind.PRODUCT
        ).count(),
        "services": Product.objects.filter(
            business=business, is_active=True, item_kind=Product.ItemKind.SERVICE
        ).count(),
        "variants": ProductVariant.objects.filter(
            business=business, is_active=True, product__item_kind=Product.ItemKind.PRODUCT
        ).count(),
        "suppliers": Supplier.objects.filter(business=business, is_active=True).count(),
        "branches": Branch.objects.filter(business=business, is_active=True).count(),
        "users_total": users.count(),
        "users_active": users.filter(is_active=True).count(),
        "daily": daily,
        "top_products": [
            {
                "product": row["variant__product__name"] or "Product",
                "qty": f"{row['qty'] or 0:.3f}",
                "revenue": money(row["revenue"]),
            }
            for row in top_products
        ],
        "recent_sales": [
            {
                "id": str(sale.id),
                "number": sale.number,
                "total": money(sale.net_total),
                "customer_name": sale.customer.name if sale.customer_id else "Walk-in",
                "branch_name": sale.branch.name,
                "cashier_name": sale.created_by.full_name if sale.created_by_id else "—",
                "created_at": sale.created_at.isoformat(),
            }
            for sale in recent_sales
        ],
        "team": [
            {
                "id": str(row.id),
                "name": row.full_name or row.email,
                "email": row.email,
                "role": "Owner" if row.is_owner else (row.role.name if row.role_id else "Staff"),
                "is_active": row.is_active,
                "is_owner": row.is_owner,
            }
            for row in users.select_related("role").order_by("-is_owner", "first_name")[:8]
        ],
        "open_shifts": [
            {
                "id": str(row.id),
                "number": row.number,
                "branch_name": row.branch.name,
                "opened_by": row.opened_by.full_name if row.opened_by_id else "—",
                "expected_cash": money(row.expected_cash),
                "sales_cash": money(row.sales_cash),
            }
            for row in open_shifts
        ],
        "alerts": alerts,
        **live_board(business, branch_ids),
    }
