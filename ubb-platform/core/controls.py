"""WHICH SPEND CONTROL A STOP CAME FROM, derived from why it fired (slice 6
§1, #458) — the one place a `control_family` is derived.

A stop's cause (`reason_code`) says which bound was reached; its family
(`control_family`) says which of the four spend controls that bound belongs
to. The second is a function of the first — the unit's own COGS ceiling and
both of its time bounds are the Ceiling's, the pool's stop is the Customer
Spend Pool's, the hard floor's is the Wallet policy's — so the kernel stamps
the family from this map when it announces a stop and needs nothing from
billing to say it, and billing's signal ledger keys its lines by the same map
so the two sides cannot disagree about which control a word names (ADR-001:
this package is importable by the kernel and every product alike).

WHAT IS NOT DERIVABLE HERE, AND IS NOT PRETENDED TO BE. The control's
IDENTITY — the declaration a ceiling was resolved from, the pool row, the
billing profile that carried a floor — is a row the caller of the stop
already holds, and it is passed beside the reason rather than looked up here
(`control_id`). And contained work stopped by its parent's end crossed
nothing of its own: it INHERITS the parent's family and id, which the parent's
row holds and this module does not, so the two cascade reasons name no family
of their own and asking for one is refused rather than answered with a blank.
Admission control stops nothing — it refuses a start — so no reason maps to
it, and the four-value set is held whole by the ledger that declares the
concept's backend consumer, not here.

`ceiling_basis` sits beside the family for the same reason: a Ceiling bounds
cost or time, and which one a stop reached is a fact about the reason. The
work model holds the same pair by reference as the registry's consumer for
the concept (`apps/platform/work/models.py`); this module answers the
question the announcement asks.
"""
from core.vocabulary import (
    CEILING_BASIS_COST,
    CEILING_BASIS_TIME,
    CONTROL_FAMILY_CEILING,
    CONTROL_FAMILY_CUSTOMER_SPEND_POOL,
    CONTROL_FAMILY_WALLET_POLICY,
    REASON_CODE_ABSOLUTE_DEADLINE,
    REASON_CODE_CUSTOMER_SPEND_POOL,
    REASON_CODE_HARD_FLOOR,
    REASON_CODE_PARENT_EXPIRED,
    REASON_CODE_PARENT_KILLED,
    REASON_CODE_SILENCE_WINDOW,
    REASON_CODE_TASK_COGS_CEILING,
)

#: Reason → family, for every reason that names a bound of its own.
FAMILY_BY_REASON = {
    REASON_CODE_TASK_COGS_CEILING: CONTROL_FAMILY_CEILING,
    REASON_CODE_SILENCE_WINDOW: CONTROL_FAMILY_CEILING,
    REASON_CODE_ABSOLUTE_DEADLINE: CONTROL_FAMILY_CEILING,
    REASON_CODE_CUSTOMER_SPEND_POOL: CONTROL_FAMILY_CUSTOMER_SPEND_POOL,
    REASON_CODE_HARD_FLOOR: CONTROL_FAMILY_WALLET_POLICY,
}

#: The reasons a cascade writes on contained work — the family is the
#: PARENT's, read off the parent's row by the cascade, never derived here.
INHERITED_FROM_THE_PARENT = frozenset({
    REASON_CODE_PARENT_KILLED,
    REASON_CODE_PARENT_EXPIRED,
})

#: Reason → what the ceiling that fired bounds. Only a ceiling's reasons are
#: here; every other stop has no basis, and `ceiling_basis` answers `None`.
CEILING_BASIS_BY_REASON = {
    REASON_CODE_TASK_COGS_CEILING: CEILING_BASIS_COST,
    REASON_CODE_SILENCE_WINDOW: CEILING_BASIS_TIME,
    REASON_CODE_ABSOLUTE_DEADLINE: CEILING_BASIS_TIME,
}


class NoFamilyOfItsOwn(LookupError):
    """The reason names no control family this module can derive: a cascade's
    (inherit the parent's) or a word UBB does not produce."""


def control_family(reason_code):
    """The family of the control whose bound `reason_code` says was reached.

    Raises :class:`NoFamilyOfItsOwn` for a cascade reason — the caller must
    read the parent's family — and for any reason not in the map, so a stop
    can never be announced under a blank family.
    """
    try:
        return FAMILY_BY_REASON[reason_code]
    except KeyError:
        raise NoFamilyOfItsOwn(
            f"{reason_code!r} names no control family of its own"
            + (" — contained work inherits its parent's"
               if reason_code in INHERITED_FROM_THE_PARENT else "")) from None


def ceiling_basis(reason_code):
    """`cost` for the COGS ceiling, `time` for either window, `None` for a
    stop that was not a ceiling's."""
    return CEILING_BASIS_BY_REASON.get(reason_code)
