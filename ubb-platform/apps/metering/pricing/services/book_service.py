import uuid

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from apps.metering.pricing.models import (
    CHANGE_ADD, CHANGE_KINDS, CHANGE_RETIRE, PRICING_MODEL_CHOICES,
    PricingBookPublish, Rate, RateCard)
from apps.platform.event_types.quantities import declaration_named
from core.problems import Problem
from core.vocabulary import DECLARATION_STATUS_PUBLISHED

_RATE_COPY_FIELDS = (
    "tenant_id", "customer_id", "card_type", "provider", "event_type",
    "task_type", "subtask_type",
    *(f"grouping_field_{i}" for i in range(1, 11)),
    # The REFERENCE, not the name (#326). A reprice copies which declaration the
    # outgoing rate priced; it never re-resolves the name, so a publish cannot
    # quietly move a rate onto a different declaration between versions.
    "measurement_id", "pricing_model", "rate_per_unit_micros",
    "unit_quantity", "fixed_micros", "currency",
    "lineage_id", "rate_card_id",
)

#: WHAT A RULE CHARGES — the three columns a change body may state, and the
#: three a diff compares.
#:
#: ⚠ **THE ARITHMETIC SHAPE IS NOT ONE OF THEM, AND THAT IS A DEFERRAL RATHER
#: THAN A JUDGEMENT.** A rule declares whether its amount is per-unit or a fixed
#: component, and a publish carries that column over from the rule it supersedes
#: — a reprice cannot change it and an added rule takes the model's own default.
#: The reason is mechanical: the column's name is retired, its ledger entry is a
#: ceiling on how many files may still spell it, and every schema publishing it
#: mints a generated SDK module that counts. Coining it here would put the
#: retired spelling on two brand-new schemas for the ticket that renames it to
#: convert; coining the canonical spelling would publish a field whose VALUES
#: are still the retired ones, which is two spellings of one fact on one
#: contract. Both belong to the ticket that converts the column, its values and
#: the three schemas beside these in one commit — and until it lands, the
#: immediate reprice route this act replaces still states the shape and is
#: untouched here.
_TERM_FIELDS = ("rate_per_unit_micros", "unit_quantity", "fixed_micros")


class PlannedChange:
    """One intended change, resolved against the book at the effective instant.

    Built once and used twice — the diff renders it and the publish executes it
    — so the two cannot disagree about what a change means. A tenant reading
    *"this reprices X from A to B on 1 August"* and then getting something else
    is the failure that shape exists to make impossible.
    """

    __slots__ = ("kind", "measurement_key", "selectors", "outgoing", "terms",
                 "declaration")

    def __init__(self, *, kind, measurement_key, selectors, outgoing, terms,
                 declaration=None):
        self.kind = kind
        #: The rule this change supersedes, or `None` where it adds one.
        self.outgoing = outgoing
        #: The terms the incoming rule will carry, or `None` where none is
        #: opened — which is what retiring a rule is.
        self.terms = terms
        #: The declared quantity an added rule prices. Resolved here, at
        #: planning time, so a name the tenant's catalogue does not carry is
        #: refused before a draft is written rather than at publish time.
        self.declaration = declaration
        self.measurement_key = measurement_key
        self.selectors = selectors

    def as_diff_row(self):
        return {
            "kind": self.kind,
            "measurement_key": self.measurement_key,
            "selectors": {name: value for name, value in self.selectors.items()
                          if value},
            "before": (_terms_of(self.outgoing)
                       if self.outgoing is not None else None),
            "after": dict(self.terms) if self.terms is not None else None,
        }


def _terms_of(rule):
    return {name: getattr(rule, name) for name in _TERM_FIELDS}


def _default_terms():
    return {name: Rate._meta.get_field(name).get_default()
            for name in _TERM_FIELDS}


def _rules_in_force_at(book, instant):
    """The book as it stands at `instant`, on the half-open range resolution
    reads: a rule covers `[valid_from, valid_to)`, so one closing exactly at
    `instant` is already gone and one opening exactly then is already there.
    """
    return Rate.objects.filter(rate_card=book, valid_from__lte=instant).filter(
        Q(valid_to__isnull=True) | Q(valid_to__gt=instant))


