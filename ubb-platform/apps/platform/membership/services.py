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
from apps.platform.membership.roles import VALID_ROLES
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
