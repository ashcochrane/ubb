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
            member.delete()
        write_event(InvitationRevoked(
            tenant_id=str(tenant.id), invitation_id=str(invitation.id),
            email=invitation.email))
    return invitation


def resolve_member_for_claims(claims):
    """Turn verified Clerk claims into the acting Member, or ``None``.

    On first login this activates every pending Member matching the token's
    email (matched by email, then bound to the Clerk ``sub``); on later logins
    activation is a no-op and the member is selected by ``sub``. Returns a
    single active Member, or ``None`` when the user is not a member, or when the
    user has memberships in more than one tenant (tenant selection is identity
    build 2 — refuse rather than guess). Never raises.
    """
    try:
        sub = (claims.get("sub") or "").strip()
        email = normalize_email(claims.get("email"))
        if not sub:
            # Without a stable subject we cannot bind a principal safely.
            return None
        if email:
            _activate_pending_members(email, sub)
        actives = list(
            Member.objects.select_related("tenant").filter(
                status=ACTIVE, clerk_user_id=sub)
        )
        if len(actives) == 1:
            return actives[0]
        if len(actives) > 1:
            logger.warning(
                "membership.ambiguous_principal",
                extra={"data": {"clerk_user_id": sub, "count": len(actives)}})
        return None
    except Exception:
        logger.warning("membership.resolve_failed", exc_info=True)
        return None


def _activate_pending_members(email, sub):
    """Flip every pending Member for ``email`` to active, binding it to ``sub``.

    Idempotent: after the first login there are no pending rows left, so this is
    a no-op (no writes, no events) on every subsequent request. ``select_for_update``
    serialises concurrent first-login requests — the loser sees active rows and
    does nothing.
    """
    with transaction.atomic():
        pendings = list(
            Member.objects.select_for_update().filter(email=email, status=PENDING))
        for member in pendings:
            member.status = ACTIVE
            member.clerk_user_id = sub
            member.activated_at = timezone.now()
            member.save(update_fields=[
                "status", "clerk_user_id", "activated_at", "updated_at"])
            if member.invitation_id:
                invitation = member.invitation
                if invitation is not None and invitation.status == INV_PENDING:
                    invitation.status = INV_ACCEPTED
                    invitation.save(update_fields=["status", "updated_at"])
            write_event(MemberActivated(
                tenant_id=str(member.tenant_id), member_id=str(member.id),
                email=member.email, role=member.role, clerk_user_id=sub))