def latest_scheduled_boundary(book):
    """The furthest instant at which any rule in this book opens or closes.

    A **maximum over both moments**, not over the openings alone: a rule that
    is retired rather than replaced closes at an instant no other rule opens
    at, so reading only `valid_from` would put the answer behind a close that
    has already been scheduled.

    ⚠ **IT READS THE BOOK AND NEVER A CLOCK**, which is exactly the mirror of
    `core.scheduling.validate_scheduled_instant`, which reads a payload and a
    clock and never a row. That is why the two floors compose and why neither
    subsumes the other: one is a statement about the present, the other about
    this book's own diary, and a book whose boundaries are all behind it
    constrains nothing at all. The day either starts reading what the other
    reads they stop being two rules; the signature is pinned by a test.

    `None` where the book holds no rule — a book nothing has ever been
    published into has no diary to be behind.
    """
    moments = Rate.objects.filter(rate_card=book).aggregate(
        opens=Max("valid_from"), closes=Max("valid_to"))
    scheduled = [moment for moment in moments.values() if moment is not None]
    return max(scheduled) if scheduled else None


def _refuse_an_instant_behind_the_books_own_diary(book, effective_at):
    """Ruling 14b — the constraint that replaced the one-pending-publish limit.

    **A publish's effective instant must be at or after the latest already
    scheduled boundary in that book.** Strictly after permits a series; equal
    permits the reversal ruling 3 expresses a cancellation as; earlier is
    refused.

    ⚠ **THIS IS THE HALF OF THE CLASS THE DATABASE CANNOT SEE, AND SAYING SO
    IS THE POINT.** The spec argues that an earlier instant is refused *because
    it is impossible anyway* — inserting a publish between two scheduled ones
    would move a close a later publish already wrote, which `Rate.valid_to`'s
    `SET_ONCE` rule rejects. That argument holds exactly when the publish
    touches the rule already scheduled to close, and `plan_changes` refuses
    **that** case in its own loop, with this same code and a message naming the
    rule. It is a restatement: the service says so with a message, the database
    says so regardless.

    A publish dated earlier that touches some *other* rule is not impossible,
    and the database would admit it. It is refused here anyway, for the reason
    `plan_changes` exists: a change is resolved against the book **as it will
    stand at the effective instant**, so an earlier-dated publish landing
    afterwards silently changes what an already-scheduled publish will do — the
    diff a tenant approved and the change that happens become different
    changes. A book's diary is written forwards.

    It carries its own code rather than the generic one, for the reason the two
    instant refusals in `core.scheduling` do: on the declaring route
    `validation_error` already means *you have not declared that grouping
    field* and *that rule is not there to reprice*, and a tenant's automation
    has to be able to tell a date it can fix from a body it cannot.
    """
    boundary = latest_scheduled_boundary(book)
    if boundary is None or effective_at >= boundary:
        return
    raise Problem(
        "effective_at_before_scheduled_boundary",
        f"effective_at is before {boundary.isoformat()}, the latest boundary "
        f"already scheduled in this book. A change is dated at or after a "
        f"book's own diary — at it to reverse what is scheduled there, after "
        f"it to follow — because a publish slipped in behind one already "
        f"scheduled would change what that one does")


#: WHAT IDENTIFIES ONE RULE INSIDE ONE BOOK: the quantity it prices and the
#: fourteen selectors. `uq_rate_active_in_book` is the same identity plus the
#: three the book already fixes — the book itself and its currency — so within
#: one book these two agree with it about which rules may be open at once.
#:
#: The two readings below take a stored rule and a change body to the same
#: value, so "which rule does this change mean" is one comparison rather than a
#: filter written twice.
def _identity_of_rule(rule):
    return (rule.measurement_key, rule.selector_tuple)


def _identity_of_change(selectors, measurement_key):
    return (measurement_key,
            tuple(selectors[name] for name in Rate.SELECTORS))


