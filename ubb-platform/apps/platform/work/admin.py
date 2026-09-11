from django.contrib import admin

from apps.platform.work.models import (
    CEILING_BASIS_CHOICES, CEILING_STATUS_CHOICES, Task)

_CEILING_STATUS_WORDING = dict(CEILING_STATUS_CHOICES)
_CEILING_BASIS_WORDING = dict(CEILING_BASIS_CHOICES)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    # The provider total is listed with its completeness beside it (#328): an
    # operator scanning this list for the unit that burned the money is reading
    # a floor wherever the count is non-zero, and a column that only appears on
    # the detail page is a column nobody reads. The ceiling assessment sits
    # beside them for the same reason (#452): it is what the total and the
    # count say about the unit's ceiling, in the registry's word.
    # And beside the assessment, which basis a stopped unit's ceiling fired
    # on (#458) — blank for a unit that is running or was not stopped by a
    # ceiling, so an operator reading the list sees a window that ran out
    # apart from a cost that was reached.
    list_display = ("id", "customer", "status", "total_billed_cost_micros",
                    "total_provider_cost_micros", "unresolved_event_count",
                    "ceiling_assessment", "ceiling_basis", "event_count",
                    "created_at")
    list_filter = ("status", "tenant")
    search_fields = ("id", "external_task_id")
    readonly_fields = ("id", "created_at", "updated_at")

    @admin.display(description="Ceiling")
    def ceiling_assessment(self, unit):
        return _CEILING_STATUS_WORDING[unit.ceiling_assessment.status]

    @admin.display(description="Ceiling basis")
    def ceiling_basis(self, unit):
        basis = unit.ceiling_basis
        return "" if basis is None else _CEILING_BASIS_WORDING[basis]
