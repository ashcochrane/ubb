from django.contrib import admin

from apps.platform.customers.models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    """The customer admin.

    ⚠ **A CUSTOMER'S BILLING TOPOLOGY IS DECLARED AT CREATION IN V1, AND IS
    READ-ONLY HERE AFTERWARDS** (R10 Stage C3, F-7; owner/consultant ruling
    2026-11-04). Its account type, its parent and — on a business — its billing
    topology are what `Customer.resolve_billing_owner` reads. The postpaid close
    bills a NEW invoice to the owner they name, and every posting already
    carries the owner it was recorded under, so changing them mid-period would
    bill recorded usage twice, or not at all, or to another owner. The add form
    still declares them, as the platform API's create does. Changing a
    customer's topology later needs a future, explicitly designed workflow with
    defined economic cutover semantics; this form is not one.
    """

    list_display = ("external_id", "tenant", "status", "created_at")
    list_filter = ("status", "tenant")
    search_fields = ("external_id",)

    #: Set at creation, read-only on an existing customer.
    TOPOLOGY = ("account_type", "parent", "billing_topology")

    def get_readonly_fields(self, request, obj=None):
        readonly = tuple(super().get_readonly_fields(request, obj))
        return readonly + self.TOPOLOGY if obj is not None else readonly
