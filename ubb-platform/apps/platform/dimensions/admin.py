from django.contrib import admin

from apps.platform.dimensions.models import DimensionDef, DimensionValue


@admin.register(DimensionDef)
class DimensionDefAdmin(admin.ModelAdmin):
    list_display = ("tenant", "key", "slot", "scope", "max_cardinality", "retired_at")
    list_filter = ("scope", "slot")
    search_fields = ("key",)


@admin.register(DimensionValue)
class DimensionValueAdmin(admin.ModelAdmin):
    list_display = ("tenant", "key", "value", "created_at")
    list_filter = ("key",)
    search_fields = ("value",)
