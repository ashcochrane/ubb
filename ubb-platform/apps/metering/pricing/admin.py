from django.contrib import admin

from apps.metering.pricing.models import ProviderRate, TenantMarkup


@admin.register(ProviderRate)
class ProviderRateAdmin(admin.ModelAdmin):
    list_display = (
        "provider",
        "event_type",
        "metric_name",
        "cost_per_unit_micros",
        "unit_quantity",
        "currency",
        "valid_from",
        "valid_to",
    )
    list_filter = ("provider", "event_type", "currency")
    search_fields = ("provider", "event_type", "metric_name")


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
