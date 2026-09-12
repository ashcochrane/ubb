from django.db import models, transaction

from apps.platform.customers.hooks import notify_seat_roster_changed
from core.models import BaseModel
from core.soft_delete import SoftDeleteMixin


#: The three standings, by name (#462): a suspended or closed customer is
#: refused new work by the kernel's admission check for every tenant, and
#: the check compares against these rather than a fourth spelling. The
#: status has no registry seat, so this model is the one home for them —
#: `ACCOUNT_TYPE_*` below is the precedent.
CUSTOMER_STATUS_ACTIVE = "active"
CUSTOMER_STATUS_SUSPENDED = "suspended"
CUSTOMER_STATUS_CLOSED = "closed"
CUSTOMER_STATUS_CHOICES = [
    (CUSTOMER_STATUS_ACTIVE, "Active"),
    (CUSTOMER_STATUS_SUSPENDED, "Suspended"),
    (CUSTOMER_STATUS_CLOSED, "Closed"),
]

#: The two account types other code branches on, by name (#459): a SEAT under
#: a pooled business is funded by its parent, and a BUSINESS is the altitude
#: the customer spend pool's tenant default never reaches. The account type
#: has no registry seat, so this model is the one home for its spellings.
ACCOUNT_TYPE_BUSINESS = "business"
ACCOUNT_TYPE_SEAT = "seat"
ACCOUNT_TYPE_CHOICES = [("individual", "Individual"),
                        (ACCOUNT_TYPE_BUSINESS, "Business"),
                        (ACCOUNT_TYPE_SEAT, "Seat")]
BILLING_TOPOLOGY_CHOICES = [("pooled", "Pooled"), ("allocated", "Allocated")]


class Customer(SoftDeleteMixin, BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="customers"
    )
    external_id = models.CharField(max_length=255, db_index=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=CUSTOMER_STATUS_CHOICES,
        default="active",
        db_index=True,
    )
    metadata = models.JSONField(default=dict)
    revenue_mode = models.CharField(max_length=20, blank=True, default="")  # "" | "billed" | "metered_only"
    account_type = models.CharField(max_length=12, choices=ACCOUNT_TYPE_CHOICES, default="individual", db_index=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="seats")
    billing_topology = models.CharField(max_length=10, choices=BILLING_TOPOLOGY_CHOICES, blank=True, default="")
    # Tier-2 P6b (D15): why the customer was suspended. Set on every suspend;
    # only a MONETARY reason is auto-cleared on recovery, so a top-up never
    # silently un-suspends an admin/fraud suspension. A monetary reason is the
    # stop that opened the episode, in that stop's own word (slice 6 §9,
    # `reasons.HARD_FLOOR` / `reasons.CUSTOMER_SPEND_POOL`; the pair is
    # `LiveCounter._MONEY_SUSPEND_REASONS`). "" when active / suspended for an
    # unrecorded reason.
    suspension_reason = models.CharField(max_length=40, blank=True, default="")

    class Meta:
        db_table = "ubb_customer"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "external_id"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_customer_tenant_external",
            ),
        ]

    def resolve_billing_owner(self):
        """The Customer whose wallet/card/auto-top-up funds this customer:
        the business for a POOLED seat, otherwise self."""
        if self.account_type == "seat" and self.parent_id:
            if self.parent.billing_topology == "pooled":
                return self.parent
        return self

    def soft_delete(self):
        """Soft delete customer and emit outbox event for product cleanup.

        Removing a seat shrinks the business roster: push the decremented live
        seat count to Stripe on commit so a removed seat never keeps billing as a
        ghost on the subscription's per-seat quantity.
        """
        with transaction.atomic():
            super().soft_delete()
            from apps.platform.events.outbox import write_event
            from apps.platform.events.schemas import CustomerDeleted
            write_event(CustomerDeleted(
                tenant_id=str(self.tenant_id),
                customer_id=str(self.id),
            ))
            if self.account_type == "seat" and self.parent_id:
                notify_seat_roster_changed(self.parent)

    def __str__(self):
        return f"Customer({self.external_id})"

