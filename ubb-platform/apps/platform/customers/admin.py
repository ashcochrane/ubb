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

    ⚠ **A CUSTOMER'S LIFECYCLE FIELDS ARE NOT ADMIN CONTROLS** (R10 Stage C4;
    owner/consultant ruling 2026-11-05, PLAN §7 item 41). ``status``,
    ``suspension_reason`` and ``deleted_at`` are read-only here. Editing them
    raw bypassed every lifecycle side effect — the announcement, the seat
    roster's notification, the soft-delete path — and let a system cause be
    rewritten (a ``hard_floor`` suspension edited to ``payment_failed`` was
    lifted by the AR pass with the wallet still past its floor).

    - **A manual hold** is placed and released only through
      ``manage.py set_customer_manual_hold``, which never overwrites or clears
      a system cause.
    - **A system suspension** is lifted only by its own recovery.
    - **Closing a customer** is not a supported v1 transition.
    - **Deleting** stays on the single-object delete, which is the canonical
      soft delete (``Customer.delete`` → ``soft_delete``). The bulk "delete
      selected" action is removed: it ran a queryset delete, a HARD delete.
    """

    list_display = ("external_id", "tenant", "status", "created_at")
    list_filter = ("status", "tenant")
    search_fields = ("external_id",)

    #: Set at creation, read-only on an existing customer: its tenant, and the
    #: fields that decide its billing owner.
    CREATION_ONLY_FIELDS = ("tenant", "account_type", "parent", "billing_topology")

    #: Changed only by the lifecycle workflows that own their side effects,
    #: read-only on an existing customer.
    LIFECYCLE_FIELDS = ("status", "suspension_reason", "deleted_at")

    def has_add_permission(self, request):
        # Customers are created through `POST /customers` only (see above).
        return False

    def get_readonly_fields(self, request, obj=None):
        readonly = tuple(super().get_readonly_fields(request, obj))
        if obj is None:
            return readonly
        return readonly + self.CREATION_ONLY_FIELDS + self.LIFECYCLE_FIELDS

    def save_model(self, request, obj, form, change):
        # An edit writes ONLY the fields this form changed. Django's default
        # saves the whole row, read-only fields included, as they were when the
        # page loaded — so a manual hold, a system suspension or a soft delete
        # committed meanwhile would be silently written back over.
        if not change:
            return super().save_model(request, obj, form, change)
        editable = {f.name for f in obj._meta.concrete_fields}
        changed = [name for name in form.changed_data if name in editable]
        if changed:
            obj.save(update_fields=[*changed, "updated_at"])

    def get_actions(self, request):
        # No bulk delete: Django's action runs a queryset delete, which is a
        # hard delete that skips `Customer.soft_delete` and everything it does.
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions
