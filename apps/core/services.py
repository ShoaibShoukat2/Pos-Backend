from apps.accounts.models import Permission, Role
from apps.businesses.models import Branch, Currency, InvoiceSettings, TaxRate
from apps.core.catalog import PERMISSION_CATALOG, ROLE_TEMPLATES

DEFAULT_UNITS = (
    ("Piece", "pcs"),
    ("Kilogram", "kg"),
    ("Gram", "g"),
    ("Litre", "ltr"),
    ("Meter", "m"),
    ("Job", "job"),
)

ELECTRONICS_PRODUCT_CATEGORIES = (
    "Mobiles",
    "Laptops & PCs",
    "Accessories",
    "Home appliances",
    "Spare parts",
)

ELECTRONICS_SERVICE_CATEGORIES = (
    "Repair",
    "Installation",
    "Diagnosis",
    "Software & data",
    "Maintenance",
)

ELECTRONICS_SERVICES = (
    {
        "name": "Mobile screen replacement",
        "category": "Repair",
        "sku": "SVC-SCRN",
        "cost_price": "1800.00",
        "selling_price": "4500.00",
        "duration_minutes": 60,
        "warranty_days": 90,
        "description": "LCD or touch replacement. Extra parts billed separately if not included.",
    },
    {
        "name": "Charging port repair",
        "category": "Repair",
        "sku": "SVC-CHRG",
        "cost_price": "400.00",
        "selling_price": "1500.00",
        "duration_minutes": 45,
        "warranty_days": 30,
        "description": "Port replacement and solder work.",
    },
    {
        "name": "Laptop diagnosis",
        "category": "Diagnosis",
        "sku": "SVC-LDIAG",
        "cost_price": "0.00",
        "selling_price": "800.00",
        "duration_minutes": 30,
        "warranty_days": 0,
        "description": "Hardware and software check. Fee can be waived if a repair is booked.",
    },
    {
        "name": "Software installation",
        "category": "Software & data",
        "sku": "SVC-SOFT",
        "cost_price": "0.00",
        "selling_price": "1200.00",
        "duration_minutes": 45,
        "warranty_days": 7,
        "description": "OS or licensed software install.",
    },
    {
        "name": "Data backup / recovery",
        "category": "Software & data",
        "sku": "SVC-DATA",
        "cost_price": "500.00",
        "selling_price": "2500.00",
        "duration_minutes": 90,
        "warranty_days": 0,
        "description": "Backup or recovery attempt. No data recovery guarantee.",
    },
    {
        "name": "CCTV installation (per camera)",
        "category": "Installation",
        "sku": "SVC-CCTV",
        "cost_price": "800.00",
        "selling_price": "2500.00",
        "duration_minutes": 60,
        "warranty_days": 90,
        "description": "Mounting, cabling and app setup per camera.",
    },
    {
        "name": "Home appliance repair visit",
        "category": "Repair",
        "sku": "SVC-APPL",
        "cost_price": "300.00",
        "selling_price": "1500.00",
        "duration_minutes": 60,
        "warranty_days": 15,
        "description": "On-site visit. Parts extra.",
    },
    {
        "name": "Preventive maintenance",
        "category": "Maintenance",
        "sku": "SVC-MAINT",
        "cost_price": "200.00",
        "selling_price": "1000.00",
        "duration_minutes": 40,
        "warranty_days": 30,
        "description": "Cleaning, thermal paste and health check.",
    },
)

DEFAULT_EXPENSE_CATEGORIES = (
    "Rent",
    "Electricity",
    "Internet",
    "Salaries",
    "Transportation",
    "Maintenance",
)


def ensure_permission_rows() -> dict[str, Permission]:
    existing = {p.codename: p for p in Permission.objects.all()}
    to_create = []
    for item in PERMISSION_CATALOG:
        if item.codename in existing:
            continue
        to_create.append(
            Permission(
                codename=item.codename,
                name=item.name,
                module=item.module,
                module_label=item.module_label,
            )
        )
    if to_create:
        Permission.objects.bulk_create(to_create)
        existing = {p.codename: p for p in Permission.objects.all()}
    return existing