def plan_changes(book, changes, effective_at):
    """Resolve every intended change against the book **as it will stand at
    `effective_at`**, or refuse the whole set.

    ⚠ **AT THE EFFECTIVE INSTANT, NEVER AS OF NOW, AND THE TWO GENUINELY
    DIFFER.** A book can already carry a rule scheduled to close and its
    scheduled replacement — that is exactly what a previous forward-dated
    publish leaves behind — so "the rule this reprices" has two different
    answers and only one of them is the one the publish will act on. Asking the
    question as of now would show a tenant a diff against terms that will not be
    in force when their change lands, and then write something else.

    Refusing here rather than at publish time is what makes a draft usable: a
    tenant finds out that a name is undeclared or that a rule is not there while
    they are still deciding, not when the price was supposed to change. The
    publish re-plans against the same book anyway, because the book can move
    between the two acts.

    ⚠ **RULING 14b'S FLOOR IS ENFORCED HERE SO THAT EVERY ACT INHERITS IT
    (#360).** Declaring, diffing and publishing all plan through this function,
    so the floor holds at all three — including the case the declaring route
    cannot reach, where a draft was legal when it was declared and a later
    publish has since moved the book's diary past it.

    **IT IS CHECKED AFTER THE CHANGES, NOT BEFORE THEM, AND THAT ORDER IS THE
    WHOLE OF WHERE THE TWO HALVES MEET.** A change naming the very rule already
    scheduled to close is refused inside the loop, with the same code and a
    message that names the rule and the instant; the book-wide floor below
    catches what the loop cannot see — a publish dated earlier that touches
    some *other* rule. Checking the book first would make the loop's refusal
    unreachable, since a rule in force at the instant and scheduled to close
    after it puts the book's own latest boundary ahead of that instant by
    construction, and the tenant would lose the only message that says which
    rule.
    """
    in_force = list(
        _rules_in_force_at(book, effective_at).select_related("measurement"))
    still_open = list(Rate.objects.filter(
        rate_card=book, valid_to__isnull=True).select_related("measurement"))
    planned = []
    claimed = set()

    for position, change in enumerate(changes):
        kind = change.get("kind")
        if kind not in CHANGE_KINDS:
            raise ValueError(
                f"change {position}: kind must be one of "
                f"{sorted(CHANGE_KINDS)}; got {kind!r}")
        measurement_key = change.get("measurement_key") or ""
        if not measurement_key:
            raise ValueError(
                f"change {position}: measurement_key names the declared "
                f"quantity this rule prices and is required")
        selectors = {name: (change.get(name) or "") for name in Rate.SELECTORS}
        identity = _identity_of_change(selectors, measurement_key)
        if identity in claimed:
            raise ValueError(
                f"change {position}: this publish already changes the rule for "
                f"{measurement_key!r} on these selectors. One publish states "
                f"one outcome per rule; two changes to one rule are two "
                f"publishes or one change")
        claimed.add(identity)

        matched = [rule for rule in in_force
                   if _identity_of_rule(rule) == identity]
        stated = {name: change[name] for name in _TERM_FIELDS
                  if change.get(name) is not None}

        if kind == CHANGE_ADD:
            if matched:
                raise ValueError(
                    f"change {position}: the book already prices "
                    f"{measurement_key!r} on these selectors at the effective "
                    f"instant. Repricing an existing rule is a reprice")
            # The book's own uniqueness rule is about OPEN rules rather than
            # about an instant, so a rule that is closed at the effective
            # instant and still open today would be admitted by the check above
            # and refused by the database. Saying so here keeps the refusal
            # readable and keeps the publish all-or-nothing.
            if any(_identity_of_rule(rule) == identity
                   for rule in still_open):
                raise ValueError(
                    f"change {position}: the book holds an open rule for "
                    f"{measurement_key!r} on these selectors that opens after "
                    f"the effective instant. Two open rules for one identity "
                    f"is what `uq_rate_active_in_book` refuses")
            declaration = declaration_named(tenant=book.tenant,
                                            measurement_key=measurement_key)
            if declaration is None:
                raise ValueError(
                    f"change {position}: no declared quantity is called "
                    f"{measurement_key!r}. A rule prices a quantity this "
                    f"tenant has declared on an Event Type; declare it first, "
                    f"then price it")
            planned.append(PlannedChange(
                kind=kind, measurement_key=measurement_key,
                selectors=selectors, outgoing=None, declaration=declaration,
                terms={**_default_terms(), **stated}))
            continue

        if len(matched) != 1:
            raise ValueError(
                f"change {position}: no rule prices {measurement_key!r} on "
                f"these selectors at the effective instant, so there is "
                f"nothing to {kind}")
        outgoing = matched[0]
        if outgoing.valid_to is not None:
            # ⚠ RULING 14b'S OWN CASE, AND THE HALF THE DATABASE ALSO REFUSES
            # (#360). This is *inserting a publish between two scheduled ones*:
            # carrying it out would move a close a later publish already wrote,
            # which `Rate.valid_to`'s SET_ONCE rule rejects whatever this
            # function does. So it is a restatement rather than the only thing
            # holding the rule — and it carries the same code as the book-wide
            # floor below, because it is the same statement about the same
            # instant, said precisely enough to name the rule.
            #
            # ⚠ THE ADVICE IT CARRIED WAS BACKWARDS. It said "date this one
            # before that instant", which is the case that produced the refusal
            # in the first place. Dating the change AT OR AFTER the scheduled
            # close is what works: at that instant the rule in force is the
            # successor, which is still open, so the publish closes that
            # instead and no close moves.
            raise Problem(
                "effective_at_before_scheduled_boundary",
                f"change {position}: the rule for {measurement_key!r} is "
                f"already scheduled to close at "
                f"{outgoing.valid_to.isoformat()}, and effective_at is before "
                f"that. `Rate.valid_to` is set once, so a close cannot be "
                f"moved; discard the publish that scheduled it, or date this "
                f"one at or after that instant")

        if kind == CHANGE_RETIRE:
            if stated:
                raise ValueError(
                    f"change {position}: a retirement opens no rule, so it "
                    f"states no terms; got {sorted(stated)}")
            planned.append(PlannedChange(
                kind=kind, measurement_key=measurement_key,
                selectors=selectors, outgoing=outgoing, terms=None))
            continue

        planned.append(PlannedChange(
            kind=kind, measurement_key=measurement_key, selectors=selectors,
            outgoing=outgoing,
            terms={**_terms_of(outgoing), **stated}))
    _refuse_an_instant_behind_the_books_own_diary(book, effective_at)
    return planned


