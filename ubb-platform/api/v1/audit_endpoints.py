"""The tenant-facing audit feed (#82, ADR-004 §5).

One cursor-paginated read over the append-only ledger, answering "who changed
this, and when?" a year later. Readable by **every tenant principal at any role**
— a Read floor, because the trail is transparency, not power (ADR-004: any
principal may see what happened on the account, even a Read-only one). It rides
the tenant-key auth scheme, so an end-customer widget token — which authenticates
only ``/me`` — can never reach it (401), exactly as the spec requires.

Scope is the tenant the principal authenticated against: a live key sees the live
account's history; a sandbox (``ubb_test_``) key sees the sandbox's (and a sandbox
reset clears those entries, recording itself as the fresh history's first line).
Operator actions on the account appear here like any other principal's, under the
one ``UBB operator`` name; widget-initiated top-ups appear with actor kind
``end_customer``.
"""
from typing import Optional

from ninja import Router, Schema

from api.v1.pagination import paginate
from apps.platform.audit.models import AuditRecord
from core.auth import ApiKeyAuth, READ, role_floor

audit_router = Router(auth=ApiKeyAuth())


class AuditRecordOut(Schema):
    id: str
    created_at: str
    action: str
    actor_kind: str
    actor_id: str
    actor_display: str
    resource_type: str
    resource_id: str
    correlation_id: str
    metadata: dict


class AuditRecordListResponse(Schema):
    data: list[AuditRecordOut]
    next_cursor: Optional[str] = None
    has_more: bool


def _audit_out(r):
    return {
        "id": str(r.id),
        "created_at": r.created_at.isoformat(),
        "action": r.action,
        "actor_kind": r.actor_kind,
        "actor_id": r.actor_id,
        "actor_display": r.actor_display,
        "resource_type": r.resource_type,
        "resource_id": r.resource_id,
        "correlation_id": r.correlation_id,
        "metadata": r.metadata,
    }


@audit_router.get("/records", response=AuditRecordListResponse)
@role_floor(READ)
def list_audit_records(request, action: str = None, resource_type: str = None,
                       resource_id: str = None, cursor: str = None,
                       limit: int = 50):
    """This account's audit entries, newest first (cursor-paginated, #78 envelope).

    Optional exact-match filters narrow the feed: ``action`` (e.g.
    ``rate_card.published``), or ``resource_type`` + ``resource_id`` together to
    answer "who changed THIS rate card?" — both served by the ledger's indexes.
    Not product-gated: the trail spans every product a tenant uses.
    """
    qs = AuditRecord.objects.filter(tenant_id=request.auth.tenant.id)
    if action:
        qs = qs.filter(action=action)
    if resource_type:
        qs = qs.filter(resource_type=resource_type)
    if resource_id:
        qs = qs.filter(resource_id=resource_id)
    rows, next_cursor, has_more = paginate(qs, cursor, limit)
    return {"data": [_audit_out(r) for r in rows],
            "next_cursor": next_cursor, "has_more": has_more}
