"""The one door a supplier cost settles through (#318, ADR-0007 §2).

A posting recorded with `costing_status = 'unresolved'` is waiting for a number
UBB did not have when the call happened. Learning it later is a **resolution** —
completing a blank — and ADR-0007 §2 permits that exactly once, in one statement
that moves the amount and the status together. Changing a number that was
already asserted is a **correction**, and a correction is not this: it belongs
in a record beside the original, not on top of it.

**This module is the only application-level writer of a cost resolution.** Not
by convention — `apps/metering/pricing/tests/test_cost_settlement.py` walks
living backend code and fails on any other `update`/`bulk_update` naming a cost
column, and on any raw `UPDATE ... SET` that names one. It carries exactly one
declared exception, the script that measures what the enforcement costs, and it
states its own blind spot: `setattr` plus `save()` names nothing an `ast` walk
can match, and needs nothing, because the posting refuses every update through
that door.

The database refuses every *other shape* of write through a trigger
(`usage/migrations/0037`), which is what makes the rule hold for a data
migration or a shell session too; what a trigger cannot do is notice that a
correct settlement has been written twice in two places, each tested once. That
half is what the walk is for.

**The first caller is the Resolution Run (#363)**, which is the order this door
was built in: proved and defended before there was anything to come through it,
so the first caller could not invent its own. A run learns a cost by re-resolving
the posting at its own instant and settles it here, one posting at a time, and it
hands over the completed receipt so the record and the columns move together.
"""
import enum

from apps.metering.usage.models import Posting
from core.vocabulary import COSTING_STATUS_KNOWN, COSTING_STATUS_UNRESOLVED


class Settlement(enum.Enum):
    """What the one statement did — never "it failed, try again".

    A zero-row settlement is an ANSWER, not an error to be retried: the row is
    in a state this door has nothing to do to. Which state it is in is the
    difference between "somebody got there first" and "this posting was never
    going to have a supplier cost", and a caller sweeping a backlog needs to
    tell those apart — one is a race it lost and the other is a row it should
    stop reading.
    """

    #: The blank was completed by this call. Exactly one row moved.
    SETTLED = "settled"
    #: The posting already carries a resolved amount. Its cost is `known`, and
    #: whether it was settled a moment ago or arrived that way is not something
    #: the table records — see the module docstring in the test.
    ALREADY_SETTLED = "already_settled"
    #: The posting is `not_applicable`: an Event Type that declares no cost, so
    #: there was never a blank here to complete.
    NEVER_UNRESOLVED = "never_unresolved"


def settle_provider_cost(*, posting_id, provider_cost_micros,
                         pricing_receipt=None):
    """Settle one posting's supplier cost, once, and say what happened.

    `provider_cost_micros` is the resolved amount in micros. **Zero is a
    resolved amount** — a supplier that charged nothing — and settles normally;
    `None` is not an amount at all and is refused before any statement runs,
    because `NULL` is precisely what "unresolved" means in this column.

    `pricing_receipt` is the posting's stored receipt with its **costing section
    completed** (`receipts.completed_receipt`), written in the SAME statement as
    the columns. It is optional and not decoration:

    * where it is given, the record and the columns move together, so the
      posting's receipt cannot come to say a cost is unresolved while the column
      beside it says the amount is known — the exact disagreement the receipt
      exists to remove;
    * where it is omitted, the posting has no receipt this code may complete —
      an empty default, or one written in an older shape, which the receipt's own
      ruling says is *read, never rewritten*. Such a posting's cost still
      settles. Refusing it would make a shape of record decide whether a supplier
      cost may be learned.

    Raises `Posting.DoesNotExist` if there is no such posting: neither outcome
    above would be true of it, and answering with one anyway is how a settlement
    sweep comes to report progress against rows that are not there.
    """
    if provider_cost_micros is None:
        raise ValueError(
            "A settlement carries an amount. NULL is what unresolved means in "
            "this column, so it cannot also be what resolves it.")

    # THE RECEIPT, ADDRESSED THROUGH THE COLUMN'S CONSTANT AND NEVER SPELLED.
    # Written when the column still carried the retired name of the concept and
    # a ratchet capped how many files might say it. #370 took that name and this
    # line came with it, which is what the indirection was for — a spelled
    # column would have gone quietly wrong on the day the rename landed.
    completes_the_record = ({Posting.RECEIPT_COLUMN: pricing_receipt}
                            if pricing_receipt is not None else {})

    # ADR-0007 §2's conditional update, and the reason it is one statement: the
    # WHERE clause holds the whole precondition, so two callers racing on the
    # same posting cannot both find it unresolved. A read followed by a write
    # would pass every test that did not run them concurrently.
    affected = (Posting.objects
                .filter(pk=posting_id,
                        provider_cost_micros__isnull=True,
                        costing_status=COSTING_STATUS_UNRESOLVED)
                .update(provider_cost_micros=provider_cost_micros,
                        costing_status=COSTING_STATUS_KNOWN,
                        unresolved_reason=None,
                        **completes_the_record))

    if affected == 1:
        return Settlement.SETTLED

    if affected > 1:
        # Unreachable while the filter above names a primary key, and kept for
        # what it makes loud if that ever stops being true: a settlement that
        # quietly wrote one supplier's amount across several postings would
        # look exactly like a successful one from here. ADR-0007 §2 asks for
        # this assertion by name.
        raise RuntimeError(
            f"a settlement matched {affected} postings; it may only ever match "
            f"one (posting_id={posting_id})")

    status = (Posting.objects.filter(pk=posting_id)
              .values_list("costing_status", flat=True).first())
    if status is None:
        raise Posting.DoesNotExist(f"no posting {posting_id} to settle")
    if status == COSTING_STATUS_UNRESOLVED:
        # The row says it is waiting and the statement above says it is not
        # there. One of the two is wrong, and neither answer below would be
        # true, so this reports the contradiction rather than picking a side.
        raise RuntimeError(
            f"posting {posting_id} reads unresolved but the settlement matched "
            f"no row; the conditional update and the table disagree")
    return (Settlement.ALREADY_SETTLED if status == COSTING_STATUS_KNOWN
            else Settlement.NEVER_UNRESOLVED)
