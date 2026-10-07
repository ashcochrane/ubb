"""Which tables carry an amount UBB may not have, and what says so (#348).

An **amount/status pair** is a nullable money column plus the status column
beside it that says why an amount is missing — the shape `core.cost_totals`
totals, and the reason a total over it has to declare what it left out. The
rules live there, and so does the type — :class:`core.cost_totals.AmountStatusPair`,
which is a parameter of those rules before it is anything else. **What lives
here is the list of pairs**, one entry per pair, because the rules are generic
and the columns are not.

**And the published wording of the supplier pair's amount, since #570**
(:data:`RESOLVED_SUPPLIER_COST_MEANING`, :func:`supplier_cost_total_meaning`),
at the foot of the module: it describes the pair's amount column wherever the
contract publishes it, and three layers publish it that may all import
``core.*`` and nothing nearer.

**Two pairs on one table, since #351**, and that is the case the parameter was
built for. They are independent: a posting can carry a settled supplier cost
and a customer price UBB could not resolve, or the reverse, so each pair
declares its own completeness key and a query totalling both writes two counts
that answer two different questions.

Two consequences worth stating, since they are why this is a module of its own
rather than four lines at the top of the seam:

* **The seam names no table.** A rule that holds a column name is a rule with
  one table's answer baked in, and the day a second table needs the same rule
  the honest options are a parameter or a second copy. `core.cost_totals` chose
  the parameter (#348); this file is where the argument comes from.
* **Everything that applies the rules can read it.** ADR-001 lets any product
  import ``core.*``, and forbids the kernel from importing a product at all —
  so a pair named beside metering's own model would be out of reach of
  `apps/platform`, which applies the unresolved rule to a running unit of work.
  That is not a hypothetical: `counts_as_unresolved` has five call sites in
  four modules today — two products, the kernel and the composition layer.

A pair is a claim about a table's schema, and nothing here checks it. The check
is the gate — `apps/platform/tests/test_no_bare_supplier_cost_aggregate.py`
sweeps for totals taken over the amount column without its count, and asks this
module which column that is rather than holding a copy of the name.
"""
from core.cost_totals import (
    UNPRICED_EVENT_COUNT_KEY, UNRESOLVED_EVENT_COUNT_KEY, AmountStatusPair,
)
from core.vocabulary import COSTING_STATUS_UNRESOLVED, PRICING_STATUS_UNKNOWN

#: The posting's supplier cost. `NULL` means UBB has not resolved this cost
#: (#317, ADR-0007 §2); `costing_status` is what separates that from a cost the
#: Event Type declares does not exist, which is also `NULL` and is not missing.
SUPPLIER_COST = AmountStatusPair(
    amount_column="provider_cost_micros",
    status_column="costing_status",
    unresolved_status=COSTING_STATUS_UNRESOLVED,
    count_key=UNRESOLVED_EVENT_COUNT_KEY,
)

#: The posting's customer price — the second pair, and the one #348 said was
#: coming (#351). `NULL` means UBB could not resolve this price; zero still
#: means priced at exactly nothing.
#:
#: ⚠ **THREE of the four `pricing_status` values carry a NULL amount and only
#: ONE of them is counted.** `unknown` is information UBB does not have, and it
#: is the reason a total over this column is a floor. `waived` is a charge
#: somebody decided not to pursue — a decision, reported as a loss (#147 §7.3),
#: so the revenue really is zero and the total really is complete. And
#: `not_applicable` is a subject that generates no customer revenue at this
#: level at all. Counting either of the last two would caveat every
#: metering-only tenant's every total forever, and a caveat that is always on
#: is a caveat nobody reads — the identical argument `core.cost_totals` makes
#: for the supplier pair's `not_applicable`.
#:
#: This asymmetry is exactly why the pair carries the ONE status that means
#: *not learned* rather than a list of statuses that null the amount: the
#: amount cannot tell the three apart, and only one of them is missing.
CUSTOMER_PRICE = AmountStatusPair(
    amount_column="billed_cost_micros",
    status_column="pricing_status",
    unresolved_status=PRICING_STATUS_UNKNOWN,
    count_key=UNPRICED_EVENT_COUNT_KEY,
)


#: WHAT THE SUPPLIER COST MEANS WHERE ONE EVENT PUBLISHES IT — the published
#: description of `provider_cost_micros` on every per-event schema and on the
#: `usage.recorded` payload (#570, and the owner's review of its PR #607: no
#: public `provider_cost_micros` is left undescribed by accident).
#:
#: **HERE, BECAUSE THREE LAYERS PUBLISH IT** — the tenant routes, a product's
#: own API module and the kernel's webhook payload — and ADR-001 lets every one
#: of them import `core.*` while forbidding a product or the kernel to import
#: the routes' module. One wording, imported, rather than three copies.
#:
#: True of every posting the column is on: a Charge's posting carries a settled
#: zero with no supplier behind it (`charge_projection.py`), and the amount is
#: present exactly when the status is `known`
#: (`ck_posting_costing_status_agrees_with_the_cost`).
RESOLVED_SUPPLIER_COST_MEANING = (
    "The supplier cost (COGS) UBB resolved for this event: the one canonical "
    "amount, whichever valid source supplied it — worked out from Cost Rates, "
    "or a reported figure that arrived on the transport the Event Type's "
    "publication admitted when the event was recorded (`provider_cost_micros` "
    "or `provider_response_cost_micros` on the recording request) — and zero "
    "on the posting that projects a Charge, which has no supplier behind it. "
    "`costing_status` beside it says whether it is settled: the amount is "
    "null wherever that status is not `known`."
)


def supplier_cost_total_meaning(over, *, can_hold_a_no_cost_event=True):
    """What `provider_cost_micros` means where a schema publishes a TOTAL of
    it: the same canonical amount, summed over the events `over` names, with
    what every such total leaves out said out loud.

    Every one of those totals is `core.cost_totals`' pair — the sum of the
    resolved column beside the count of `unresolved` rows — so one sentence is
    true of all of them, and only what they are taken over differs. ``over``
    finishes "summed over …".

    ``can_hold_a_no_cost_event`` is False where the events summed can never
    include one whose Event Type declares no cost — the waived postings, for
    the reason `metering.queries.get_waived_loss` records: a tenant-facing
    sentence describing that case there would explain one they can never meet.
    """
    no_cost = ("; one declared to carry no cost adds nothing and is not "
               "counted" if can_hold_a_no_cost_event else "")
    return (
        f"The total supplier cost (COGS) UBB resolved, summed over {over}: "
        "each event's canonical `provider_cost_micros`, whichever valid "
        "source supplied it. An event whose supplier cost is unresolved adds "
        "nothing and is counted in `unresolved_event_count` beside it, so the "
        f"total is a floor{no_cost}."
    )
