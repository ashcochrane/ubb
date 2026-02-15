from django.contrib import admin

from apps.platform.runs.models import Run


@admin.register(Run)
class RunAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "status", "total_cost_micros", "event_count", "created_at")
    list_filter = ("status", "tenant")
    search_fields = ("id", "external_run_id")
    readonly_fields = ("id", "created_at", "updated_at")
