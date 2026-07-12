from django.contrib import admin

from apps.metering.pricing.models import TenantMarkup


@admin.register(TenantMarkup)
class TenantMarkupAdmin(admin.ModelAdmin):
    list_display = ("tenant", "customer", "markup_percentage_micros", "fixed_uplift_micros")
    list_filter = ()
    search_fields = ("tenant__name",)
