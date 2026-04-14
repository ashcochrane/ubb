from django.contrib import admin

from apps.metering.pricing.models import Card, Rate, TenantMarkup


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "tenant",
        "provider",
        "event_type",
        "status",
        "dimensions_hash",
        "created_at",
    )
    list_filter = ("provider", "event_type", "status")
    search_fields = ("name", "provider", "event_type", "tenant__name")


@admin.register(Rate)
class RateAdmin(admin.ModelAdmin):
    list_display = (
        "card",
        "metric_name",
        "cost_per_unit_micros",
        "unit_quantity",
        "currency",
        "valid_from",
        "valid_to",
    )
    list_filter = ("metric_name", "currency")
    search_fields = ("metric_name", "card__name")


@admin.register(TenantMarkup)
class TenantMarkupAdmin(admin.ModelAdmin):
    list_display = (
        "tenant",
        "event_type",
        "provider",
        "margin_pct",
        "valid_from",
        "valid_to",
    )
    list_filter = ("event_type", "provider")
    search_fields = ("tenant__name", "event_type", "provider")
