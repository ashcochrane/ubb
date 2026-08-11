from django.contrib import admin

from apps.metering.usage.models import Posting


@admin.register(Posting)
class PostingAdmin(admin.ModelAdmin):
    list_display = (
        "request_id",
        "tenant",
        "customer",
        "provider_cost_micros",
        "billed_cost_micros",
        "effective_at",
    )
    list_filter = ("tenant",)
    search_fields = ("request_id", "idempotency_key")
