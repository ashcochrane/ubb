"""Read contract for the Grouping Field registry (ADR-001).

Products (metering pricing/analytics, billing start-gate) call these instead of
importing the ORM models, so the registry can be reshaped without touching
product code. Returns plain data only — never ORM objects.
"""
from apps.platform.grouping_fields.models import SLOT_CHOICES, GroupingField


def slot_map(tenant_id) -> dict:
    """{declared key: slot} for a tenant, retired defs included.

    Retired defs stay in the map so historical rows remain groupable (D8) —
    retirement blocks new VALUES, not reads.
    """
    return dict(GroupingField.objects.filter(tenant_id=tenant_id)
                .values_list("key", "slot"))


def keys_by_slot(tenant_id) -> dict:
    """{slot: declared key} for a tenant — the inverse of :func:`slot_map`.

    `slot_map` answers the WRITE direction: a caller names its own key and the
    registry says which column to put it in. This answers the READ direction,
    which is what a response needs — the row carries a column and the reader
    needs the tenant's own word for it. Both are one query over at most ten rows
    under `uq_dimension_def_slot`, and the two are inverses because that
    constraint and `uq_dimension_def_key` together make the binding a bijection.

    Retired defs are included for the reason `slot_map` includes them: a posting
    recorded before its field was retired must still be able to say what its
    value means (D8).
    """
    return dict(GroupingField.objects.filter(tenant_id=tenant_id)
                .values_list("slot", "key"))


def declared_dimensions(tenant_id) -> list[dict]:
    """Full registry as plain dicts, in slot order.

    SLOT ORDER IS NOT ALPHABETICAL ORDER, and it became possible for the two to
    disagree the moment #276 took the slot count into double figures: sorted as
    text, slot ten falls between slot one and slot two. Sorting by the declared
    vocabulary's own order is exact and stays exact whatever the identifiers are
    spelled like next. The registry is capped at one row per slot, so this sorts
    at most ten rows in Python rather than in the database.
    """
    order = {slot: position for position, (slot, _) in enumerate(SLOT_CHOICES)}
    rows = [
        {"key": d["key"], "slot": d["slot"], "scope": d["scope"],
         "max_cardinality": d["max_cardinality"],
         "retired": d["retired_at"] is not None}
        for d in GroupingField.objects.filter(tenant_id=tenant_id)
        .values("key", "slot", "scope", "max_cardinality", "retired_at")
    ]
    # A slot the vocabulary does not contain sorts last rather than raising: a
    # read contract that refuses to answer is a worse way to surface bad data
    # than one that answers and puts it where a reader will notice.
    return sorted(rows, key=lambda r: (order.get(r["slot"], len(order)), r["slot"]))
