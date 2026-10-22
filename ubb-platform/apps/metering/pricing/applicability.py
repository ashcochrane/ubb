"""Why a subject generates no customer revenue at this level (#351, #151 §8.2;
rewritten by #553, ADR-0021 §5).

`pricing_status = not_applicable` says a posting genuinely has no customer price
and that this is correct rather than a gap. `not_applicable_reason` says why,
and this module is the rule that decides it.

**A reason and not a fifth status** (#151 §8.3). The status is already right;
what was missing is the cause. This extends the four the way `not_applicable`
extended #147's three — adding a distinction INSIDE a value, never reversing
one.

**THE REGIME DECIDES THE REASON, FOR EVERY TENANT (#553, the owner's C2 ruling
of 2026-10-08).** One cause remains: the event belongs to a unit of work sold
for ONE AGREED PRICE, so the customer revenue is that unit's — on its Charge,
projected onto one posting — and none of it is this event's. That is
`fixed_task_pricing`, and it is the answer whatever the tenant's billing mode.

⚠ **THE TIE-BREAK THIS MODULE USED TO ARGUE IS SUPERSEDED, AND ITS VALUE IS
GONE.** It read *"posture wins"*: a metering-only tenant's fixed-price work was
`tenant_not_billing`, on the argument that `fixed_task_pricing` would send a
reader to look for a bill nobody raises (#418). The ruling it is superseded by
separates two questions that sentence joined. Whether UBB may KNOW a customer's
price is not decided by whether UBB COLLECTS it: a metering-only tenant now
declares Pricing Books like any other (ADR-0021 §4), its delivered fixed-price
work produces a Charge whose posting carries the agreed price, and its margin
reporting reads that revenue. `fixed_task_pricing` is then simply true — the
revenue for this event sits on the unit's Charge — and the billing mode is not
encoded a second time in the pricing result; whether money is collected is the
billing product's business, behind its own gate. With no producer left,
`tenant_not_billing` was removed in the same change (a value nothing can
produce is deleted with its last producer, not kept alive), the existing
postings holding it were rewritten to the value that was always true of them
(`usage/0047`), and the sealed receipts that hold it keep it as written.

**Why this is a function and not a registry `value_semantics` block.** The rule
is one fact, and the case where it is false — event-priced work — has no reason
at all, because the price applies and the status is not `not_applicable`. A
`value_semantics` block would have to invent a value for that case, which is
the "answer nobody decided" the registry's totality proof exists to prevent.
So the rule lives here, returns `None` for the case that has no reason, and
says so in the type.

**THE PRICE RESOLVER IS THE CALLER.** `not_applicable` is not a fact about
resolution: the spine declines to consult the ladder at all for work sold for
one agreed price, and asks this for the reason. The fact arrives on
`PricingSubject.pricing_mode`, the thread that carries `work.Task.pricing_mode`
(#415) down to the one function that decides both statuses.
"""
from core.vocabulary import NOT_APPLICABLE_REASON_FIXED_TASK_PRICING


def not_applicable_reason_for(*, sold_for_one_agreed_price: bool) -> str | None:
    """The reason a subject has no customer price, or `None` if it has one.

    ``sold_for_one_agreed_price`` is the unit of work's pricing regime — true
    where the event belongs to a unit sold for one agreed price, so the revenue
    is the unit's and none of it is this event's.

    Keyword-only, as it was when it took two booleans of the same type: a
    caller states which fact it is passing.

    Returns `None` for event-priced work, where the price applies: there is no
    reason because the status is not `not_applicable`. A caller that has
    already decided the status is `not_applicable` can treat a `None` here as a
    contradiction, and the database will refuse the row either way —
    `not_applicable` with no reason is a combination
    `ck_posting_pricing_status_agrees_with_the_price` rejects.
    """
    if sold_for_one_agreed_price:
        return NOT_APPLICABLE_REASON_FIXED_TASK_PRICING
    return None
