"""
Permission catalog for all 20 POS modules.

Only Modules 1–2 are enforced in the API today. Remaining codes exist so
roles, the frontend, and later modules share one source of truth.
"""

from collections import namedtuple

PermissionDef = namedtuple("PermissionDef", ["codename", "name", "module", "module_label"])

PERMISSION_CATALOG: list[PermissionDef] = [
    # 1. Business & Setup
    PermissionDef("business.view", "View business profile", "business", "Business & Setup"),
    PermissionDef("business.edit", "Edit business profile", "business", "Business & Setup"),
    PermissionDef("branch.view", "View branches", "business", "Business & Setup"),
    PermissionDef("branch.create", "Create branches", "business", "Business & Setup"),
    PermissionDef("branch.edit", "Edit branches", "business", "Business & Setup"),
    PermissionDef("branch.delete", "Delete branches", "business", "Business & Setup"),
    PermissionDef("tax.manage", "Manage tax rates", "business", "Business & Setup"),
    PermissionDef("currency.manage", "Manage currencies", "business", "Business & Setup"),
    PermissionDef("invoice_settings.manage", "Manage invoice settings", "business", "Business & Setup"),
    # 2. Users & Roles
    PermissionDef("user.view", "View users", "users", "Users & Roles"),
    PermissionDef("user.create", "Create users", "users", "Users & Roles"),
    PermissionDef("user.edit", "Edit users", "users", "Users & Roles"),
    PermissionDef("user.delete", "Delete users", "users", "Users & Roles"),
    PermissionDef("role.view", "View roles", "users", "Users & Roles"),
    PermissionDef("role.manage", "Manage roles and permissions", "users", "Users & Roles"),
    # 3. Products & Inventory (reserved)
    PermissionDef("product.view", "View products", "products", "Products & Inventory"),
    PermissionDef("product.manage", "Manage products", "products", "Products & Inventory"),
    PermissionDef("category.manage", "Manage categories", "products", "Products & Inventory"),
    PermissionDef("brand.manage", "Manage brands", "products", "Products & Inventory"),
    # 4. POS / Sales
    PermissionDef("pos.access", "Access POS terminal", "pos", "POS / Sales"),
    PermissionDef("sale.create", "Create sales", "pos", "POS / Sales"),
    PermissionDef("sale.view", "View sales", "pos", "POS / Sales"),
    PermissionDef("sale.hold", "Hold and resume sales", "pos", "POS / Sales"),
    PermissionDef("sale.discount", "Apply sale discounts", "pos", "POS / Sales"),
    # 5. Payments
    PermissionDef("payment.view", "View payments", "payments", "Payments"),
    PermissionDef("payment.create", "Take payments", "payments", "Payments"),
    PermissionDef("payment.refund", "Issue refunds", "payments", "Payments"),
    # 6. Purchases
    PermissionDef("purchase.view", "View purchases", "purchases", "Purchases"),
    PermissionDef("purchase.manage", "Manage purchase orders", "purchases", "Purchases"),
    # 7. Stock
    PermissionDef("stock.view", "View stock", "stock", "Stock Management"),
    PermissionDef("stock.adjust", "Adjust stock", "stock", "Stock Management"),
    PermissionDef("stock.transfer", "Transfer stock", "stock", "Stock Management"),
    PermissionDef("stock.count", "Perform stock counts", "stock", "Stock Management"),
    # 8. Customers
    PermissionDef("customer.view", "View customers", "customers", "Customers"),
    PermissionDef("customer.manage", "Manage customers", "customers", "Customers"),
    PermissionDef("customer.credit", "Manage customer credit", "customers", "Customers"),
    # 9. Suppliers
    PermissionDef("supplier.view", "View suppliers", "suppliers", "Suppliers"),
    PermissionDef("supplier.manage", "Manage suppliers", "suppliers", "Suppliers"),
    # 10. Reports
    PermissionDef("report.sales", "View sales reports", "reports", "Reports & Analytics"),
    PermissionDef("report.profit", "View profit reports", "reports", "Reports & Analytics"),
    PermissionDef("report.inventory", "View inventory reports", "reports", "Reports & Analytics"),
    PermissionDef("report.cashier", "View cashier reports", "reports", "Reports & Analytics"),
    # 11. Expenses
    PermissionDef("expense.view", "View expenses", "expenses", "Expenses"),
    PermissionDef("expense.manage", "Manage expenses", "expenses", "Expenses"),
    # 12. Cash & Accounts
    PermissionDef("cash.drawer", "Open and close cash drawer", "cash", "Cash & Accounts"),
    PermissionDef("cash.reconcile", "Reconcile cash", "cash", "Cash & Accounts"),
    # 13. Returns
    PermissionDef("return.sale", "Process sales returns", "returns", "Returns & Exchanges"),
    PermissionDef("return.purchase", "Process purchase returns", "returns", "Returns & Exchanges"),
    # 14. Notifications
    PermissionDef("notification.view", "View notifications", "notifications", "Notifications"),
    PermissionDef("notification.manage", "Manage notification rules", "notifications", "Notifications"),
    # 15. Settings & Integrations
    PermissionDef("settings.integrations", "Manage integrations", "settings", "Settings & Integrations"),
    PermissionDef("settings.backup", "Run backups", "settings", "Settings & Integrations"),
    # 16. Multi-Branch
    PermissionDef("branch.reports", "View branch reports", "multi_branch", "Multi-Branch"),
    # 17. Accounting
    PermissionDef("ledger.view", "View ledgers", "accounting", "Accounting / Ledger"),
    PermissionDef("ledger.manage", "Manage accounting", "accounting", "Accounting / Ledger"),
    # 18. Discounts & Loyalty
    PermissionDef("discount.manage", "Manage discounts", "loyalty", "Discounts & Loyalty"),
    PermissionDef("loyalty.manage", "Manage loyalty programs", "loyalty", "Discounts & Loyalty"),
    # 19. Offline & Sync
    PermissionDef("sync.manage", "Manage offline sync", "sync", "Offline & Sync"),
    # 20. Business Type
    PermissionDef("business_type.configure", "Configure business type", "business_type", "Business Type"),
]