class BookService:
    @staticmethod
    def publish(book, changes, as_of=None):
        """Atomically reprice a set of the book's rates. Each change must match
        exactly one ACTIVE rate in the book by (measurement_key, plus the
        fourteen selector columns — provider, event_type, task_type,
        subtask_type and the ten slots). Only six of the slots can be pinned
        through the published reprice body — no slice-2 ticket widens it — so a
        change body leaves the other four at "", and a rate pinned on one of
        them is not repriceable through this route.

        ⚠ THAT GAP IS CLOSED ON THE ACT THAT REPLACES THIS ONE, AND STILL OPEN
        HERE (#358). A publish record's change body names its grouping fields by
        the tenant's own declared KEY rather than by six physical slot
        spellings, so the registry resolves whichever slot the tenant bound it
        to and all ten are reachable. This method keeps the gap because its own
        body is the one being retired, not converted.
        Supersedes it (valid_to=T, book_version_to=old
        version) and inserts a new active rate (same lineage_id, valid_from=T,
        book_version_from=new version). Bumps book.version once. All-or-nothing.

        ONE CLOCK CLOSES THE BOUNDARY AND OPENS IT, AND THAT FIXED A LIVE BUG
        (#325). Until the effective moment became suppliable, the replacement
        opened at the instant of INSERT — `T + ε`, strictly after the moment the
        outgoing rate closed at. Resolution asks for `valid_from <= as_of` and
        `valid_to > as_of`, so no rate at all covered `[T, T + ε)`: an event
        landing in that window matched nothing and fell through to markup
        pricing, which returns a plausible number and raises nothing.
        Microseconds wide, real and invisible. Both rows now take the same `T`,
        which with a half-open range is exactly no gap and exactly no overlap.
        `NoInstantFallsBetweenTwoVersionsTest` holds it.

        A FUTURE `as_of` IS NOW HONOURED DOWNSTREAM, AND THIS METHOD
        INVALIDATES NOTHING (#356). The two defects the pricing-versions
        decision (§8.3) assigned to the work that introduces forward-dating are
        both paid: `CardCache.resolve` takes the instant as a parameter instead
        of reading a clock, and its key carries that instant — so a cached
        resolution answers for the moment it was computed for and for no other.
        A publish therefore has nothing to invalidate. Entries for instants
        before the new boundary stay correct forever, and entries for instants
        after it were never created; the alternative, invalidating *at* the
        boundary, is the scheduled job forward-dated publishing exists to avoid,
        and "nothing runs at the effective instant" is only literally true
        without it.

        What THIS method still does not do is REFUSE a moment, and it still has
        no caller that supplies one: `PublishIn` carries no moment, so the
        immediate route this survives beside always means now. The horizon a
        dated change is bounded by landed in `core.scheduling` with #359 and is
        enforced on the DECLARE route, which is the surface that advertises an
        instant. This entity's published surface is still a later ticket's.
        """
        as_of = as_of or timezone.now()
        with transaction.atomic():
            locked = RateCard.objects.select_for_update().get(id=book.id)
            new_version = locked.version + 1
            for ch in changes:
                # Matched on the NAME the change body carries, read through the
                # reference (#326) — a reprice body names a quantity, not a
                # declaration id, and nothing published gives a caller one to
                # name. A rate the conversion deactivated references nothing and
                # is therefore unmatchable here, which is the same answer it
                # gives resolution: it cannot be repriced, and the refusal below
                # says so with the name in it.
                #
                # `of=("self",)` locks the RATE and not the row it joins. The
                # lock is here to serialise reprices of one rate; a declaration
                # is read-only on this path, and locking it would make two
                # publishes of two different rates that happen to price one
                # quantity wait for each other.
                old = Rate.objects.select_for_update(of=("self",)).filter(
                    rate_card=locked, valid_to__isnull=True,
                    measurement__code=ch["measurement_key"],
                    **{s: ch.get(s, "") for s in Rate.SELECTORS},
                ).first()
                if old is None:
                    raise ValueError(
                        f"publish: no active rate for {ch['measurement_key']!r} in book {locked.key}")
                data = {f: getattr(old, f) for f in _RATE_COPY_FIELDS}
                for k in ("pricing_model", "rate_per_unit_micros", "unit_quantity",
                          "fixed_micros"):
                    if k in ch:
                        data[k] = ch[k]
                data["book_version_from"] = new_version
                data["book_version_to"] = None
                data["valid_from"] = as_of
                # Re-validate the repriced shape so a publish can never create a
                # rate with a retired/unknown pricing_model. Raises
                # ValueError -> rolls back the whole publish (endpoint maps 422).
                valid_models = {c[0] for c in PRICING_MODEL_CHOICES}
                if data["pricing_model"] not in valid_models:
                    raise ValueError(
                        f"pricing_model must be one of {sorted(valid_models)}")
                # Close the old row at T, then open the new AT THE SAME T.
                old.valid_to = as_of
                old.book_version_to = locked.version
                old.save(update_fields=["valid_to", "book_version_to", "updated_at"])
                Rate.objects.create(**data)
            locked.version = new_version
            locked.save(update_fields=["version", "updated_at"])
            book.version = new_version
            return book

    # --- Every change to a book is a publish, and a draft is not one (#358) ---
    #
    # The three methods below replace the three immediate mutation surfaces
    # above and beside this file with one act. The immediate ones SURVIVE this
    # commit — `BookService.publish`, `add_rate` and `delete_rate` are still
    # reachable and still write rules with no publish record behind them — and
    # deleting them is a later ticket's, together with the three retired audit
    # action names they write. Until then a book has two ways to change and only one of
    # them leaves a record; that is the state this commit deliberately creates
    # and the next one in the chain removes.

    @staticmethod
    def declare(book, changes, effective_at=None):
        """Declare a draft: the intended changes, and nothing written.

        **A DRAFT WRITES NO RULE.** It holds the change list and the instant it
        will take effect, and that is the whole of it — which is what makes it
        freely editable and freely discardable, and why discarding one reopens
        nothing.

        The changes are planned against the book as it will stand at
        `effective_at` and the whole set is refused if any one of them cannot be
        carried out, so a tenant learns that a name is undeclared or that a rule
        is not there while they are still deciding.

        ⚠ **THE EFFECTIVE INSTANT IS FIXED HERE AND NOT AT PUBLISH TIME**, and
        that is what keeps a diff meaningful. A tenant reads the diff, and the
        diff is a statement about one instant; recomputing it against "now" when
        the publish lands would let the change a tenant approved and the change
        that happens be different changes.

        **THE PUBLISHED SURFACE NOW ADVERTISES A FUTURE INSTANT (#359).**
        `BookPublishIn.effective_at` carries it, and a caller who omits it means
        now — which is what the fall-back below says. The bound it is refused
        beyond, and the reason that refusal is the route's first statement
        rather than this method's, are in `core.scheduling`: this is a service
        that takes an instant, not a surface that decides which instants a
        tenant may name.
        """
        effective_at = effective_at or timezone.now()
        plan_changes(book, changes, effective_at)
        return PricingBookPublish.objects.create(
            tenant=book.tenant, book=book, effective_at=effective_at,
            changes=list(changes))

    @staticmethod
    def diff(record):
        """What this publish will do to the book, before it does it — one row
        per intended change.

        Computed from the draft's own change list against the book as it will
        stand at the record's effective instant — the same call the publish
        makes, so what a tenant reads and what happens are one computation
        rather than two that agree today.

        ⚠ **RAISES `ValueError` WHERE THE BOOK HAS MOVED UNDER THE DRAFT**, which
        is a reachable state rather than a defensive branch: a book still has
        three immediate mutation routes, and two drafts can name one rule while
        only one of them publishes. A caller reading a draft has to be able to
        say so rather than answer a diff it cannot compute — `metering_endpoints`
        turns it into the record's `diff_unavailable_reason`.
        """
        return [change.as_diff_row()
                for change in plan_changes(record.book, record.changes,
                                           record.effective_at)]

    @staticmethod
    def publish_declared(record, actor=None):
        """Publish a draft: close each superseded rule, open its replacement.

        **ONE CLOCK CLOSES THE BOUNDARY AND OPENS IT.** The outgoing rule's
        `valid_to` and the incoming rule's `valid_from` are the same value —
        `record.effective_at`, read once — which with the half-open range
        resolution reads is exactly no gap and exactly no overlap. Writing them
        from two reads of a clock is the live defect this act was built to make
        unrepeatable: the interval between them was covered by no rule at all,
        so an event landing in it matched nothing and fell through to markup,
        which returns a plausible number and raises nothing.

        **NOTHING RUNS AT THE EFFECTIVE INSTANT.** The rows are written when the
        publish lands, carrying the boundary as a value the resolver reads. No
        task, no signal, no deferred write — a late job would price a day of
        traffic at the old rate on records with no re-invoice path behind them.

        All-or-nothing, and re-planned against the book as it stands now:
        the book can move between declaring and publishing, and a plan made
        against a book that has since changed is not a plan.
        """
        if record.is_published:
            raise ValueError("publish: this record is already published")
        with transaction.atomic():
            locked = RateCard.objects.select_for_update().get(id=record.book_id)
            new_version = locked.version + 1
            planned = plan_changes(locked, record.changes,
                                   record.effective_at)
            opened, closed = [], []
            for change in planned:
                if change.outgoing is not None:
                    outgoing = Rate.objects.select_for_update(
                        of=("self",)).get(pk=change.outgoing.pk)
                    outgoing.valid_to = record.effective_at
                    outgoing.book_version_to = locked.version
                    outgoing.save(update_fields=["valid_to", "book_version_to",
                                                 "updated_at"])
                    closed.append(str(outgoing.pk))
                if change.terms is None:
                    continue
                if change.outgoing is not None:
                    data = {field: getattr(change.outgoing, field)
                            for field in _RATE_COPY_FIELDS}
                else:
                    # An added rule starts a lineage of its own: there is no
                    # predecessor whose history it continues.
                    data = {
                        "tenant_id": locked.tenant_id, "customer_id": None,
                        "card_type": locked.card_type,
                        "measurement_id": change.declaration.id,
                        "currency": locked.currency,
                        "lineage_id": uuid.uuid4(),
                        "rate_card_id": locked.id,
                        **change.selectors,
                    }
                incoming = Rate.objects.create(**{
                    **data, **change.terms,
                    "book_version_from": new_version, "book_version_to": None,
                    "valid_from": record.effective_at, "valid_to": None,
                })
                opened.append(str(incoming.pk))
            locked.version = new_version
            locked.save(update_fields=["version", "updated_at"])
            record.declaration_status = DECLARATION_STATUS_PUBLISHED
            record.published_at = timezone.now()
            record.actor_kind = actor.kind if actor is not None else ""
            record.actor_id = actor.id if actor is not None else ""
            record.actor_display = actor.display if actor is not None else ""
            record.opened_rule_ids = opened
            record.closed_rule_ids = closed
            record.save()
        record.book.version = new_version
        return record

    @staticmethod
    def discard(record):
        """Discard a draft, leaving the book exactly as it stood.

        A draft closed nothing, so discarding it reopens nothing — the whole of
        the act is removing the intention. A published record is refused here
        rather than in the database: a `BEFORE DELETE` trigger cannot tell this
        `DELETE` from the one a tenant wipe issues, and a route knows which act
        it is performing.
        """
        if record.is_published:
            raise ValueError(
                "discard: this record is published. A publish that has already "
                "closed and opened rules is not an intention that can be "
                "withdrawn; the act that undoes it is a further publish")
        record.delete()
