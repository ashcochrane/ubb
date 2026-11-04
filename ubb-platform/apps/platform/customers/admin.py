from django.contrib import admin

from apps.platform.customers.models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    """The customer admin.

    ⚠ **AN EXISTING CUSTOMER'S TENANT AND BILLING TOPOLOGY ARE DECLARED AT
    CREATION IN V1, AND ARE READ-ONLY HERE AFTERWARDS** (R10 Stage C3, F-7;
    owner/consultant rulings 2026-11-04).

    - **The topology** — its account type, its parent and, on a business, its
      billing topology — is what `Customer.resolve_billing_owner` reads. The
      postpaid close bills a NEW invoice to the owner it names, and every
      posting already carries the owner it was recorded under, so changing it
      mid-period would bill recorded usage twice, or not at all, or to another
      owner.
    - **The tenant** is not an ordinary edit: moving a customer between tenants
      would carry its ownership, its history and every relationship made under
      the original tenant across the isolation boundary.

    The add form still declares all four, as the platform API's create does.
    Changing any of them later needs a future, explicitly designed workflow
    with defined economic cutover semantics; this form is not one.
    """

    list_display = ("external_id", "tenant", "status", "created_at")
    list_filter = ("status", "tenant")
    search_fields = ("external_id",)

    #: Set at creation, read-only on an existing customer: its tenant, and the
    #: fields that decide its billing owner.
    CREATION_ONLY_FIELDS = ("tenant", "account_type", "parent", "billing_topology")

    def get_readonly_fields(self, request, obj=None):
        readonly = tuple(super().get_readonly_fields(request, obj))
        return readonly + self.CREATION_ONLY_FIELDS if obj is not None else readonly
