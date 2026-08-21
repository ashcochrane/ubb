from django.contrib import admin

from apps.platform.plans.models import CustomerPlanAssignment, Plan


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "tenant", "access_fee_micros",
                    "per_seat_micros", "pricing_book", "archived_at")
    list_filter = ("tenant", "interval")
    search_fields = ("key", "name")


@admin.register(CustomerPlanAssignment)
class CustomerPlanAssignmentAdmin(admin.ModelAdmin):
    list_display = ("customer", "plan", "assigned_at")
    list_filter = ("tenant",)
