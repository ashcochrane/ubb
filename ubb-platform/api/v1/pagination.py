"""Cursor pagination for the composition layer (#78).

``paginate`` is the one idiom behind every entity-list route: keyset cursor
(the blessed ``core.pagination`` implementation), ``limit`` clamped to
[1, 100] (default 50), ``limit + 1`` fetch to learn ``has_more``, and a
``next_cursor`` only when there is more. A bad cursor is a 400
``invalid_cursor`` problem. Callers wrap the rows in the one envelope:
``{"data": [...], "next_cursor": ..., "has_more": ...}``.
"""
from core.pagination import encode_cursor, decode_cursor, apply_cursor_filter  # noqa: F401
from core.problems import Problem

MAX_LIMIT = 100


def paginate(qs, cursor, limit, time_field="created_at"):
    """Order, cursor-filter, and slice ``qs``; return
    ``(rows, next_cursor, has_more)``. Ordering is always
    ``(-time_field, -id)`` — the keyset the cursor encodes."""
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
