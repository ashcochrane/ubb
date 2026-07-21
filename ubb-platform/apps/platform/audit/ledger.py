"""``record()`` — the one surface for writing an audit entry (ADR-004 §2, §6).

The ``write_event`` calling pattern: call it at the mutation site, inside the same
``@transaction.atomic`` as the change, and the actor is read from the request-scoped
contextvar the auth seam captured — mutation sites never pass "who" by hand. If the
transaction rolls back, the entry vanishes with it; if it commits, the entry is
durable. Unlike ``write_event`` there is no post-commit dispatch — a ledger has no
queue, no doorbell, nothing to deliver.
"""
import logging

from apps.platform.audit.actions import is_registered_action
from apps.platform.audit.actors import SYSTEM, get_current_actor
from apps.platform.audit.models import AuditRecord
from core.logging import get_correlation_id

logger = logging.getLogger("ubb.audit")


def record(*, action, tenant_id, resource_type, resource_id="",
           metadata=None, actor=None):
    """Write an audit entry. **Call inside the mutation's ``@transaction.atomic``.**

    ``action`` must be a registered name (``apps.platform.audit.actions``) — an
    unregistered name is a programming error and raises, keeping the contractual
    registry from drifting from what the ledger writes. ``actor`` defaults to the
    principal captured at the auth seam this request; an entry with no resolvable
    actor is still written — never lose the fact that a change happened — under the
    reserved ``system`` kind, and logged so the gap is visible.

    Returns the created ``AuditRecord``.
    """
    if not is_registered_action(action):
        raise ValueError(
            f"unregistered audit action {action!r} — add it to "
            f"apps.platform.audit.actions.AUDIT_ACTIONS (additive-only)"
        )

    actor = actor if actor is not None else get_current_actor()
    if actor is None:
        logger.warning(
            "audit.unattributed",
            extra={"data": {"action": action, "resource_type": resource_type}},
        )

    return AuditRecord.objects.create(
        tenant_id=tenant_id,
        action=action,
        actor_kind=actor.kind if actor is not None else SYSTEM,
        actor_id=actor.id if actor is not None else "",
        actor_display=actor.display if actor is not None else "",
        resource_type=resource_type,
        resource_id=str(resource_id or ""),
        # Links the entry to any outbox events the same request emitted (§4).
        correlation_id=get_correlation_id(),
        metadata=metadata or {},
    )
