from django.contrib import admin

from apps.platform.work.models import CEILING_STATUS_CHOICES, Task

_CEILING_STATUS_WORDING = dict(CEILING_STATUS_CHOICES)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    # The provider total is listed with its completeness beside it (#328): an
    # operator scanning this list for the unit that burned the money is reading
    # a floor wherever the count is non-zero, and a column that only appears on
    # the detail page is a column nobody reads. The ceiling assessment sits
    # beside them for the same reason (#452): it is what the total and the
    # count say about the unit's ceiling, in the registry's word.
    list_display = ("id", "customer", "status", "total_billed_cost_micros",
                    "total_provider_cost_micros", "unresolved_event_count",
                    "ceiling_assessment", "event_count", "created_at")
    list_filter = ("status", "tenant")
    search_fields = ("id", "external_task_id")
    readonly_fields = ("id", "created_at", "updated_at")

    @admin.display(description="Ceiling")
    def ceiling_assessment(self, unit):
        return _CEILING_STATUS_WORDING[unit.ceiling_assessment.status]
