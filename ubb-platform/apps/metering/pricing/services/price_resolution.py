"""The one door a customer price resolves through (#363, ADR-0007 §2).

The price side's twin of `cost_settlement`, and deliberately its twin rather
than its generalisation. A posting recorded with `pricing_status = 'unknown'`
is waiting for a price no rule was written for when the call happened. Learning
one later is a **resolution** — completing a blank — which ADR-0007 §2 permits
exactly once, in one statement that moves the amount and the status together.
Changing a price that was already asserted is a **correction**, and a correction
belongs in a record beside the original rather than on top of it.

**WHY A SECOND DOOR AND NOT ONE DOOR WITH A PARAMETER.** The two pairs are
independent by construction and the database says so:
`trg_posting_declared_transitions` holds the cost pair,
`trg_posting_price_transitions` holds the price pair, their `WHEN` clauses name
disjoint columns, and dropping either leaves the other standing. Their permitted
moves are also different statements — `unresolved` to `known` there, `unknown`
to `known` here — and their zero-row answers are different sets, because the
price side has THREE terminal statuses and the cost side has one. A single
parametrised door would have to establish which pair it was looking at before it
could say anything, which is the shape the price pair's rule refused at the
database and it is no better one layer up.

**THE THREE TERMINAL ANSWERS ARE NOT ONE ANSWER.** A zero-row resolution is an
ANSWER rather than an error to retry, and which state the row is in is what a
caller sweeping a backlog needs:

* `known` — somebody got there first, or it was never unresolved;
* `waived` — a charge somebody decided not to pursue. **Never a candidate for a
  recovery**, because a decision is not information UBB is missing, and the loss
  it represents is reported as money rather than repaired;
* `not_applicable` — no customer revenue arises at this level at all.

⚠ **AND LIKE ITS TWIN, A RESOLUTION HERE DECLARES A CLOSED MONTH STALE** (#502,
slice 7 §8). The two per-customer monthly caches are built from these postings,
and a price learned long after the call lands at the instant the call happened.
An excluded price leaves a margin without part of its revenue — so **the
customer named unprofitable on a margin missing its revenue is the one who might
have been fine all along**, and a late price is the resolution most worth
letting reach a period that has closed. `queries.mark_backfill_dirty_period_for_posting` is the shared half.

Collapsing the last two would throw away exactly the distinction ruling 12c
exists to draw.

**AND IT IS THE ONLY WRITER, BECAUSE THE TABLE SAYS SO (#557).** The cost side
has an `ast` walk (`pricing/tests/test_cost_settlement.py`) that fails on any
other module writing a cost column: the transition trigger stops a second writer
corrupting a posting, but not resolving one, and then "this price is now known"
is decided in two places and tested in one. The owner re-scoped the price side's
answer (#557, `5785065807`): a behavioural or database rule, never a second
tree walk. So the price pair's trigger (`trg_posting_price_transitions`) admits
the move from `unknown` to `known` only on a statement this door has marked — a
transaction-local setting (:data:`PRICE_DOOR_SETTING`) set to
:data:`PRICE_DOOR_MARK` immediately before the one `UPDATE` below and cleared
immediately after. Any other writer, through any door — `save()`, a queryset,
raw SQL, a data migration — meets the refusal at the table.

It is a rule against a second writer by ACCIDENT, which is the risk the issue
names; code that sets the mark itself is not accidental, and it is one search
for the constant away. Every setter goes through
:func:`marked_as_the_price_door`: this door; the measurement script
(`scripts/measure_posting_transition_cost.py`), which times this statement in
bulk; and the test helper that asks whether the RULE admits the move at each
of ADR-0007 §2's three doors (`usage/tests/_helpers.as_the_price_door`).
"""
import enum
from contextlib import contextmanager, suppress

from django.db import DatabaseError, connection, transaction

from apps.metering.pricing.services.cost_settlement import (
    its_unit_takes_up_the_resolution)
from apps.metering.queries import mark_backfill_dirty_period_for_posting
from apps.metering.usage.models import Posting
from core.vocabulary import (
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_NOT_APPLICABLE,
    PRICING_STATUS_UNKNOWN,
    PRICING_STATUS_WAIVED,
)


