from django.contrib import admin

from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.billing.topups.models import AutoTopUpConfig


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("external_id", "tenant", "status", "created_at")
    list_filter = ("status", "tenant")
    search_fields = ("external_id",)


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("customer", "balance_micros", "currency", "updated_at")
    search_fields = ("customer__external_id",)


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "wallet",
        "transaction_type",
        "amount_micros",
        "balance_after_micros",
        "created_at",
    )
    list_filter = ("transaction_type",)


@admin.register(AutoTopUpConfig)
class AutoTopUpConfigAdmin(admin.ModelAdmin):
    list_display = (
        "customer",
        "is_enabled",
        "trigger_threshold_micros",
        "top_up_amount_micros",
    )
    list_filter = ("is_enabled",)
