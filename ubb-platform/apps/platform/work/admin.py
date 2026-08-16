from django.contrib import admin

from apps.platform.work.models import Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    # The provider total is listed with its completeness beside it (#328): an
    # operator scanning this list for the unit that burned the money is reading
    # a floor wherever the count is non-zero, and a column that only appears on
    # the detail page is a column nobody reads.
    list_display = ("id", "customer", "status", "total_billed_cost_micros",
                    "total_provider_cost_micros", "unresolved_event_count",
                    "event_count", "created_at")
    list_filter = ("status", "tenant")
    search_fields = ("id", "external_task_id")
    readonly_fields = ("id", "created_at", "updated_at")
