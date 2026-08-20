"""The one door a customer price resolves through (#363, ADR-0007 §2).

The price side's twin of `cost_settlement`, and deliberately its twin rather
than its generalisation. A posting recorded with `pricing_status = 'unknown'`
is waiting for a price no rule was written for when the call happened. Learning
one later is a **resolution** — completing a blank — which ADR-0007 §2 permits
exactly once, in one statement that moves the amount and the status together.
Changing a price that was already asserted is a **correction**, and a correction
belongs in a record beside the original rather than on top of it.

**WHY A SECOND DOOR AND NOT ONE DOOR WITH A PARAMETER.** The two pairs are
independent by construction and the database says so: `usage/migrations/0037`
holds the cost pair, `0039` holds the price pair, their `WHEN` clauses name
disjoint columns, and dropping either leaves the other standing. Their permitted
moves are also different statements — `unresolved` to `known` there, `unknown`
to `known` here — and their zero-row answers are different sets, because the
price side has THREE terminal statuses and the cost side has one. A single
parametrised door would have to establish which pair it was looking at before it
could say anything, which is the shape `0039` refused at the database and it is
no better one layer up.

**THE THREE TERMINAL ANSWERS ARE NOT ONE ANSWER.** A zero-row resolution is an
ANSWER rather than an error to retry, and which state the row is in is what a
caller sweeping a backlog needs:

* `known` — somebody got there first, or it was never unresolved;
* `waived` — a charge somebody decided not to pursue. **Never a candidate for a
  recovery**, because a decision is not information UBB is missing, and the loss
  it represents is reported as money rather than repaired;
* `not_applicable` — no customer revenue arises at this level at all.

Collapsing the last two would throw away exactly the distinction ruling 12c
exists to draw.

**⚠ THERE IS NO `ast` WALK OVER THE TREE FOR THIS PAIR, AND THE COST SIDE HAS
ONE.** `pricing/tests/test_cost_settlement.py` walks living backend code and
fails on any other module writing a cost column, because a second writer cannot
corrupt a posting — the trigger sees to that — but it can perfectly well resolve
one, and then "this price is now known" is decided in two places and tested in
one. That argument holds here word for word, and the walk is not extended in
this commit: it is a gate over the whole tree with its own vacuity controls and
its own excused files, and copying it with three columns swapped is the
duplication `docs/conventions/testing.md` refuses. What this module has instead
is the database rule, which holds through every door, and being the only caller
of its own statement. **Extending that walk to a second column set is a
separable ticket and is recorded here rather than left as an absence.**
"""
import enum

from apps.metering.usage.models import Posting
from core.vocabulary import (
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_NOT_APPLICABLE,
    PRICING_STATUS_UNKNOWN,
    PRICING_STATUS_WAIVED,
)


class PriceResolution(enum.Enum):
    """What the one statement did — never "it failed, try again"."""

    #: The blank was completed by this call. Exactly one row moved.
    RESOLVED = "resolved"
    #: The posting already carries a resolved price. Whether it was resolved a
    #: moment ago or arrived that way is not something the table records.
    ALREADY_RESOLVED = "already_resolved"
    #: The posting's charge was waived — a decision somebody made not to pursue
    #: it. It is not a blank and completing it would be overturning a decision.
    WAIVED = "waived"
    #: The posting generates no customer revenue at this level at all, so there
    #: was never a blank here to complete.
    NOT_APPLICABLE = "not_applicable"


def resolve_customer_price(*, posting_id, billed_cost_micros,
                           pricing_receipt=None):
    """Resolve one posting's customer price, once, and say what happened.

    `billed_cost_micros` is the resolved amount in micros. **Zero is a resolved
    price** — priced at exactly nothing — and resolves normally; `None` is not a
    price at all and is refused before any statement runs, because `NULL` is
    precisely what "could not resolve" means in this column.

    `pricing_receipt` is the posting's stored receipt with its **pricing section
    completed** (`receipts.completed_receipt`), written in the SAME statement as
    the columns so the record and the columns move together. Omitted where the
    posting carries no receipt this code may complete — an empty default, or one
    in an older shape, which is read and never rewritten.

    Raises `Posting.DoesNotExist` if there is no such posting: none of the four
    outcomes would be true of it, and answering with one anyway is how a recovery
    comes to report progress against rows that are not there.
    """
    if billed_cost_micros is None:
        raise ValueError(
            "A price resolution carries an amount. NULL is what unknown means "
            "in this column, so it cannot also be what resolves it.")

    # Addressed through the column's constant and never spelled: the column
    # still carries the retired name of the concept, and this follows the
    # rename rather than going quietly wrong on the day it lands.
    completes_the_record = ({Posting.RECEIPT_COLUMN: pricing_receipt}
                            if pricing_receipt is not None else {})

    # ADR-0007 §2's conditional update, one statement, with the whole
    # precondition in the WHERE clause — so two callers racing on the same
    # posting cannot both find it unknown. A read followed by a write would pass
    # every test that did not run them concurrently.
    #
    # ⚠ `not_applicable_reason` IS NOT TOUCHED, WHICH IS NOT THE COST SIDE'S
    # SHAPE. There the reason column is cleared by the settlement, because it
    # qualifies the status being left behind. Here the reason belongs to
    # `not_applicable`, a status this statement can neither start from nor
    # arrive at, so a row reaching this door has a null reason already and
    # `0039` refuses the statement outright if it does not.
    affected = (Posting.objects
                .filter(pk=posting_id,
                        billed_cost_micros__isnull=True,
                        pricing_status=PRICING_STATUS_UNKNOWN)
                .update(billed_cost_micros=billed_cost_micros,
                        pricing_status=PRICING_STATUS_KNOWN,
                        **completes_the_record))

    if affected == 1:
        return PriceResolution.RESOLVED

    if affected > 1:
        # Unreachable while the filter above names a primary key, and kept for
        # what it makes loud if that ever stops being true: one customer's
        # price written quietly across several postings would look exactly like
        # a successful resolution from here.
        raise RuntimeError(
            f"a price resolution matched {affected} postings; it may only ever "
            f"match one (posting_id={posting_id})")

    status = (Posting.objects.filter(pk=posting_id)
              .values_list("pricing_status", flat=True).first())
    if status is None:
        raise Posting.DoesNotExist(f"no posting {posting_id} to price")
    if status == PRICING_STATUS_UNKNOWN:
        # The row says it is waiting and the statement above says it is not
        # there. One of the two is wrong, and no answer below would be true, so
        # this reports the contradiction rather than picking a side.
        raise RuntimeError(
            f"posting {posting_id} reads unknown but the resolution matched no "
            f"row; the conditional update and the table disagree")
    return {
        PRICING_STATUS_KNOWN: PriceResolution.ALREADY_RESOLVED,
        PRICING_STATUS_WAIVED: PriceResolution.WAIVED,
        PRICING_STATUS_NOT_APPLICABLE: PriceResolution.NOT_APPLICABLE,
    }[status]