def seed_business_defaults(business, owner, *, branch_name="Head Office"):
    permissions = ensure_permission_rows()

    roles_by_name = {}
    for role_name, codes in ROLE_TEMPLATES.items():
        role, _ = Role.objects.get_or_create(
            business=business,
            name=role_name,
            defaults={"is_system": True, "description": f"Default {role_name} role"},
        )
        role.permissions.set([permissions[c] for c in codes if c in permissions])
        roles_by_name[role_name] = role

    branch, _ = Branch.objects.get_or_create(
        business=business,
        code="HO",
        defaults={
            "name": branch_name,
            "city": business.city,
            "address": business.address,
            "phone": business.phone,
            "is_head_office": True,
        },
    )

    Currency.objects.get_or_create(
        business=business,
        code="PKR",
        defaults={
            "name": "Pakistani Rupee",
            "symbol": "Rs",
            "is_base": True,
            "exchange_rate": 1,
        },
    )

    TaxRate.objects.get_or_create(
        business=business,
        code="GST",
        defaults={"name": "GST", "rate": 18, "is_default": True},
    )

    InvoiceSettings.objects.get_or_create(business=business)
    seed_units(business)
    seed_expense_categories(business)
    seed_loyalty(business)
    if business.business_type == "electronics":
        seed_electronics_catalog(business)

    owner.business = business
    owner.role = roles_by_name.get("Admin")
    owner.default_branch = branch
    owner.is_owner = True
    owner.save(update_fields=["business", "role", "default_branch", "is_owner"])
    owner.branches.add(branch)
    return branch


def seed_units(business):
    from apps.catalog.models import Unit

    for name, code in DEFAULT_UNITS:
        Unit.objects.get_or_create(
            business=business,
            short_code=code,
            defaults={"name": name},
        )


def seed_expense_categories(business):
    from apps.finance.models import ExpenseCategory

    for name in DEFAULT_EXPENSE_CATEGORIES:
        ExpenseCategory.objects.get_or_create(
            business=business,
            name=name,
            defaults={"is_system": True},
        )


def seed_electronics_catalog(business) -> int:
    from apps.businesses.models import TaxRate
    from apps.catalog.models import Category, Product, ProductVariant, Unit

    seed_units(business)
    unit = Unit.objects.filter(business=business, short_code="job").first() or Unit.objects.filter(business=business).first()
    if not unit:
        return 0
    tax = TaxRate.objects.filter(business=business, is_default=True).first()

    for name in ELECTRONICS_PRODUCT_CATEGORIES:
        Category.objects.get_or_create(
            business=business,
            name=name,
            defaults={"kind": Category.Kind.PRODUCT},
        )
    for name in ELECTRONICS_SERVICE_CATEGORIES:
        Category.objects.get_or_create(
            business=business,
            name=name,
            defaults={"kind": Category.Kind.SERVICE},
        )

    created = 0
    for row in ELECTRONICS_SERVICES:
        if Product.objects.filter(business=business, sku=row["sku"]).exists():
            continue
        category = Category.objects.filter(business=business, name=row["category"]).first()
        product = Product.objects.create(
            business=business,
            name=row["name"],
            description=row["description"],
            category=category,
            unit=unit,
            tax_rate=tax,
            sku=row["sku"],
            cost_price=row["cost_price"],
            selling_price=row["selling_price"],
            item_kind=Product.ItemKind.SERVICE,
            track_stock=False,
            has_variants=False,
            duration_minutes=row["duration_minutes"],
            warranty_days=row["warranty_days"],
        )
        ProductVariant.objects.create(
            business=business,
            product=product,
            name=product.name,
            sku=product.sku,
            cost_price=product.cost_price,
            selling_price=product.selling_price,
            is_default=True,
        )
        created += 1
    return created


def seed_loyalty(business):
    from apps.promotions.models import LoyaltySettings, MembershipTier

    LoyaltySettings.objects.get_or_create(business=business)
    for name, points, percent in (
        ("Silver", 0, 0),
        ("Gold", 500, 5),
        ("Platinum", 2000, 10),
    ):
        MembershipTier.objects.get_or_create(
            business=business,
            name=name,
            defaults={"min_points": points, "discount_percent": percent},
        )