def permissions_by_module() -> dict[str, list[PermissionDef]]:
    grouped: dict[str, list[PermissionDef]] = {}
    for item in PERMISSION_CATALOG:
        grouped.setdefault(item.module, []).append(item)
    return grouped


# System role templates used during onboarding.
ROLE_TEMPLATES: dict[str, list[str]] = {
    "Admin": [p.codename for p in PERMISSION_CATALOG],
    "Manager": [
        "business.view",
        "branch.view",
        "tax.manage",
        "currency.manage",
        "user.view",
        "product.view",
        "product.manage",
        "category.manage",
        "brand.manage",
        "pos.access",
        "sale.create",
        "sale.view",
        "sale.hold",
        "sale.discount",
        "payment.view",
        "payment.create",
        "payment.refund",
        "purchase.view",
        "purchase.manage",
        "stock.view",
        "stock.adjust",
        "stock.transfer",
        "stock.count",
        "customer.view",
        "customer.manage",
        "customer.credit",
        "supplier.view",
        "supplier.manage",
        "report.sales",
        "report.profit",
        "report.inventory",
        "report.cashier",
        "expense.view",
        "expense.manage",
        "cash.drawer",
        "return.sale",
        "return.purchase",
        "notification.view",
        "discount.manage",
        "loyalty.manage",
    ],
    "Cashier": [
        "pos.access",
        "sale.create",
        "sale.view",
        "sale.hold",
        "payment.create",
        "customer.view",
        "product.view",
        "cash.drawer",
        "return.sale",
        "notification.view",
    ],
    "Accountant": [
        "business.view",
        "sale.view",
        "payment.view",
        "payment.refund",
        "purchase.view",
        "customer.view",
        "customer.credit",
        "supplier.view",
        "report.sales",
        "report.profit",
        "report.cashier",
        "expense.view",
        "expense.manage",
        "cash.reconcile",
        "ledger.view",
        "ledger.manage",
        "invoice_settings.manage",
    ],
}
