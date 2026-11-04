from django.contrib import admin

from apps.platform.customers.models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    """The customer admin: inspection and ordinary maintenance of EXISTING
    customers. It is not a customer-creation surface.

    ⚠ **CUSTOMER CREATION IS PERFORMED THROUGH THE PRODUCT CUSTOMER-CREATION
    API, `POST /customers`. DJANGO ADMIN IS NOT A CUSTOMER CREATION SURFACE**
    (R10 Stage C3; owner/consultant ruling 2026-11-04, R1). This is the
    deliberate v1 product boundary: one authoritative creation path. That path
    validates what decides a customer's billing owner — a seat's parent is a
    business of the seat's own tenant, and only a business declares a billing
    topology — and it does what creating a customer entails: the seat-quantity
    sync and the `customer.created` audit record. The admin's add form did
    neither; it could create a seat whose billing owner belonged to another
    tenant, or a pooled owner that is not a business, whose seats' usage
    postpaid billing then never invoiced.

    ⚠ **AN EXISTING CUSTOMER'S TENANT AND BILLING TOPOLOGY ARE CREATION-ONLY,
    AND READ-ONLY HERE** (owner/consultant rulings 2026-11-04).

    - **The topology** — its account type, its parent and, on a business, its
      billing topology — is what `Customer.resolve_billing_owner` reads. The
      postpaid close bills a NEW invoice to the owner it names, and every
      posting already carries the owner it was recorded under, so changing it
      mid-period would bill recorded usage twice, or not at all, or to another
      owner.
    - **The tenant** is not an ordinary edit: moving a customer between tenants
      would carry its ownership, its history and every relationship made under
      the original tenant across the isolation boundary.

    Changing any of them later needs a future, explicitly designed workflow
    with defined economic cutover semantics; this form is not one.
    """

    list_display = ("external_id", "tenant", "status", "created_at")
    list_filter = ("status", "tenant")
    search_fields = ("external_id",)

    #: Set at creation, read-only on an existing customer: its tenant, and the
    #: fields that decide its billing owner.
    CREATION_ONLY_FIELDS = ("tenant", "account_type", "parent", "billing_topology")

    def has_add_permission(self, request):
        # Customers are created through `POST /customers` only (see above).
        return False

    def get_readonly_fields(self, request, obj=None):
        readonly = tuple(super().get_readonly_fields(request, obj))
        return readonly + self.CREATION_ONLY_FIELDS if obj is not None else readonly
