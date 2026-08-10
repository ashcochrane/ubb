from django.contrib import admin

from apps.platform.grouping_fields.models import GroupingField, GroupingFieldValue


@admin.register(GroupingField)
class GroupingFieldAdmin(admin.ModelAdmin):
    list_display = ("tenant", "key", "slot", "scope", "max_cardinality", "retired_at")
    list_filter = ("scope", "slot")
    search_fields = ("key",)


@admin.register(GroupingFieldValue)
class GroupingFieldValueAdmin(admin.ModelAdmin):
    list_display = ("tenant", "key", "value", "created_at")
    list_filter = ("key",)
    search_fields = ("value",)
