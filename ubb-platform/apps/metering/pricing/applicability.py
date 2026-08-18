"""Why a subject generates no customer revenue at this level (#351, #151 §8.2).

`pricing_status = not_applicable` says a posting genuinely has no customer price
and that this is correct rather than a gap. It does not say WHICH of two
mutually exclusive causes produced it, and the two send a reader to different
places: one to a Charge that exists at the Task, the other to no Charge at all.
`not_applicable_reason` carries that, and this module is the rule that decides
it.

**A reason and not a fifth status** (#151 §8.3). The status is already right;
what was missing is the cause. This extends the four the way `not_applicable`
extended #147's three — adding a distinction INSIDE a value, never reversing
one.

**POSTURE WINS THE TIE-BREAK, AND THE ARGUMENT IS WORTH STATING BECAUSE A
CALLER WILL BE TEMPTED TO PREFER THE MORE SPECIFIC ONE.** Both facts can be true
at once: a metering-only tenant can run a Task sold for one agreed price. The
answer there is `tenant_not_billing`, not `fixed_task_pricing`. For a
metering-only tenant **no Charge is created anywhere**, so naming the job's
pricing regime would imply revenue sits on a Charge that does not exist —
sending a reader to look for a number nobody wrote. `fixed_task_pricing` is only
ever true of a tenant that does bill through UBB, where the Charge really is at
the Task and really can be looked up.

**Why this is a function and not a registry `value_semantics` block.** The
registry can carry a decision rule as data, and the compiler proves such a rule
**total** over its declared boolean inputs. This rule is not: of the four
combinations of the two facts below, the fourth — a billing tenant running an
event-priced job — has no `not_applicable_reason` at all, because the price
applies and the status is not `not_applicable`. A `value_semantics` block would
have to invent a value for that case, which is precisely the "answer nobody
decided" the totality proof exists to prevent. So the rule lives here, returns
`None` for the case that has no reason, and says so in the type.

**It has no production caller yet, and that is the shape of this slice rather
than an oversight.** The price resolver — the one new seam slice 4 introduces —
is what will consult it, along with the rest of the four statuses' writers. This
is the same way `PRICING_MODE_EVENT_PRICED` is named out loud in
`services/pricing_service.py` before the column it will be read from exists: the
rule that is already decided is written down where its caller will find it,
rather than re-derived from a decision document by whoever gets there first.
"""
from core.vocabulary import (
    NOT_APPLICABLE_REASON_FIXED_TASK_PRICING,
    NOT_APPLICABLE_REASON_TENANT_NOT_BILLING,
)


def not_applicable_reason_for(*, tenant_bills_through_ubb: bool,
                              sold_for_one_agreed_price: bool) -> str | None:
    """The reason a subject has no customer price, or `None` if it has one.

    Both arguments are keyword-only because they are two booleans of the same
    type: a positional call site that swapped them would produce the *other*
    reason silently, on the one path where the two answers differ.

    ``tenant_bills_through_ubb`` is the tenant's posture — `full_billing` is
    true, `metering_only` is false. ``sold_for_one_agreed_price`` is the unit of
    work's pricing regime — true where the event belongs to a Task sold for one
    agreed price, so the revenue is the Task's and none of it is this event's.

    Returns `None` for a billing tenant running an event-priced job, which is
    the case where the price applies: there is no reason because the status is
    not `not_applicable`. A caller that has already decided the status is
    `not_applicable` can treat a `None` here as a contradiction, and the
    database will refuse the row either way — `not_applicable` with no reason is
    one of the seven combinations `ck_posting_pricing_status_agrees_with_the_price`
    rejects.
    """
    if not tenant_bills_through_ubb:
        # Posture wins, whatever the job's regime. See the module docstring.
        return NOT_APPLICABLE_REASON_TENANT_NOT_BILLING
    if sold_for_one_agreed_price:
        return NOT_APPLICABLE_REASON_FIXED_TASK_PRICING
    return None
