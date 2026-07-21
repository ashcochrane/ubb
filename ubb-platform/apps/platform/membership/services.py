"""Membership domain operations (identity build 1, #79).

The kernel owns the invite → activate → revoke lifecycle; the composition layer
(``api/v1``) only translates HTTP to these calls. Every state change is written
in the same transaction as its outbox event, and ``member.activated`` is emitted
from ``resolve_member_for_claims`` — the activation path runs inside the auth
seam, not an endpoint, because "activation on first login" is transparent.
"""
import logging

from django.db import transaction
from django.utils import timezone

from apps.platform.events.outbox import write_event
from apps.platform.events.schemas import (
    InvitationCreated,
    InvitationRevoked,
    MemberActivated,
)
from apps.platform.membership.models import (
    ACTIVE,
    INV_ACCEPTED,
    INV_PENDING,
    INV_REVOKED,
    PENDING,
    Invitation,
    Member,
    normalize_email,
)
from apps.platform.membership.roles import ADMIN, VALID_ROLES
from core.problems import Problem

logger = logging.getLogger("ubb.auth")


def invite_member(tenant, email, role, invited_by_member=None):
    """Create a first-class Invitation and its pending Member for (tenant,
    email). Returns the Invitation.

    Refuses (Problem) an unknown role, an email that is already an active
    member, or an email that already has an outstanding pending invite (the
    partial unique index is the backstop; this pre-check makes the 409 clean).
    Emits ``invitation.created``.
    """
    email = normalize_email(email)
    if not email or "@" not in email:
        raise Problem("validation_error", "a valid email address is required")
    if role not in VALID_ROLES:
        raise Problem("validation_error",
                      f"role must be one of {sorted(VALID_ROLES)}")
    with transaction.atomic():
        existing = Member.objects.select_for_update().filter(
            tenant=tenant, email=email).first()
        if existing is not None:
            if existing.status == ACTIVE:
                raise Problem("conflict", "email is already a member of this tenant")
            raise Problem("conflict",
                          "an invitation for this email is already pending")
        invitation = Invitation.objects.create(
            tenant=tenant, email=email, role=role,
            invited_by_member=invited_by_member,
        )
        member = Member.objects.create(
            tenant=tenant, email=email, role=role, status=PENDING,
            invitation=invitation,
        )
        write_event(InvitationCreated(
            tenant_id=str(tenant.id), invitation_id=str(invitation.id),
            member_id=str(member.id), email=email, role=role))
    return invitation


def revoke_invitation(tenant, invitation_id):
    """Revoke a still-pending invitation and drop its pending Member so it can
    never activate. Returns the (revoked) Invitation.

    404 if unknown; idempotent no-op if already revoked; 409 if already
    accepted — un-inviting an active member is member removal (identity build
    2, which needs the last-Admin guard). Emits ``invitation.revoked`` only on
    the pending → revoked transition.
    """
    with transaction.atomic():
        invitation = Invitation.objects.select_for_update().filter(
            tenant=tenant, id=invitation_id).first()
        if invitation is None:
            raise Problem("not_found", "invitation not found")
        if invitation.status == INV_REVOKED:
            return invitation
        if invitation.status == INV_ACCEPTED:
            raise Problem(
                "conflict",
                "invitation already accepted; removing an active member is "
                "not available in this build")
        invitation.status = INV_REVOKED
        invitation.save(update_fields=["status", "updated_at"])
        member = Member.objects.select_for_update().filter(
            invitation=invitation, status=PENDING).first()
        if member is not None:
            # Hard delete is deliberate here (not a soft-delete policy break): a
            # pending Member never activated, so it has no history worth keeping
            # — the revoked Invitation IS the durable audit record — and the
            # unconditional uq_one_member_per_tenant_email would otherwise let a
            # tombstoned row block re-inviting the same address.
            member.delete()
        write_event(InvitationRevoked(
            tenant_id=str(tenant.id), invitation_id=str(invitation.id),
            email=invitation.email))
    return invitation


