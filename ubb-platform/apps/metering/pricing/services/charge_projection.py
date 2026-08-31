"""How a Charge reaches the money rails — as exactly one marked posting (#417,
spec §12).

**A PROJECTION, NOT "A POSTING WITH A FLAG", AND THE THREE REASONS ARE WHY THIS
MODULE EXISTS AT ALL.**

1. **Re-derivability.** `pricing.Charge` is canonical and correctable by a
   compensating record; a posting is immutable AND undeletable. A wrong posting
   can be rebuilt from the Charge that produced it. A wrong canonical event
   could never be rebuilt from anything, which is why #416 refused a
   system-generated posting as the canonical record.
2. **The platform fee becomes an EXPLICIT property of this projection** rather
   than something a synthetic row inherits by accident — see
   :func:`project_the_charge`'s note on the accumulation, and
   `test_the_charge_reaches_the_rails_as_one_marked_posting.py`, which proves
   what UBB's fee is charged on rather than inferring it from the fee formula.
3. **Catalogue compatibility.** The Charge holds the policy provenance a rating
   record needs; the posting is marked *system-generated* by its own `kind`
   instead of impersonating a recognised tenant Event Type, which would be
   unrecognised at the catalogue and quarantined.

**GROUPING FIELD INHERITANCE IS WHAT MAKES THIS NEARLY FREE.** The ten slots
already reach every posting from the unit of work, so a charge projection
carrying the same ten nets this revenue against that same unit's COGS in the
same bucket — *margin by region* keeps working with no new code, no
re-implementation of inheritance and no second analytics path. A separate
revenue entity would have owed all three.

**THE PROJECTION PRESERVES THE MONEY KEY.** The posting's id **is** the
exactly-once key every money path already uses — `usage_deduction:{id}` in the
wallet ledger, the repair sweep's column anti-join — and that is sound because
the chain *unit of work → Charge → posting → deduction* is 1:1 at every hop.
The amount-mismatch guard in `wallets/operations.py::draw_down_usage` still
protects it: a second debit under one key is refused and logged rather than
applied.

⚠ **THIS MODULE IS IN `pricing` AND WRITES A `usage` ROW, WHICH IS THE
`cost_settlement` SHAPE.** Two service modules in this app already write
`usage.Posting` — `cost_settlement` and `price_resolution`, one `UPDATE` each —
and `resolution_run` reads it. A posting is metering's record either way, and
what decides which app a writer lives in is which concept owns the statement.
The statement here is *what a Charge looks like on the rails*, and the Charge is
this app's.

⚠ It is nonetheless the first INSERT of a posting outside
`usage.services.usage_service`, which is worth saying rather than leaving for a
reader to notice: the two writers above complete a column on a row the recording
path created, and this one creates the row. What makes that admissible is that
the row it creates is the one kind no caller can report.
"""
from apps.metering.usage.models import Posting
from apps.platform.events.outbox import write_event
from apps.platform.events.schemas import UsageRecorded
from core.vocabulary import (
    COSTING_STATUS_KNOWN,
    PRICING_STATUS_KNOWN,
    USAGE_EVENT_KIND_TASK_CHARGE,
)

#: WHAT A CHARGE PROJECTION COSTS UBB'S TENANT — nothing, and it is written as a
#: number rather than left absent.
#:
#: `provider_cost_micros = 0` with `costing_status = known` is the column's own
#: distinction used exactly as it was built: NULL means *not resolved* and zero
#: means *resolved, and it was exactly nothing*. A charge projection is the
#: second. There is no supplier behind it to learn a cost from — the supplier
#: work a fixed-price unit really did burn is on the metered postings beside
#: this one — so leaving it NULL would put a permanent unresolved row in every
#: recovery queue for a cost that does not exist.
PROVIDER_COST_OF_A_PROJECTION = 0

