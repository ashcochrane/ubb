from django.contrib import admin

from apps.metering.pricing.models import Card, Rate


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "tenant",
        "provider",
        "status",
        "created_at",
    )
    list_filter = ("provider", "status")
    search_fields = ("name", "slug", "provider", "tenant__name")


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
