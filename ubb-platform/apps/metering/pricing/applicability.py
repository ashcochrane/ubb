"""Why a subject generates no customer revenue at this level (#351, #151 §8.2).

`pricing_status = not_applicable` says a posting genuinely has no customer price
and that this is correct rather than a gap. It does not say WHICH of two
mutually exclusive causes produced it, and the two send a reader to different
places: one to the customer charge that exists at the Task, the other to no
customer charge at all. `not_applicable_reason` carries that, and this module is
the rule that decides it.

**A reason and not a fifth status** (#151 §8.3). The status is already right;
what was missing is the cause. This extends the four the way `not_applicable`
extended #147's three — adding a distinction INSIDE a value, never reversing
one.

**POSTURE WINS THE TIE-BREAK, AND THE ARGUMENT IS WORTH STATING BECAUSE A
CALLER WILL BE TEMPTED TO PREFER THE MORE SPECIFIC ONE.** Both facts can be true
at once: a metering-only tenant can run a Task sold for one agreed price. The
answer there is `tenant_not_billing`, not `fixed_task_pricing`. `not_applicable_
reason` answers *why this posting produces no CUSTOMER REVENUE*, and for a
metering-only tenant nothing on any work produces any, for a reason that has
nothing to do with how the work was sold: UBB does not bill their customers at
all. `fixed_task_pricing` says *the customer revenue for this event sits on the
Task instead* — which for that tenant names revenue nobody will ever collect and
sends a reader to look for a bill that will never be raised.

⚠ **THE ARGUMENT THIS PARAGRAPH USED TO MAKE EXPIRED IN #416, AND #418 RE-TOOK
THE TIE-BREAK AGAINST WHAT REPLACED IT RATHER THAN AGAINST THE OLD SENTENCE.**
It rested on *"for a metering-only tenant no Charge is created anywhere"*, and
concluded that naming the piece of work's pricing regime would imply revenue
sitting on a Charge that does not exist — true when slice 4 wrote it and false
one commit later. (The quotation is trimmed to the clause that carried the
argument; the rest of that sentence named a unit of work by a word the registry
has since retired.) A Charge IS created for a metering-only tenant's delivered
fixed-price work, deliberately and as that ticket's hardest-to-see acceptance
criterion; #417 then projected it onto a posting, so there is now a real row,
carrying a real amount, reachable from the very posting this rule is deciding a
reason for.

**THE RULING SURVIVES THAT, AND ON A NARROWER ARGUMENT THAN THE ONE IT LOST.**
`fixed_task_pricing` does not say *a Charge exists*; it says *the CUSTOMER
REVENUE for this event sits on the piece of work instead* — an instruction to a
reader about where to find what this event earned. For a tenant that does not
bill through UBB there is no customer revenue anywhere, on the Charge or off it:
the Charge is a recorded revenue and margin fact for the tenant's own reporting,
and nobody's customer is ever asked for the money. So the more specific value
would still send a reader to look for a bill that is never raised, which is
exactly the wrong answer the paragraph above refuses — and it would do it while
being, now, half true, which is worse than being plainly wrong. What changed is
that the counter-example is REACHABLE rather than hypothetical, and the value
that names the posture is what stays right for it. `test_why_a_price_does_not_
apply.py` states the row on its own, and
`test_the_postings_under_an_agreed_price_are_not_applicable.py` drives it end to
end through a tenant that has the Charge and not the bill.

**Why this is a function and not a registry `value_semantics` block.** The
registry can carry a decision rule as data, and the compiler proves such a rule
**total** over its declared boolean inputs. This rule is not: of the four
combinations of the two facts below, the fourth — a billing tenant running
event-priced work — has no `not_applicable_reason` at all, because the price
applies and the status is not `not_applicable`. A `value_semantics` block would
have to invent a value for that case, which is precisely the "answer nobody
decided" the totality proof exists to prevent. So the rule lives here, returns
`None` for the case that has no reason, and says so in the type.

**THE PRICE RESOLVER IS THE CALLER, AND #418 IS WHERE IT ARRIVED.** The
resolver reached three of the four price statuses — `known` where a rung priced
the event, `waived` where a margin was taken over a supplier cost UBB never
learned, and `unknown` where no rung answered — and could not reach the fourth,
because `not_applicable` is not a fact about resolution. It still is not: both
of this rule's inputs are facts about the SUBJECT, so the spine does not resolve
its way to this answer, it declines to consult the ladder at all. What made the
wiring possible was `work.Task.pricing_mode` (#415) and the thread that carries
it — `PricingSubject.pricing_mode` — down to the one function that decides both
statuses.

⚠ **THE REGIME DECIDES THE STATUS; THE POSTURE ONLY DECIDES THE REASON.** A
metering-only tenant's EVENT-PRICED work is priced exactly as it always was —
`known`, `waived` or `unknown`, whichever the ladder answers — because the
tenant's own margin reporting is what those prices are resolved for. Widening
`not_applicable` to every posting of such a tenant is a different ruling about
a different subject and belongs to the slice that owns the posture. So the two
booleans below are asked in that order for a reason: the second is the gate and
the first is the tie-break inside it.
"""
from core.vocabulary import (
    NOT_APPLICABLE_REASON_FIXED_TASK_PRICING,
    NOT_APPLICABLE_REASON_TENANT_NOT_BILLING,
    TENANT_PRODUCT_BILLING,
)


def bills_through_ubb(tenant) -> bool:
    """Whether UBB raises this tenant's customer bills at all.

    **THE PRODUCT IS WHAT THE QUESTION ASKS**, not whether any money record
    happens to exist — the same reading `api/v1/task_endpoints.py` gives it at
    the start gate, where a billing tenant's customer who has never been
    credited has no wallet row and is still a customer UBB bills. Both hold the
    product by reference from the generated vocabulary rather than spelling it,
    so a tenant posture stays one value with one spelling.

    Named here, beside the rule that consumes it, because this is the module
    that owns *why a subject produces no customer revenue* — and a resolver
    asking the question inline would be a second reading of a product flag with
    no name to grep for.
    """
    return TENANT_PRODUCT_BILLING in (tenant.products or [])


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

    Returns `None` for a billing tenant running event-priced work, which is
    the case where the price applies: there is no reason because the status is
    not `not_applicable`. A caller that has already decided the status is
    `not_applicable` can treat a `None` here as a contradiction, and the
    database will refuse the row either way — `not_applicable` with no reason is
    one of the seven combinations `ck_posting_pricing_status_agrees_with_the_price`
    rejects.
    """
    if not tenant_bills_through_ubb:
        # Posture wins, whatever the work's regime. See the module docstring.
        return NOT_APPLICABLE_REASON_TENANT_NOT_BILLING
    if sold_for_one_agreed_price:
        return NOT_APPLICABLE_REASON_FIXED_TASK_PRICING
    return None
