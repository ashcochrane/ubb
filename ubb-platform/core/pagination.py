import base64
import json
import uuid
from datetime import datetime, timezone
from typing import Generic, Optional, TypeVar

from django.db.models import Q
from ninja import Schema

from core.problems import Problem

MAX_LIMIT = 100

T = TypeVar("T")


class Paginated(Schema, Generic[T]):
    """The one cursor envelope (#115) — every list endpoint answers this shape.

    Declare a CONCRETE subclass per endpoint (``class PaginatedRates(
    Paginated[RateOut]): ...``) rather than using ``Paginated[RateOut]``
    inline: the subclass pins the OpenAPI component name, keeping the
    committed spec — and the SDK DTOs generated from it — stable (ADR-002;
    post-launch renames are contract breaks, ADR-003 §4). A subclass
    serializes to exactly the schema of the hand-written envelope it
    replaced (pinned by api/v1/tests/test_pagination.py).
    """
    data: list[T]
    next_cursor: Optional[str] = None
    has_more: bool


def encode_cursor(effective_at, record_id):
    """Encode pagination cursor as base64 JSON."""
    payload = {
        "v": 1,
        "t": effective_at.astimezone(timezone.utc).isoformat(timespec="microseconds"),
        "id": str(record_id),
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def decode_cursor(cursor_str):
    """Decode pagination cursor. Returns (datetime, uuid) or raises ValueError."""
    try:
        raw = base64.urlsafe_b64decode(cursor_str.encode())
        payload = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as e:
        raise ValueError(f"Invalid cursor: {e}")

    if payload.get("v") != 1:
        raise ValueError("Unsupported cursor version")

    try:
        t = datetime.fromisoformat(payload["t"])
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
    except (KeyError, ValueError) as e:
        raise ValueError(f"Invalid cursor timestamp: {e}")

    try:
        record_id = uuid.UUID(payload["id"])
    except (KeyError, ValueError) as e:
        raise ValueError(f"Invalid cursor id: {e}")

    return t, record_id


def apply_cursor_filter(queryset, cursor_str, time_field="effective_at"):
    """Apply cursor-based pagination filter to queryset (descending order)."""
    if not cursor_str:
        return queryset
    t, record_id = decode_cursor(cursor_str)
    return queryset.filter(
        Q(**{f"{time_field}__lt": t})
        | Q(**{time_field: t, "id__lt": record_id})
    )


def paginate(qs, cursor, limit, time_field="created_at"):
    """The one entity-list idiom (#78): order, cursor-filter, and slice
    ``qs``; return ``(rows, next_cursor, has_more)``.

    Keyset on ``(-time_field, -id)`` — the pair the cursor encodes; ``limit``
    clamped to [1, MAX_LIMIT] (default 50 at the endpoints); ``limit + 1``
    fetch to learn ``has_more``; ``next_cursor`` only when there is more. A
    bad cursor is a 400 ``invalid_cursor`` problem. Endpoints answer via
    ``page()`` below, which wraps the rows in the one envelope; call this
    directly only when the raw rows are the point.
    """
    limit = min(max(limit, 1), MAX_LIMIT)
    qs = qs.order_by(f"-{time_field}", "-id")
    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field=time_field)
        except ValueError as e:
            raise Problem("invalid_cursor", str(e))
    rows = list(qs[: limit + 1])
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = encode_cursor(getattr(last, time_field), last.id)
    return rows, next_cursor, has_more


def page(qs, cursor, limit, *, serialize, time_field="created_at"):
    """``paginate()`` + the envelope (#115): the whole list answer in one call.

    ``serialize`` is the entity's named single-entry serializer (one function
    per Out schema, declared beside it); the return value is the
    ``Paginated[T]`` body: ``{"data", "next_cursor", "has_more"}``.
    """
    rows, next_cursor, has_more = paginate(qs, cursor, limit, time_field=time_field)
    return {"data": [serialize(r) for r in rows],
            "next_cursor": next_cursor, "has_more": has_more}


def empty_page():
    """The empty envelope — the list answer when the container (e.g. a
    wallet) does not exist yet, or the caller may not see the rows. A fresh
    dict every call; never share a module-level literal."""
    return {"data": [], "next_cursor": None, "has_more": False}