#: THE SETTING THE PRICE PAIR'S TRIGGER READS, and the value that is this door
#: (#557). Named once, here, because the migration that installs the rule
#: (`usage/migrations/0002_the_database_rules.py`) freezes both literals and
#: every reader of them — the door, the measurement script, the tests — must
#: spell what the table asks for.
PRICE_DOOR_SETTING = "ubb.price_door"
PRICE_DOOR_MARK = "resolve_customer_price"


@contextmanager
def marked_as_the_price_door():
    """This door's mark, for the length of its one statement and no longer.

    Transaction-local (`set_config(..., true)`), so a mark can never outlive
    the transaction it was set in — and gone on the way out WHATEVER happened,
    so no later statement in the same transaction (a run resolving two hundred
    postings, say) inherits it:

    * the statement finished — the mark is cleared;
    * Python raised under it — the transaction is still usable, and the mark
      is cleared the same way;
    * the DATABASE refused the statement — the (sub)transaction is aborted,
      and the rollback that must follow reverts this transaction-local
      setting with everything else. A clear attempted in the aborted
      transaction would itself fail and report THAT instead of why the
      statement failed, so it is attempted and its failure suppressed; the
      door holds its statement in a savepoint of its own for exactly this.
    """
    _set_the_mark(PRICE_DOOR_MARK)
    try:
        yield
    except BaseException:
        with suppress(DatabaseError):
            _set_the_mark("")
        raise
    _set_the_mark("")


def _set_the_mark(value):
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, true)",
                       [PRICE_DOOR_SETTING, value])


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
    the columns so the record and the columns move together. Where it is
    omitted only the columns move. (Before the cutover, #190, that was a
    posting with no receipt this code could complete — an empty default, or
    one in an older shape, read and never rewritten. Since it the column has
    no default and every receipt is in the one shape, and the Resolution Run
    hands one over on every resolution.)

    Raises `Posting.DoesNotExist` if there is no such posting: none of the four
    outcomes would be true of it, and answering with one anyway is how a recovery
    comes to report progress against rows that are not there.
    """
    if billed_cost_micros is None:
        raise ValueError(
            "A price resolution carries an amount. NULL is what unknown means "
            "in this column, so it cannot also be what resolves it.")

    # Addressed through the column's constant and never spelled. It was the
    # retired name of the concept when this was written; #370 took the ratified
    # one and this line followed, rather than going quietly wrong on the day
    # the rename landed.
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
    # `trg_posting_price_transitions` refuses the statement outright if it
    # does not.
    #
    # AND `pricing_status_reason` IS CLEARED WITH THEM (#603), which IS the
    # cost side's shape: it qualifies the `unknown` being left behind, and the
    # same trigger refuses a `known` row that still carries one. The normal resolver
    # never hands this door a price whose reason is `negative_price_unsupported`
    # (`resolution_run.NOT_RETRIED`); the capability that one day carries a
    # negative price completes it through here, and the reason goes with it.
    #
    # ⚠ AND IT IS ONE TRANSACTION WITH EVERYTHING IT OWES, whatever the caller
    # holds — the cost door's rule, for the cost door's reason (#603; the
    # owner's review of #614): the resolved posting moves its unit's billed
    # total and unpriced count, and the two can never become separately
    # durable facts.
    #
    # AND IT IS MARKED AS THIS DOOR'S, which is the one thing the table now
    # admits the move on (#557): the setting is on for this statement only.
    with transaction.atomic():
        with marked_as_the_price_door():
            affected = (Posting.objects
                        .filter(pk=posting_id,
                                billed_cost_micros__isnull=True,
                                pricing_status=PRICING_STATUS_UNKNOWN)
                        .update(billed_cost_micros=billed_cost_micros,
                                pricing_status=PRICING_STATUS_KNOWN,
                                pricing_status_reason=None,
                                **completes_the_record))

        if affected > 1:
            # Unreachable while the filter above names a primary key, and kept
            # for what it makes loud if that ever stops being true: one
            # customer's price written quietly across several postings would
            # look exactly like a successful resolution from here — and raised
            # inside the transaction, it takes the write back.
            raise RuntimeError(
                f"a price resolution matched {affected} postings; it may only "
                f"ever match one (posting_id={posting_id})")

        if affected == 1:
            mark_backfill_dirty_period_for_posting(posting_id)
            its_unit_takes_up_the_resolution(
                posting_id, billed_cost_micros=billed_cost_micros)
            return PriceResolution.RESOLVED

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