def _guard_last_active_admin(locked_members, member, *, new_role):
    """Refuse an op that would leave the tenant with zero active Admins.

    The last-Admin guard (identity build 2, #80): a tenant must always keep at
    least one active Admin, so it can never lock itself out. ``locked_members``
    are all the tenant's Member rows, already ``select_for_update``-locked in a
    deterministic order by the caller — so two concurrent demote/remove requests
    against two different Admins serialise and cannot both slip past the count.

    The op is a demotion (``new_role`` is a non-Admin role) or a removal
    (``new_role`` is ``None``). Only ACTIVE Admins count toward lock-out: a
    pending Admin invitation is not yet holding the keys.
    """
    demote_or_remove = new_role != ADMIN  # a non-admin role, or None (removal)
    if not (member.status == ACTIVE and member.role == ADMIN and demote_or_remove):
        return
    other_active_admins = sum(
        1 for m in locked_members
        if m.pk != member.pk and m.status == ACTIVE and m.role == ADMIN)
    if other_active_admins == 0:
        raise Problem(
            "last_active_admin",
            "cannot demote or remove the tenant's last active Admin — a tenant "
            "must always keep at least one active Admin")


def _lock_roster_find_member(tenant, member_id):
    """Lock the tenant's whole member roster (deterministic order) and return
    ``(roster, target)``. Locking every row in one ordered query gives
    concurrent demote/remove requests a single lock order — no deadlock — and a
    consistent snapshot for the last-Admin count. Must be called inside a
    transaction (``select_for_update``). 404 if the target isn't in the roster.
    """
    roster = list(Member.objects.select_for_update().filter(
        tenant=tenant).order_by("created_at", "id"))
    member = next((m for m in roster if str(m.id) == str(member_id)), None)
    if member is None:
        raise Problem("not_found", "member not found")
    return roster, member


def change_member_role(tenant, member_id, new_role):
    """Change a member's role (Admin-gated route). Returns the updated Member.

    404 if unknown; 422 on an unknown role; 409 ``last_active_admin`` when the
    change would demote the tenant's last active Admin. A no-op (same role)
    returns the member untouched. For a still-pending member the linked
    invitation's role is kept in step, so activation reflects the new role.
    """
    if new_role not in VALID_ROLES:
        raise Problem("validation_error",
                      f"role must be one of {sorted(VALID_ROLES)}")
    with transaction.atomic():
        members, member = _lock_roster_find_member(tenant, member_id)
        if member.role == new_role:
            return member
        _guard_last_active_admin(members, member, new_role=new_role)
        member.role = new_role
        member.save(update_fields=["role", "updated_at"])
        if member.status == PENDING and member.invitation_id:
            invitation = member.invitation
            if (invitation is not None and invitation.status == INV_PENDING
                    and invitation.role != new_role):
                invitation.role = new_role
                invitation.save(update_fields=["role", "updated_at"])
    return member


def remove_member(tenant, member_id):
    """Remove a member (Admin-gated route). 404 if unknown.

    409 ``last_active_admin`` when removing the tenant's last active Admin. The
    Member row is hard-deleted — the principal 401s on its next request and the
    email is free to be re-invited (the unconditional
    uq_one_member_per_tenant_email would otherwise let a tombstone block a
    re-invite; same rationale as revoke_invitation's pending delete). Removing a
    still-pending member also revokes its outstanding invitation so a later first
    login can never resurrect it.
    """
    with transaction.atomic():
        members, member = _lock_roster_find_member(tenant, member_id)
        _guard_last_active_admin(members, member, new_role=None)
        invitation = None
        if member.invitation_id:
            invitation = Invitation.objects.select_for_update().filter(
                pk=member.invitation_id).first()
        member.delete()
        if invitation is not None and invitation.status == INV_PENDING:
            invitation.status = INV_REVOKED
            invitation.save(update_fields=["status", "updated_at"])


