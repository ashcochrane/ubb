from django.contrib import admin

from apps.metering.pricing.models import TenantMarkup


@admin.register(TenantMarkup)
class TenantMarkupAdmin(admin.ModelAdmin):
    list_display = (
        "tenant",
        "event_type",
        "provider",
        "markup_percentage_micros",
        "fixed_uplift_micros",
        "valid_from",
        "valid_to",
    )
    list_filter = ("event_type", "provider")
    search_fields = ("tenant__name", "event_type", "provider")
