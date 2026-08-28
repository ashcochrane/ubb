from django.contrib import admin

from apps.metering.usage.models import Posting


@admin.register(Posting)
class PostingAdmin(admin.ModelAdmin):
    # The supplier cost is listed with the status that says how to read it
    # (#328). The amount is NULL both where UBB has not resolved a cost and
    # where the Event Type declares none, and an operator looking at a blank
    # cell cannot tell those apart — which is the whole distinction this slice
    # put in the database.
    list_display = (
        "idempotency_key",
        "tenant",
        "customer",
        "provider_cost_micros",
        "costing_status",
        "billed_cost_micros",
        "effective_at",
    )
    list_filter = ("tenant", "costing_status")
    search_fields = ("idempotency_key",)
