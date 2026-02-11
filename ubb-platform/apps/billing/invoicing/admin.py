from django.contrib import admin

from apps.billing.invoicing.models import Invoice


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("customer", "total_amount_micros", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("customer__external_id", "stripe_invoice_id")