def bootstrap_owner_admin(tenant, owner_email):
    """Seed a fresh tenant's first Admin through the standard machinery (#80).

    The operator names an owner email at tenant provisioning; this routes it
    straight through ``invite_member`` with the Admin role — there is no bespoke
    first-admin code path, so the owner joins exactly like any later teammate
    (Clerk signup, activation on first login). Returns the created (or
    pre-existing) Invitation, or ``None`` for a blank email. Tolerant of
    re-provisioning: an email that is already a member or already has a pending
    invite is left as-is rather than raising.
    """
    email = normalize_email(owner_email)
    if not email:
        return None
    existing = Member.objects.filter(tenant=tenant, email=email).first()
    if existing is not None:
        return existing.invitation
    return invite_member(tenant, email, ADMIN)


def resolve_member_for_claims(claims):
    """Turn verified Clerk claims into the acting Member, or ``None``.

    A returning member is selected by the Clerk ``sub`` it was bound to at
    activation; a first login is activated by matching a pending Member on email.
    Crucially, a member with a working membership is never disturbed — additional
    memberships (a second tenant) are only activated once tenant selection lands
    (identity build 2), so a later invite can never break an existing principal.

    Returns a single active Member, or ``None`` when: the token has no subject,
    the user is not a member, or resolution is ambiguous (memberships in more
    than one tenant, or more than one pending invite for the email — refuse
    rather than guess). Never raises.
    """
    try:
        sub = (claims.get("sub") or "").strip()
        email = normalize_email(claims.get("email"))
        if not sub:
            # Without a stable subject we cannot bind a principal safely.
            return None
        # Already joined: select by the cryptographic subject, and do NOT touch
        # any pending membership — activating one here could turn a working
        # single-tenant principal ambiguous (two actives) and lock the user out.
        actives = list(
            Member.objects.select_related("tenant").filter(
                status=ACTIVE, clerk_user_id=sub))
        if len(actives) == 1:
            return actives[0]
        if len(actives) > 1:
            logger.warning(
                "membership.ambiguous_principal",
                extra={"data": {"clerk_user_id": sub, "count": len(actives)}})
            return None
        # First login: activate the pending membership matched by email, but only
        # when it is unambiguous. Multiple pending invites (different tenants)
        # can't be resolved without a tenant selector, so they stay pending.
        if not email:
            return None
        pendings = list(
            Member.objects.select_related("tenant").filter(
                status=PENDING, email=email))
        if len(pendings) == 1:
            return _activate_member(pendings[0], sub)
        if len(pendings) > 1:
            logger.warning(
                "membership.ambiguous_pending",
                extra={"data": {"clerk_user_id": sub, "count": len(pendings)}})
        return None
    except Exception:
        logger.warning("membership.resolve_failed", exc_info=True)
        return None


def _activate_member(member, sub):
    """Flip one pending Member to active, binding it to ``sub``. Returns the
    active Member (or ``None`` if it turned out not to be activatable).

    ``select_for_update`` serialises concurrent first-login requests: the loser
    re-reads an already-active row and returns it — one activation, one event.
    """
    with transaction.atomic():
        locked = Member.objects.select_for_update().select_related(
            "tenant").get(pk=member.pk)
        if locked.status == ACTIVE:
            return locked
        if locked.status != PENDING:
            return None
        locked.status = ACTIVE
        locked.clerk_user_id = sub
        locked.activated_at = timezone.now()
        locked.save(update_fields=[
            "status", "clerk_user_id", "activated_at", "updated_at"])
        if locked.invitation_id:
            invitation = locked.invitation
            if invitation is not None and invitation.status == INV_PENDING:
                invitation.status = INV_ACCEPTED
                invitation.save(update_fields=["status", "updated_at"])
        write_event(MemberActivated(
            tenant_id=str(locked.tenant_id), member_id=str(locked.id),
            email=locked.email, role=locked.role, clerk_user_id=sub))
        return locked
