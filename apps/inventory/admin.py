from django.contrib import admin

from apps.inventory.models import StockLevel, StockMovement, StockOperation, StockTransfer


@admin.register(StockLevel)
class StockLevelAdmin(admin.ModelAdmin):
    list_display = ("variant", "branch", "quantity")


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("created_at", "movement_type", "variant", "branch", "quantity", "balance_after")


@admin.register(StockOperation)
class StockOperationAdmin(admin.ModelAdmin):
    list_display = ("number", "kind", "branch", "status")


@admin.register(StockTransfer)
class StockTransferAdmin(admin.ModelAdmin):
    list_display = ("number", "from_branch", "to_branch", "status")
