import base64
import json
import uuid
from datetime import datetime, timezone

from django.db.models import Q


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
