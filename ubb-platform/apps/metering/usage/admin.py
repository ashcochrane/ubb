from django.contrib import admin

from apps.metering.usage.models import Invoice, UsageEvent


@admin.register(UsageEvent)
class UsageEventAdmin(admin.ModelAdmin):
    list_display = (
        "request_id",
        "tenant",
        "customer",
        "cost_micros",
        "effective_at",
    )
    list_filter = ("tenant",)
    search_fields = ("request_id", "idempotency_key")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "customer",
        "tenant",
        "status",
        "total_amount_micros",
        "finalized_at",
        "paid_at",
    )
    list_filter = ("status", "tenant")
    search_fields = ("stripe_invoice_id",)
