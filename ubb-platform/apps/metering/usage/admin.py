from django.contrib import admin

from apps.metering.usage.models import UsageEvent


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
