from django.contrib import admin

from apps.platform.tasks.models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "status", "total_billed_cost_micros",
                    "total_provider_cost_micros", "event_count", "created_at")
    list_filter = ("status", "tenant")
    search_fields = ("id", "external_task_id")
    readonly_fields = ("id", "created_at", "updated_at")
