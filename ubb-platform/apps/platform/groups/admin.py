from django.contrib import admin

from apps.platform.groups.models import Group


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "tenant", "margin_pct", "status", "parent", "created_at")
    list_filter = ("status", "tenant")
    search_fields = ("name", "slug")
    readonly_fields = ("id", "created_at", "updated_at")