#: THE TEN SLOTS, READ OFF THE MODEL BEING WRITTEN rather than counted out, so a
#: slot arriving on the record reaches the projection with no edit here. The
#: same construction `charge_service._GROUPING_SLOTS` uses, for the same reason,
#: and deliberately not an import of it: this one is a fact about `Posting` and
#: that one is a fact about `Charge`, and the day the two tables disagree about
#: how many slots exist is the day one shared constant would be silently wrong
#: for one of them.
#:
#: ⚠ SO AN ELEVENTH POSTING SLOT WITH NO `Charge` TWIN RAISES `AttributeError`
#: AT WRITE TIME, AND THAT IS THE INTENDED FAILURE. Reading the slots off the
#: CHARGE instead would project nine of ten silently, which is #361's lesson
#: exactly — walk the record you are writing and let a missing value raise,
#: because the alternative is a bucket quietly losing one of its axes. The two
#: tables are widened together or the widening stops here, loudly.
_GROUPING_SLOTS = tuple(
    field.name for field in Posting._meta.get_fields()
    if field.name.startswith("grouping_field_"))


def project_the_charge(charge):
    """Write ``charge``'s one posting and put it on the rails.

    **EXACTLY ONE POSTING, AND THE DATABASE IS WHAT SAYS SO.** The posting
    takes the Charge's own derived idempotency key, so
    `uq_usage_event_idempotency_v2` makes a second projection of one Charge an
    `IntegrityError` rather than a second row moving the money twice. That is
    the third of the three guards #416 named — the winning transition, the
    partial uniqueness on `ubb_charge`, and this one — and it is the only one
    that holds when the other two are bypassed.

    **WHAT THE ROW CARRIES, AND WHY EACH ANSWER IS THE ONE IT IS:**

    * `billed_cost_micros` is the Charge's amount and `pricing_status` is
      `known`. This is the one posting under a fixed-price unit of work that
      DOES carry customer revenue; every metered posting beside it carries none,
      and #418 is what makes those say `not_applicable` rather than zero.
    * `provider_cost_micros` is zero and settled — see
      `PROVIDER_COST_OF_A_PROJECTION` above.
    * **No measurement record at all.** `usage_service` writes one for every
      metered posting, empty bag or not, precisely so that ABSENCE keeps its own
      meaning: *the posting kind that never had measurements*. This is that
      kind, and it is the first row in the repository to use the meaning.
      `measurements_status` then answers `not_applicable` off the kind, which is
      the registry's own rule and needs nothing here.
    * `event_type` and `provider` are empty, which is the system-generated
      marking working. A synthetic Event Type would be a code no tenant
      declared; `kind` says what this row is instead, and nothing has to
      recognise a catalogue entry that was never registered.
    * The ten slots come from the CHARGE and not from the unit of work, because
      the Charge froze them at the moment the money became owed and the unit's
      row is mutable.
    * `task_type` comes from the unit of work and `subtask_type` is empty,
      which is not an omission: `ck_task_agreed_price_only_on_a_whole_fixed_
      unit` admits an agreed price only on a WHOLE unit of work, so a Charge's
      unit never has a parent and there is no contained altitude to name.
    * `effective_at` is `charged_at` — when delivery was declared. The revenue
      lands in the period the delivery did, which is the whole of §11's
      dated-at-delivery ruling carried onto the rail that reads this column.
    * `pricing_receipt` is left empty. A receipt whose subject is a Charge is
      #418's, and writing a half of one here would be a record explaining an
      amount in a shape no reader knows.

    ⚠ **§12'S FOURTH CLAUSE HAS NO SUBJECT ANY MORE, AND IT IS NOT SILENTLY
    SATISFIED.** It asks for the posting's nameless inline quantity to be null —
    the column #272 deleted, because one integer per posting could only ever
    describe one thing and an event carrying both an input and an output amount
    was inexpressible under it. What replaced it is the measurement record,
    keyed by declared quantity. So there is no column here to leave null, and
    what the clause MEANS is the bullet above: this posting was never measured,
    and says so by having no child at all rather than by carrying an empty one.
    Written down rather than ticked off, because an acceptance criterion naming
    a column that does not exist reads as satisfied from either side. (The
    clause's own word is a retired term this file may not spell; naming it by
    the operation that removed it is the ratified way past that.)

    **THE PLATFORM FEE IS CHARGED ON THIS AMOUNT, AND THAT IS A DECISION RATHER
    THAN AN INHERITANCE.** `TenantBillingService.accumulate_usage` adds a
    posting's `billed_cost_micros` to the period total UBB's own fee is a
    percentage of, and this row reaches it by the same route every metered
    posting does — the `usage.recorded` payload below. Making the projection a
    real posting is what puts the fee on fixed-price revenue; a revenue record
    that stayed off this rail would have exempted it silently.

    ⚠ **A COMPENSATING CHARGE IS REFUSED HERE, AND THE REASON IS MEASURED
    RATHER THAN STYLISTIC.** `apps/billing/handlers.py` acts only on
    `billed_cost_micros > 0`, so a negative posting reaches the wallet, the
    period total and the live spend counter as nothing at all — a projection
    of a correction would look like a reversal and move no money. Correcting a
    charge on the rails needs a refund path rather than a negative posting, and
    that is a real gap this ticket does not close: `charge_service.compensate`
    has no route either (#416 left it needing an operator surface and a record
    of who acted), so nothing can reach this refusal from outside a test today.
    Refusing loudly is what stops the gap being closed by accident.

    Must be called inside @transaction.atomic, with the transition that earned
    the Charge — the same requirement, for the same reason, as writing the
    Charge itself: a crash between the two would leave a charge that never
    reached the money.
    """
    if charge.compensates_id is not None:
        raise ValueError(
            "a compensating charge is not projected onto a posting: the "
            "money rails ignore a non-positive amount, so the reversal would "
            "move nothing while looking like it had")
    task = charge.task
    posting = Posting.objects.create(
        tenant_id=charge.tenant_id,
        customer_id=task.customer_id,
        idempotency_key=charge.idempotency_key,
        kind=USAGE_EVENT_KIND_TASK_CHARGE,
        currency=charge.currency,
        billed_cost_micros=charge.amount_micros,
        pricing_status=PRICING_STATUS_KNOWN,
        provider_cost_micros=PROVIDER_COST_OF_A_PROJECTION,
        costing_status=COSTING_STATUS_KNOWN,
        task_id=charge.task_id,
        task_type=task.task_type,
        effective_at=charge.charged_at,
        # PINNED ON THE ROW, exactly as the recording path pins it, because the
        # drawdown repair sweep's comment calls the owner "pinned on the event"
        # and only falls back to re-resolving for rows written before the
        # column existed. A projection written today with nothing there would
        # be a new row taking a path built for old ones.
        billing_owner_id=task.customer.resolve_billing_owner().id,
        **{slot: getattr(charge, slot) for slot in _GROUPING_SLOTS})
    write_event(UsageRecorded(
        tenant_id=str(charge.tenant_id),
        customer_id=str(task.customer_id),
        event_id=str(posting.id),
        cost_micros=posting.billed_cost_micros,
        provider_cost_micros=posting.provider_cost_micros,
        costing_status=posting.costing_status,
        billed_cost_micros=posting.billed_cost_micros,
        pricing_status=posting.pricing_status,
        task_id=str(charge.task_id),
        billing_owner_id=str(posting.billing_owner_id),
        effective_at=posting.effective_at.isoformat()))
    # ⚠ THE DISCRIMINATOR IS DELIBERATELY NOT ON THE PAYLOAD, and the payload's
    # own rule is what decides it: `costing_status` joined this event because
    # two products count their exclusions off it, and the field beside it
    # records that a fact "joins the payload the day a subscriber needs it".
    # No subscriber filters on the kind today — the measure that will is
    # `recorded_events`, which exists as vocabulary and as nothing else, and
    # G14's row is now owed by the slice that builds it. A field nothing reads
    # is a field that goes stale, and this one would go stale on the wire.
    return posting
