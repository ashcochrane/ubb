"""Kernel membership models — Member and Invitation (identity build 1, #79).

These sit in the platform kernel beside tenants and customers, not in a fifth
product. A **Member** is a person who administers a tenant; an **Invitation** is
the first-class, admin-managed record of an outstanding invite. No password is
ever stored here — Clerk owns credentials and the login flow — but the Member
table is ours, so identity survives Clerk being replaced.

Lifecycle: an Admin creates an Invitation, which also mints a ``pending`` Member
(the roster shows invited-but-not-yet-joined). On the invitee's first
Clerk-verified request, the Member is matched by email and flips to ``active``,
stamping the Clerk user id — from then on the principal is bound to that
cryptographic ``sub``, not the email. Revoking a still-pending Invitation
removes its pending Member so it can never activate; member *removal* of an
already-active member is identity build 2 (it needs the last-Admin guard).
"""
from django.db import models

from apps.platform.membership.roles import READ, ROLE_CHOICES
from apps.platform.tenants.models import Tenant
from core.models import BaseModel


def normalize_email(value):
    """The canonical form an email is stored and matched in — lower-cased and
    trimmed. Clerk asserts the verified address; we compare case-insensitively
    so an invite to ``Sam@x.com`` activates a login as ``sam@x.com``."""
    return (value or "").strip().lower()


# Member.status
PENDING = "pending"
ACTIVE = "active"
MEMBER_STATUS_CHOICES = [
    (PENDING, "Pending"),
    (ACTIVE, "Active"),
]

# Invitation.status. ACCEPTED is set when the linked Member activates; REVOKED
# is an Admin cancelling a still-pending invite.
INV_PENDING = "pending"
INV_ACCEPTED = "accepted"
INV_REVOKED = "revoked"
INVITATION_STATUS_CHOICES = [
    (INV_PENDING, "Pending"),
    (INV_ACCEPTED, "Accepted"),
    (INV_REVOKED, "Revoked"),
]


class Invitation(BaseModel):
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="invitations"
    )
    email = models.EmailField()
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=READ)
    status = models.CharField(
        max_length=10, choices=INVITATION_STATUS_CHOICES, default=INV_PENDING,
        db_index=True,
    )
    # Provenance: the Member who sent this invite, or null when it was created
    # with a tenant API key (no member principal). SET_NULL so a future member
    # removal never cascades away the invitation history.
    invited_by_member = models.ForeignKey(
        "membership.Member", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sent_invitations",
    )

    class Meta:
        db_table = "ubb_invitation"
        constraints = [
            # At most one OUTSTANDING invite per email per tenant. Revoking then
            # re-inviting the same address is allowed (the old row is revoked,
            # so it is outside this partial index).
            models.UniqueConstraint(
                fields=["tenant", "email"],
                condition=models.Q(status="pending"),
                name="uq_one_pending_invite_per_tenant_email",
            ),
        ]

    def __str__(self):
        return f"{self.email} ({self.role}) — {self.status}"

    def save(self, *args, **kwargs):
        self.email = normalize_email(self.email)
        super().save(*args, **kwargs)


class Member(BaseModel):
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="members"
    )
    email = models.EmailField(db_index=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=READ)
    status = models.CharField(
        max_length=10, choices=MEMBER_STATUS_CHOICES, default=PENDING,
        db_index=True,
    )
    # Stamped on first activation — the stable, cryptographic identity the
    # principal is bound to once joined (email only matches a *pending* member).
    clerk_user_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    # The invite this member came from, if any. SET_NULL keeps the member if the
    # invitation row is ever cleaned up.
    invitation = models.OneToOneField(
        Invitation, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="member",
    )

    class Meta:
        db_table = "ubb_member"
        constraints = [
            # One membership per email per tenant (pending or active).
            models.UniqueConstraint(
                fields=["tenant", "email"],
                name="uq_one_member_per_tenant_email",
            ),
        ]

    def __str__(self):
        return f"{self.email} ({self.role}) — {self.status}"

    def save(self, *args, **kwargs):
        self.email = normalize_email(self.email)
        super().save(*args, **kwargs)
