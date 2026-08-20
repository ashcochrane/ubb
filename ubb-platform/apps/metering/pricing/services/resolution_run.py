"""A Resolution Run — one recovery mechanism, scoped by construction (#363).

Four documents each described a way to put right what UBB could not resolve at
the time, and none owned building one. This is the one mechanism they become,
covering the three recovery paths that do not move money — a supplier cost UBB
never learned, a customer price no rule was written for, and the decision record
for a correction — because all three are the same act: **completing a `NULL`
beside a status that says the field was never resolved.**

**⚠ MEMBERSHIP IS THE STATUS, WHICH IS WHY THERE IS NOTHING TO GET RIGHT.** The
candidate set is built from `core.amount_status_pairs` — each pair names the ONE
status meaning *not learned* — so a run reaches only postings whose own status
says they were never resolved. There is no flag to set correctly and no
predicate to evaluate, and therefore **no way for a run to touch a number that
already exists**. Take the selector away entirely and that property survives,
because it was never the selector doing it.

`waived` is outside a run by the same construction rather than by an exclusion
somebody remembered to write: it is not the pairs' unresolved status, so it is
not in the set. A waived charge is a decision somebody made; `unknown` is
information UBB does not have. What waiving costs is reported as money
elsewhere, not repaired here.

**THE SELECTOR IS THREE AXES AND NEVER A PREDICATE.** A date range, a customer,
an Event Type — the axes the rule ladder itself selects on. A filter rather than
a button, and not for convenience: a tenant onboarding in August who backfills
July has postings unresolved for two different causes, and *everything it
matches* would apply one repair to postings needing another. An arbitrary
predicate is the check the construction argument above just refused.

**NOTHING IS BACKDATED, AND THAT IS WHY THIS IS SAFE.** A run re-resolves each
posting **at the posting's own instant** through `pricing_service.resolve_price`,
so a rule written today — which can only take effect from today forward — does
not reach a posting from July. What a run recovers is what is genuinely
resolvable at that past instant with configuration that carries no effective
moment of its own: the markup rung, and an Event Type's costing declaration. A
backdated rate is the one input that would break historical accuracy, and no
path anywhere accepts one.

**A RUN MOVES NO MONEY.** No invoice, no credit note, no charge, no wallet
movement, no call to Stripe. It completes what was never resolved and records
that it did; what recovering is worth is a projection over these records, and the
tenant then acts through the money path UBB already has. Stripe owns the billing
engine and UBB never reimplements it.

**IT IS IDEMPOTENT BY CONSTRUCTION, NOT BY A CHECK.** Everything a run completes
leaves the candidate set the moment it completes, so running the same selector
again reaches the postings the first run could not repair and nothing else. ⚠
**That is also why no refusal may be added above it.** A guard that turned "this
selector has already been run" or "there is nothing to do" into an error would
refuse the second call forever while every acceptance criterion still read as
satisfied — a refusal is a statement about work still to do, and this programme
has paid for that exact shape once already. A run that completes nothing answers
with an outcome saying so.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from django.db.models import Q

from apps.metering.pricing.models import Rate, ResolutionRun
from apps.metering.pricing.receipts import (
    RESOLUTION_RUN_KEY, SECTIONS, ReceiptSubject, Resolution,
    completed_receipt, recorded_quantities, written_in_the_current_shape)
from apps.metering.pricing.services.cost_settlement import (
    Settlement, settle_provider_cost)
from apps.metering.pricing.services.price_resolution import (
    PriceResolution, resolve_customer_price)
from apps.metering.pricing.services.pricing_service import (
    PricingSubject, resolve_price)
from apps.metering.usage.models import Posting
from apps.platform.audit.actors import SYSTEM, get_current_actor
from core.amount_status_pairs import CUSTOMER_PRICE, SUPPLIER_COST
from core.vocabulary import (
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_NOT_APPLICABLE,
    PRICING_RECEIPT_SUBJECT_TYPE_USAGE_EVENT,
)

#: THE PAIRS A RUN RECOVERS, WHICH IS EVERY PAIR THERE IS. Read from the
#: registry rather than listed here, so a third amount UBB may not have joins a
#: run's reach on the day it is declared rather than on the day somebody
#: remembers this module.
PAIRS = (SUPPLIER_COST, CUSTOMER_PRICE)

#: WHICH SECTION OF THE RECEIPT EXPLAINS WHICH PAIR OF COLUMNS, joined on the
#: amount column rather than by a table written here. The receipt's own
#: `SECTIONS` already takes its amount key from the pair; joining on it means
#: the two can never come to disagree, and it is the same join the database rule
#: that seals a receipt makes.
PAIR_BY_SECTION = {name: pair
                   for name, rules in SECTIONS.items()
                   for pair in PAIRS
                   if pair.amount_column == rules.amount_key}

#: HOW MANY POSTINGS ONE RUN TAKES.
#:
#: A run is synchronous — it is an ADMIN pressing a button and reading what
#: happened — and re-resolving a posting costs a handful of queries, so an
#: unbounded run over a tenant's whole history is a request that never returns.
#: The bound is safe precisely BECAUSE membership is the status: everything a
#: run completes leaves the candidate set, so the next run continues where this
#: one stopped and there is no cursor to carry and nothing to get wrong. What is
#: NOT safe is a bound nobody is told about, which reads as *"that was all of
#: them"* — so a run that hit it says so in `more_to_do`.
MAXIMUM_POSTINGS_PER_RUN = 200


@dataclass(frozen=True)
class RunSelector:
    """The three axes, as the caller stated them.

    Every field is optional and an omitted one means *unpinned on this axis* —
    the same reading a rule's own selectors take, where an empty selector
    matches anything. There is no fourth field, and adding one that took a
    condition would be the arbitrary predicate this mechanism refuses.
    """

    #: The posting's own effective instant, half-open: `[from, to)`. The same
    #: convention a rule's `[valid_from, valid_to)` window uses, so a boundary
    #: instant belongs to exactly one of two adjacent ranges and a tenant
    #: running July then August cannot repair one posting twice or miss one.
    selected_from: Optional[datetime] = None
    selected_to: Optional[datetime] = None
    selected_customer: Any = None
    selected_event_type: str = ""


def never_resolved_condition():
    """The membership predicate, built from the pairs rather than from literals.

    Public because the property worth asserting is that **this is all there
    is**: no exclusion of settled rows, no exclusion of `waived`, nothing about
    a flag. A test that reads this can show the set is constructed rather than
    filtered, which prose cannot.
    """
    predicate = Q()
    for pair in PAIRS:
        predicate |= Q(**{pair.status_column: pair.unresolved_status})
    return predicate


def candidates(tenant, selector):
    """The postings a run may reach, in the order it will reach them.

    ⚠ **THE MEMBERSHIP TERM IS APPLIED SEPARATELY FROM THE SELECTOR AND THAT IS
    VISIBLE HERE ON PURPOSE.** The three axes narrow a set that was already only
    the never-resolved; they do not compose into one condition where a reader
    has to work out which term is load-bearing. Delete every `if` below and the
    query still cannot reach a posting that has an amount.

    Ordered oldest-first so a bounded run works forward through a backlog, and
    tie-broken on the id so two runs over the same data take the same postings —
    an unbroken tie is handed to the query plan, which is how a repair becomes
    dependent on the planner.
    """
    postings = (Posting.objects.filter(tenant=tenant)
                .filter(never_resolved_condition()))
    if selector.selected_from is not None:
        postings = postings.filter(effective_at__gte=selector.selected_from)
    if selector.selected_to is not None:
        postings = postings.filter(effective_at__lt=selector.selected_to)
    if selector.selected_customer is not None:
        postings = postings.filter(customer=selector.selected_customer)
    if selector.selected_event_type:
        postings = postings.filter(event_type=selector.selected_event_type)
    return postings.order_by("effective_at", "id")


def execute(*, tenant, selector, actor=None):
    """Run one recovery and record it. Returns the :class:`ResolutionRun`.

    **Must run inside the caller's transaction**, which is what makes a run all
    or nothing: a failure part way through leaves no completed postings and no
    record claiming otherwise. That is the honest shape for an act that cannot
    be undone.

    ⚠ **THE RUN'S ID IS DECIDED BEFORE THE RECORD IS.** Each receipt a run
    completes names the run in its provenance, and the receipts are written
    before the outcome is known — so the id is generated here and the record is
    created at the end carrying it, exactly as the recording path generates a
    posting's id before it prices one. The record is written once and never
    updated (a database rule refuses one), so its columns cannot be filled in as
    the run goes.
    """
    run_id = uuid.uuid4()

    # ONE ID MORE THAN THE BOUND, WHICH IS HOW `more_to_do` IS ANSWERED WITHOUT
    # A SECOND COUNT. A `COUNT(*)` over the same predicate would be a second
    # query answering a question this one already knows.
    reachable = list(candidates(tenant, selector)
                     .values_list("id", flat=True)[:MAXIMUM_POSTINGS_PER_RUN + 1])
    more_to_do = len(reachable) > MAXIMUM_POSTINGS_PER_RUN
    taking = reachable[:MAXIMUM_POSTINGS_PER_RUN]

    costs_settled = prices_resolved = left_unresolved = 0
    for posting_id in taking:
        settled, resolved = _complete(posting_id, run_id)
        costs_settled += int(settled)
        prices_resolved += int(resolved)
        left_unresolved += int(not (settled or resolved))

    # THE ACTOR IS RESOLVED THE WAY THE LEDGER RESOLVES IT, and from the same
    # contextvar the auth seam captured — so this record and the
    # `resolution_run.executed` entry beside it cannot name two different
    # people. An unattributable run still records, under the reserved `system`
    # kind, because losing the fact that a run happened is worse than losing who
    # ran it; the route above this refuses everything below ADMIN, so that state
    # is a background caller rather than an unauthenticated one.
    actor = actor if actor is not None else get_current_actor()
    return ResolutionRun.objects.create(
        id=run_id, tenant=tenant,
        actor_kind=actor.kind if actor is not None else SYSTEM,
        actor_id=actor.id if actor is not None else "",
        actor_display=actor.display if actor is not None else "",
        selected_from=selector.selected_from,
        selected_to=selector.selected_to,
        selected_customer=selector.selected_customer,
        selected_event_type=selector.selected_event_type or "",
        postings_examined=len(taking),
        costs_settled=costs_settled,
        prices_resolved=prices_resolved,
        postings_left_unresolved=left_unresolved,
        more_to_do=more_to_do)


def _complete(posting_id, run_id):
    """Re-resolve one posting and complete whatever was never resolved.

    Returns `(a cost settled, a price resolved)`. Each completion is one
    statement through the pair's own door, and the two pairs are independent:
    the cost may settle while the price stays unknown, or the reverse, or both
    may move, or neither.

    ⚠ **THE ROW IS RE-READ UNDER A LOCK, AND THE STATUSES ARE RE-ASKED AFTER
    IT.** The candidate ids were selected a moment ago; between then and now a
    concurrent run may have completed one. The doors would answer that safely on
    their own — their `WHERE` clauses hold the whole precondition — but the
    receipt each door carries is computed from a record read here, and two
    completions computed from the same stale read would each be missing the
    other's. The lock is what makes the read and the write one decision.
    """
    # ⚠ `of=("self",)` LOCKS THE POSTING AND NOTHING ELSE. `select_related`
    # makes the statement an INNER JOIN, and a bare `FOR UPDATE` over a join
    # locks a row in EVERY joined table — so this would have taken locks on the
    # customer and the tenant, in the wrong order: `docs/conventions/
    # coding-standards.md` puts Customer BEFORE Posting in the canonical global
    # order, and taking them the other way round is how two paths deadlock. The
    # join is here to save two queries per posting on a loop that may run two
    # hundred times; `of` is what keeps it from also being a lock.
    posting = (Posting.objects.select_for_update(of=("self",))
               .select_related("tenant", "customer").get(pk=posting_id))
    stored = getattr(posting, Posting.RECEIPT_COLUMN)

    completable = {name for name, pair in PAIR_BY_SECTION.items()
                   if getattr(posting, pair.status_column)
                   == pair.unresolved_status}
    if not completable \
            or _the_record_cannot_account_for_a_completion(posting, stored):
        return False, False

    resolved = resolve_price(_subject_of(posting, stored),
                             posting.effective_at)

    settled_cost = _settle_the_cost(posting, stored, resolved, run_id) \
        if "costing" in completable else False
    # The stored record moves when the cost settles, and the price completion
    # is computed from what is on the row NOW rather than from the read above —
    # otherwise the price's statement would carry a receipt with the cost's
    # completion missing, and the sealing rule would refuse it for having
    # dropped a field that was never unresolved.
    if settled_cost:
        posting.refresh_from_db()
        stored = getattr(posting, Posting.RECEIPT_COLUMN)
    resolved_price = _resolve_the_price(posting, stored, resolved, run_id) \
        if "pricing" in completable else False

    return settled_cost, resolved_price


def _the_record_cannot_account_for_a_completion(posting, stored):
    """⚠ TWO WAYS A RECORD CANNOT SUPPORT A RECOVERY, AND BOTH LEAVE THE POSTING
    ALONE. Each was a live defect before it was a branch.

    **ONE — THE RECORD CANNOT NAME THE ACT THAT COMPLETED IT.** A receipt in an
    older shape, or the empty default, is one `completed_receipt` may not touch:
    *read, never rewritten*. Without this branch the doors still moved the money
    columns and simply carried no receipt — so a posting was priced, the
    outcome counted it, and **nothing anywhere named the run that did it**. A
    number a recovery changed has to be explicable by the act that changed it,
    and half of that claim is worse than none: these are precisely the oldest
    postings, which is where a recovery is most likely to be questioned.

    **TWO — AN UNRESOLVED COST WHOSE RECORD KEPT NO QUANTITIES.** A run
    re-resolves from the receipt — never from the measurement rows, which prune
    — and the receipt keeps the quantities a recovery needs in exactly one case:
    an unresolved cost whose quantities matched no rule (`uncosted_quantities`,
    #350). The other cause of an unresolved cost is a supplier declared to
    report its own figure that never did, and that branch of the engine records
    **no quantities at all**, because what recovers it is the figure arriving
    rather than a re-costing. Re-resolved from an empty bag the engine computes
    a cost of exactly zero, and every condition for settling it is then
    satisfied: status `known`, amount a number, door admits, trigger admits,
    receipt seals over it. A posting that measured a million tokens would have
    settled at nothing, permanently.

    ⚠ The second is asked of the COST side only, and that is not an omission.
    Where the cost is settled, `_subject_of` states the figure the record
    already holds, so an empty bag is harmless: no rule matches nothing, and a
    margin over the stated basis is the right answer for a posting that measured
    nothing. It is only an unresolved cost that would be *computed* from the bag.

    Where either holds, the run examines the posting, completes nothing, and
    reports it still unresolved — which is the true answer about it.
    """
    if not written_in_the_current_shape(stored):
        return True
    return (posting.costing_status
            == PAIR_BY_SECTION["costing"].unresolved_status
            and not recorded_quantities(stored))


def _settle_the_cost(posting, stored, resolved, run_id):
    """Settle the supplier cost where the re-resolution now believes one."""
    if resolved["costing"]["status"] != SECTIONS["costing"].settled:
        return False
    outcome = settle_provider_cost(
        posting_id=posting.pk,
        provider_cost_micros=resolved["totals"]["provider_cost_micros"],
        pricing_receipt=_receipt_completing("costing", stored, resolved, run_id))
    return outcome is Settlement.SETTLED


def _resolve_the_price(posting, stored, resolved, run_id):
    """Resolve the customer price where the re-resolution now decides one."""
    if resolved["pricing"]["status"] != SECTIONS["pricing"].settled:
        return False
    outcome = resolve_customer_price(
        posting_id=posting.pk,
        billed_cost_micros=resolved["totals"]["billed_cost_micros"],
        pricing_receipt=_receipt_completing("pricing", stored, resolved, run_id))
    return outcome is PriceResolution.RESOLVED


def _receipt_completing(section, stored, resolved, run_id):
    """The stored receipt with one section completed, naming the run that did it.

    It asks nothing about the record's shape, and that is the point rather than
    an omission: a posting whose record cannot be completed never reaches here,
    because `_the_record_cannot_account_for_a_completion` has already left it
    alone. Asking twice would put the decision in two places, and the second
    copy is the one that goes stale — the boundary's own refusal is what this
    would be duplicating, and it stays there where every caller meets it.
    """
    side = resolved[section]
    return completed_receipt(
        stored,
        sections={section: Resolution(
            method=side["method"], status=side["status"],
            amount_micros=resolved["totals"][SECTIONS[section].amount_key],
            detail=side["detail"])},
        provenance={RESOLUTION_RUN_KEY: str(run_id)})


def _subject_of(posting, stored):
    """The posting, as a question for the resolver.

    ⚠ **THE COST UBB ALREADY HOLDS IS STATED RATHER THAN RECOMPUTED, AND THAT
    IS WHAT KEEPS A RUN FROM REPRICING HISTORY.** A margin is taken over what
    the call cost, so where the record already says what it cost, that is the
    basis — not a figure re-derived from cost rates that may have moved. The
    three cases the cost side can be in are answered separately:

    * `known` — the recorded amount, stated;
    * `not_applicable` — a genuine zero, which is what
      `pricing_service.a_margin_has_no_basis` already says an Event Type
      declaring no cost means, stated as zero;
    * `unresolved` — nothing stated, because this is the side being recovered
      and re-resolving it is the whole point.

    Stating a figure makes the re-resolution's own costing section read
    `reported`, which is discarded: a settled section is never written back, and
    only the section being completed is taken from this answer.
    """
    return PricingSubject(
        receipt_subject=ReceiptSubject(
            subject_type=PRICING_RECEIPT_SUBJECT_TYPE_USAGE_EVENT,
            subject_id=str(posting.pk)),
        tenant=posting.tenant, customer=posting.customer,
        selectors={name: getattr(posting, name) for name in Rate.SELECTORS},
        measurements=recorded_quantities(stored),
        currency=posting.currency,
        caller_provider_cost=_the_cost_the_record_holds(posting),
        # A RUN STATES NO PRICE OF ITS OWN, EVER. The caller rung sits above the
        # ladder, and a recovery inventing a price would be the money-moving
        # surface this mechanism exists not to be.
        caller_billed=None)


def _the_cost_the_record_holds(posting):
    if posting.costing_status == COSTING_STATUS_KNOWN:
        return posting.provider_cost_micros
    if posting.costing_status == COSTING_STATUS_NOT_APPLICABLE:
        return 0
    return None
