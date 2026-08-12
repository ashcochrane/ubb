"""What a posting's grouping values look like to the tenant who declared them.

A posting stores its grouping values in ten physical slot columns. **The slot is
UBB's identity for the binding, not the tenant's** — nobody chose "slot four" —
so a response that named the slot would be asking an integrator to carry a
mapping UBB already holds. This module is the one place that mapping is applied
on the way out, and #193 §G4 is the ruling behind it.

**Why an object and not a wider list of properties.** The published shape is one
object keyed by the tenant's own declared key, unset slots omitted. That makes
the response self-describing, matches the flat `{key: value}` shape the write
side already takes on the record request and at the start gate, and makes
three-versus-six-versus-ten a question the contract never has to answer:
#276 took six slots to ten without a contract change, and the next widening is
not a contract change either.

**Derived, never stored** — the same rule and the same reason as
`measurements.py` beside it (ADR-0006 §4). Nothing writes a column of this
shape; the projection is computed at the serialiser, from the row's own columns
and the registry that already owns the binding.
"""
from apps.platform.grouping_fields.models import SLOTS
from apps.platform.grouping_fields.queries import keys_by_slot


def grouping_fields_for(posting) -> dict:
    """One posting's grouping values, keyed by the tenant's own declared key.

    Unset slots are omitted: "" is the column's "not set", and publishing it
    would hand an integrator a key they declared and never used, to be told
    apart from a real value by comparing against the empty string.

    A slot holding a value the registry cannot name is omitted too. That is a
    declaration deleted outright rather than retired — retirement keeps the
    binding readable — and there is no key to publish the value under. Falling
    back to the physical slot would publish the one name this shape exists to
    keep private, under a word the tenant never chose.

    **Costs no query when there is nothing to say.** This runs on the
    record-usage response, which is the hottest write path in the system, and a
    tenant that has declared no grouping fields is every tenant on day one. The
    columns are already on the row, so the registry is read only once a value is
    actually there to be named — and then exactly once, over at most ten rows.
    """
    set_slots = {slot: value for slot in SLOTS
                 if (value := getattr(posting, slot))}
    if not set_slots:
        return {}
    keys = keys_by_slot(posting.tenant_id)
    return {keys[slot]: value for slot, value in set_slots.items()
            if slot in keys}
