"""A receipt seals when its last unresolved field completes (#353).

#349 made the Pricing Receipt the record that explains an amount and #350 made
it outlive the measurements it explains. Both say what a receipt CONTAINS.
Neither says what may happen to one afterwards — and a record that can be
edited is not an authority, it is a cache of the configuration with extra steps.
This module is the third of the posting table's declared-transition trios, and
its subject is the two properties that make the receipt the authority:

* **Once complete, a receipt cannot change.** A historical price cannot be
  edited into a different historical price.
* **A field recorded as unresolved completes exactly once.** That is the only
  write a recovery run is ever permitted; a second one is a revision wearing a
  recovery's clothes.

Sealing is the join of the two: the record becomes immutable when its last
unresolved field completes, and before that it is immutable except for the
completion of a field that is still unresolved.

**WHAT AN UNRESOLVED FIELD IS, TAKEN FROM THE RECORD'S OWN RULE.**
`apps/metering/pricing/receipts.py` holds each section's amount, status and
method to agreeing — *an amount is present exactly when the status says the
resolution is settled, and the method is present on exactly the same condition*.
So the fields that are null exactly while a section is unresolved are that
section's `method` and its amount under `totals`, and its `status` is the
discriminator that moves with them. The rule under test is that sentence one
level up: **a section RECORDED AS UNRESOLVED completes once, as a whole.**

⚠ *Unresolved*, not *unsettled*. `waived` and `not_applicable` null the same two
fields, so the shape cannot tell a decision somebody made from information UBB
is missing — `core.amount_status_pairs` can, and
`OnlyAnUnresolvedFieldIsCompletableTest` below is that distinction at the
receipt.

**⚠ THE RECEIPT IS A COLUMN ON THIS TABLE, NOT A TABLE OF ITS OWN.** Its rule is
therefore a THIRD rule on `ubb_posting` rather than the first rule on a second
table, and what makes it provable in isolation is not where it lives: it is that
it names a **disjoint column**, that every refusal below asserts **that column**
in the message Postgres answers with, and that dropping it leaves both
neighbours standing. All three rules are declared `resolve_once`, so the class
alone stopped discriminating the day the second one landed — `REFUSAL_NAMES` is
what separates them, and it is set per class here as it is in the two modules
beside this one.

**⚠ WHY THIS MODULE EXISTS SEPARATELY FROM THE DECLARATION.** G19 walks the
declarations and asks, for each declared column, whether the table's rules name
it — a **word-boundary search over the concatenated trigger bodies**. #325
measured that deleting a refusal branch outright leaves that search satisfied,
and #352 measured the whole shape: a fully green declaration check over a table
that admitted every write its rule exists to refuse. So **a green G19 proves
only that this column is NAMED by a rule.** What proves holding is the trio
below, and `AGreenDeclarationCheckDoesNotProveTheRuleHoldsTest` is that sentence
as a test.

**The admitted move is not a courtesy, it is the control.** Almost every
assertion here is *"this statement was refused"*, which a rule refusing **every**
write would satisfy completely — while making an unresolved receipt impossible
to complete, which is a worse defect than the one being fixed and one no later
run could repair. The class carrying it is named for that job.

**There is no test-only hook for this rule, anywhere, and that is the spec's
ruling rather than an omission.** Sealing is asserted at the database through
three doors precisely because a service-level seam is the door the migration
decision found unguarded. `TheModelGuardIsNotTheEnforcementTest` is where that
is checked rather than assumed.

**A `BEFORE` trigger runs before the table's constraints are evaluated**, and
this one fires only when the receipt column itself moves — so an update leaving
the receipt alone never enters its body, which is what keeps the two sibling
rules' own cases answering for their own mechanisms.
"""
import copy
import re

from django.apps import apps
from django.db import IntegrityError, connection, migrations, transaction
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase

from apps.metering.pricing.receipts import (
    MARKUP_TERMS_KEY, SECTIONS, Resolution, ReceiptSubject, build_receipt)
from apps.metering.pricing.tests._helpers import markup_terms
from apps.metering.usage.models import Posting
from apps.metering.usage.tests._helpers import (
    DOORS, TransitionRefusalMixin, committed_posting, rule_on_the_table,
    rules_on_the_table, through_raw_sql, through_save, through_the_queryset)
from apps.platform.tests.test_transition_class_declarations import (
    columns_the_database_does_not_defend, declaring_models_by_table)
from core.amount_status_pairs import CUSTOMER_PRICE, SUPPLIER_COST
from core.transitions import (
    RESOLVE_ONCE, columns_declared_into_defended_classes)
from core.vocabulary import (
    COSTING_METHOD_CALCULATED,
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_NOT_APPLICABLE,
    COSTING_STATUS_UNRESOLVED,
    PRICING_METHOD_MARGIN_OVER_COST,
    PRICING_RECEIPT_SUBJECT_TYPE_USAGE_EVENT,
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_NOT_APPLICABLE,
    PRICING_STATUS_UNKNOWN,
    PRICING_STATUS_WAIVED,
    UNRESOLVED_REASON_COST_RATE_MISSING,
)

#: The column under test, addressed through the model's own constant rather
#: than spelled. That indirection was written while the column still carried
#: the retired spelling, and #370 is what it was for: the rename landed and
#: every reader going through here came with it, rather than quietly stopping
#: being about this column. It stays for the same reason it was worth having.
RECEIPT = Posting.RECEIPT_COLUMN

PRICE = "billed_cost_micros"
PRICING_STATUS = "pricing_status"
COST = "provider_cost_micros"
COSTING_STATUS = "costing_status"

TABLE = Posting._meta.db_table

#: This rule, addressed BY NAME rather than by counting. The table carries
#: three, and `pg_trigger` promises no order at all.
TRIGGER = "trg_posting_receipt_sealing"
FUNCTION = "ubb_posting_receipt_sealing"

#: WHICH MIGRATION DEFINES THIS RULE TODAY, which is not the one that first
#: installed it. `0040` installed it; `0042` took the rule off the table,
#: renamed the column it is about, and put the rule back naming the new column
#: — because Postgres stores a `plpgsql` body as text and a column rename does
#: not reach inside one. So `0040`'s DDL now names a column that does not
#: exist, and a reverse driven through it would fail against today's table
#: while proving nothing about the rule that is actually installed. The claim
#: is unchanged and it moves to the migration that carries it.
MIGRATION = "0042_the_receipt_takes_the_ratified_name_of_what_it_holds"

#: The operation inside it whose forward direction is the live rule. That
#: migration runs THREE — take the rule off, rename the column, put it back —
#: so `next(... isinstance(op, RunPython))` would find the first, whose
#: forward direction is the removal. Addressed by the function's own name.
INSTALLING_OPERATION = "install"

SUBJECT = ReceiptSubject(
    subject_type=PRICING_RECEIPT_SUBJECT_TYPE_USAGE_EVENT,
    subject_id="11111111-1111-1111-1111-111111111111")

AN_INSTANT = "2026-08-18T09:00:00+00:00"
ENGINE = "2.1.0"

SETTLED_COST = Resolution(
    method=COSTING_METHOD_CALCULATED, status=COSTING_STATUS_KNOWN,
    amount_micros=4_000, detail={"components": []})
UNRESOLVED_COST = Resolution(
    method=None, status=COSTING_STATUS_UNRESOLVED, amount_micros=None,
    detail={"uncosted_measurement_keys": ["image_pixels"]})
#: THE TERMS A MARGIN OVER COST HAS TO CARRY (#357), in the amounts these
#: fixtures already used: 20% over a 4_000 basis is 800, so the 4_800 below is
#: the sum of these rather than a number that merely sits beside them.
MARKUP_TERMS = markup_terms(4_000, micro_percent=20_000_000)
SETTLED_PRICE = Resolution(
    method=PRICING_METHOD_MARGIN_OVER_COST, status=PRICING_STATUS_KNOWN,
    amount_micros=4_800,
    detail={"components": [], MARKUP_TERMS_KEY: MARKUP_TERMS})
UNKNOWN_PRICE = Resolution(
    method=None, status=PRICING_STATUS_UNKNOWN, amount_micros=None, detail={})

#: THE TERMINAL STATUSES, WHICH ARE NOT SETTLED AND ARE NOT COMPLETABLE EITHER.
#:
#: They carry the same pair of absent fields an unresolved section carries — no
#: method, no amount — so "not settled" and "completable" look identical on the
#: record and are different facts. `core.amount_status_pairs` is where that is
#: already settled for the columns: each pair names ONE `unresolved_status`, and
#: `waived` and `not_applicable` are not it.
WAIVED_PRICE = Resolution(
    method=None, status=PRICING_STATUS_WAIVED, amount_micros=None, detail={})
NOT_APPLICABLE_PRICE = Resolution(
    method=None, status=PRICING_STATUS_NOT_APPLICABLE, amount_micros=None,
    detail={})
NOT_APPLICABLE_COST = Resolution(
    method=None, status=COSTING_STATUS_NOT_APPLICABLE, amount_micros=None,
    detail={})


def _receipt(costing=SETTLED_COST, pricing=SETTLED_PRICE, **overrides):
    """A real receipt, built through the one construction boundary.

    Never a hand-written dict. A literal would re-encode the record's key names
    here, so it would keep passing through a reshaping of the very record this
    rule is about — and, worse, it could assert a refusal of a shape the
    boundary would never have let reach the column in the first place.
    """
    fields = {"subject": SUBJECT, "effective_at": AN_INSTANT, "currency": "usd",
              "pricing_engine_version": ENGINE, "costing": costing,
              "pricing": pricing, "provenance": {"price_rate_ids": {}}}
    fields.update(overrides)
    return build_receipt(**fields)


def _sealed():
    """A receipt with nothing left unresolved — the immutable state."""
    return _receipt()


def _with_an_unresolved_cost():
    return _receipt(costing=UNRESOLVED_COST)


def _with_an_unknown_price():
    return _receipt(pricing=UNKNOWN_PRICE)


def _with_both_unresolved():
    return _receipt(costing=UNRESOLVED_COST, pricing=UNKNOWN_PRICE)


def _priced_at(amount):
    """A receipt whose price section is settled at ``amount``.

    ONE SHAPE, AND WHAT IT MEANS DEPENDS ENTIRELY ON THE ROW IT LANDS ON —
    which is the rule's whole subject. Written onto a posting whose price was
    unknown it is a completion and is admitted; written onto one that already
    carries a settled price it is a correction and is refused. Same record,
    same subject, same instant, same method; a different answer.
    """
    return _receipt(pricing=Resolution(
        method=PRICING_METHOD_MARGIN_OVER_COST, status=PRICING_STATUS_KNOWN,
        amount_micros=amount,
        # A rung of zero over a basis of `amount` IS `amount`, so the terms
        # reproduce the figure this case parameterises rather than merely
        # sitting beside it — which is the helper's own default.
        detail={"components": [], MARKUP_TERMS_KEY: markup_terms(amount)}))


def _edited(receipt, edit):
    """A copy of ``receipt`` with ``edit`` applied — the record, minus a field.

    Deep-copied so a case cannot quietly mutate the fixture another case reads,
    and applied by a callable so each case says what it changed in one line.
    """
    changed = copy.deepcopy(receipt)
    edit(changed)
    return changed


def _posting(receipt, **columns):
    return committed_posting(**{RECEIPT: receipt, **columns})


def _holding(receipt_factory, **columns):
    """A factory the refusal mixin can call once per door."""
    return lambda: _posting(receipt_factory(), **columns)


_through_the_queryset = through_the_queryset
_through_raw_sql = through_raw_sql
_through_save = through_save


class ATriggerRefusingEveryWriteWouldSatisfyTheRefusalsAloneTest(TestCase):
    """The admitted move, and the trio is worthless without it.

    Every other refusal in this module would be satisfied by a rule with a
    single unconditional `RAISE` at the top of its body — which would make an
    unresolved receipt impossible to complete, and so make the recovery runs
    that are the whole point of recording *unresolved* impossible to build.

    The class is named for the failure it catches rather than for the behaviour
    it exercises, which is the naming the two modules beside this one use.
    """

    def _completes(self, receipt, completed, section, amount_key, amount):
        for name, door in DOORS:
            with self.subTest(door=name):
                posting = _posting(receipt())
                door(posting, **{RECEIPT: completed})
                posting.refresh_from_db()
                stored = getattr(posting, RECEIPT)
                self.assertEqual(stored[section]["status"],
                                 SECTIONS[section].settled)
                self.assertEqual(stored["totals"][amount_key], amount)
                self.assertIsNotNone(stored[section]["method"])

    def test_an_unresolved_cost_completes_through_every_door(self):
        self._completes(
            _with_an_unresolved_cost, _receipt(), "costing", COST, 4_000)

    def test_an_unknown_price_completes_through_every_door(self):
        """The same rule on the other side of the margin, and it is one rule.

        The trigger reads its two sections out of one array rather than out of
        two branches, so a repair to either is a repair to both — and a case per
        side is what says that is true rather than merely intended.
        """
        self._completes(
            _with_an_unknown_price, _receipt(), "pricing", PRICE, 4_800)

    def test_both_sections_complete_in_one_statement(self):
        """A receipt unresolved on both sides seals in a single write.

        The rule is per section, so a statement completing both is two
        completions at once rather than a completion and an edit — and a rule
        that admitted one at a time only would force a recovery to write twice,
        the second of which would land on a section already settled.
        """
        for name, door in DOORS:
            with self.subTest(door=name):
                posting = _posting(_with_both_unresolved())
                door(posting, **{RECEIPT: _receipt()})
                posting.refresh_from_db()
                stored = getattr(posting, RECEIPT)
                self.assertEqual(stored["totals"],
                                 {COST: 4_000, PRICE: 4_800})

    def test_a_completion_of_exactly_zero_is_admitted(self):
        """Zero is a resolved amount, not a missing one.

        The distinction the nullable columns exist to hold, one level up: a
        rule written as if a completion always carries a positive number would
        turn away the receipt for an event correctly priced at nothing.
        """
        posting = _posting(_with_an_unknown_price())
        _through_the_queryset(posting, **{RECEIPT: _priced_at(0)})
        posting.refresh_from_db()
        self.assertEqual(getattr(posting, RECEIPT)["totals"][PRICE], 0)

    def test_a_completion_may_record_the_run_that_made_it(self):
        """Provenance gains a cross-reference on the statement that completes.

        The record's shape says provenance carries the ids of the matched rule,
        the publish, the cost rates *and where applicable the run that completed
        it*. A rule that froze provenance outright would leave a completed
        receipt unable to say which run completed it, which is the one
        cross-reference that cannot be known when the record is built.
        """
        completed = _receipt(
            provenance={"price_rate_ids": {}, "resolution_run_id": "run-1"})
        posting = _posting(_with_an_unknown_price())
        _through_the_queryset(posting, **{RECEIPT: completed})
        posting.refresh_from_db()
        self.assertEqual(
            getattr(posting, RECEIPT)["provenance"]["resolution_run_id"],
            "run-1")

    def test_a_completion_rewrites_the_detail_of_the_section_it_completes(self):
        """The section completes as a whole, and that is a decision.

        An unresolved costing section carries the quantities that went uncosted
        so that a recovery has something to work from; a completed one carries
        the components that explain the amount. Those are different content in
        the same slot, so a rule admitting only additions there would seal a
        receipt still advertising quantities that have since been costed.
        """
        posting = _posting(_with_an_unresolved_cost())
        self.assertEqual(
            getattr(posting, RECEIPT)["costing"]["detail"]
            ["uncosted_measurement_keys"], ["image_pixels"])

        _through_the_queryset(posting, **{RECEIPT: _receipt()})
        posting.refresh_from_db()
        self.assertEqual(getattr(posting, RECEIPT)["costing"]["detail"],
                         {"components": []})


class ASealedReceiptIsNotEditableTest(TransitionRefusalMixin, TestCase):
    """The first property: once complete, a receipt cannot change.

    Nothing else on this table can see these writes. There is no `CHECK` over
    the receipt column — the record's shape is refused at its construction
    boundary, which runs before persistence and knows nothing about what was
    there a moment ago — so every case in this class is this rule's alone.
    """

    REFUSAL_NAMES = RECEIPT

    def test_a_settled_amount_cannot_be_edited(self):
        """The sentence the receipt exists for: a historical price stays put."""
        self._refused_by_the_trigger(
            _holding(_sealed), RESOLVE_ONCE,
            **{RECEIPT: _priced_at(9_999)})

    def test_a_settled_section_cannot_be_unsettled(self):
        """The queue does not grow by relabelling, any more than it shrinks.

        Moving a settled section back to unresolved would take a number the
        tenant has already been shown out of every total that reported it, and
        put the row in front of a recovery run that has nothing to recover.
        """
        self._refused_by_the_trigger(
            _holding(_sealed), RESOLVE_ONCE,
            **{RECEIPT: _with_an_unknown_price()})

    def test_a_settled_method_cannot_be_relabelled(self):
        """How an amount was arrived at is settled when the amount is.

        The method is not decoration: it is what a reader consults to know
        whether a figure is a margin over a supplier cost or a price the tenant
        set directly, and re-labelling it rewrites the explanation while leaving
        the number that needs explaining alone.
        """
        self._refused_by_the_trigger(
            _holding(_sealed), RESOLVE_ONCE,
            **{RECEIPT: _edited(_sealed(), lambda r: r["pricing"].update(
                method=None))})

    def test_the_detail_of_a_settled_section_cannot_be_rewritten(self):
        """What explained a settled amount stays what explained it.

        The completion case above is the only statement that may write a
        section's detail, and it is the statement that settles it. Afterwards
        the components are part of the record a tenant can be shown.
        """
        self._refused_by_the_trigger(
            _holding(_sealed), RESOLVE_ONCE,
            **{RECEIPT: _edited(_sealed(), lambda r: r["costing"]["detail"]
                                .update(components=[{"micros": 1}]))})

    def test_a_sealed_receipt_cannot_gain_a_cross_reference(self):
        """Provenance may grow on a completion, and only on a completion.

        Without that condition the first property has a hole in it: a sealed
        receipt would accumulate cross-references forever, each of them a
        statement about a resolution that had already happened.
        """
        self._refused_by_the_trigger(
            _holding(_sealed), RESOLVE_ONCE,
            **{RECEIPT: _receipt(
                provenance={"price_rate_ids": {}, "resolution_run_id": "r"})})


class AnUnresolvedFieldCompletesExactlyOnceTest(TransitionRefusalMixin,
                                                TestCase):
    """The second property, and it is what makes remediation safe to build.

    A recovery run may complete a blank. If it could complete the same blank
    twice, "recovery" and "revision" would be the same operation and the
    difference would survive only as long as everyone remembered which one they
    were running.
    """

    REFUSAL_NAMES = RECEIPT

    def _completed_once(self):
        """A posting whose unresolved price has been completed, once, already."""
        posting = _posting(_with_an_unknown_price())
        _through_the_queryset(posting, **{RECEIPT: _receipt()})
        posting.refresh_from_db()
        return posting

    def test_a_completed_field_cannot_be_completed_again(self):
        """The second completion, through every door.

        It is a different statement from editing a receipt that was never
        unresolved — the row reached this state through the move the rule
        admits — and it is the one a recovery run could actually make by
        running twice.
        """
        self._refused_by_the_trigger(
            self._completed_once, RESOLVE_ONCE,
            **{RECEIPT: _priced_at(7_777)})

    def test_completing_one_section_does_not_unseal_the_other(self):
        """The sections seal independently, and one completion is not a licence.

        A receipt unresolved on the cost side and settled on the price side
        completes its cost — and the price side is exactly as sealed during
        that statement as it was before it.
        """
        posting = _posting(_with_an_unresolved_cost())
        _through_the_queryset(posting, **{RECEIPT: _receipt()})
        posting.refresh_from_db()

        with self.assertRaises(IntegrityError) as refusal:
            with transaction.atomic():
                _through_the_queryset(posting,
                                      **{RECEIPT: _priced_at(1)})
        self.assertIn(RECEIPT, str(refusal.exception))

    def test_half_a_completion_is_refused(self):
        """A status that says settled, with no amount to be settled about.

        The record's own boundary refuses this shape before persistence, which
        is why it can never be built through `build_receipt` — so it is written
        here by editing a valid record, which is exactly what a writer reaching
        around that boundary would produce.
        """
        self._refused_by_the_trigger(
            _holding(_with_an_unknown_price), RESOLVE_ONCE,
            **{RECEIPT: _edited(
                _with_an_unknown_price(),
                lambda r: r["pricing"].update(status=PRICING_STATUS_KNOWN))})

    def test_an_unresolved_section_cannot_be_rewritten_short_of_completing(self):
        """The move that is not a completion, on the row a recovery holds.

        Completing is the only thing an unresolved section may do. Rewriting
        what a recovery would work from — while leaving it unresolved — changes
        the record's account of what the engine could not price, on a row a
        tenant may already have been shown, and settles nothing.
        """
        self._refused_by_the_trigger(
            _holding(_with_an_unresolved_cost), RESOLVE_ONCE,
            **{RECEIPT: _edited(
                _with_an_unresolved_cost(),
                lambda r: r["costing"]["detail"].update(
                    uncosted_measurement_keys=["audio_seconds"]))})


class OnlyAnUnresolvedFieldIsCompletableTest(TransitionRefusalMixin, TestCase):
    """⚠ NOT SETTLED IS NOT THE SAME FACT AS COMPLETABLE, and on this record the
    two look identical.

    A section carries an amount and a method exactly when its status is settled,
    so EVERY unsettled status leaves both null — `unknown` and `unresolved`,
    which say UBB does not have the information, and `waived` and
    `not_applicable`, which say a decision was made. Nothing in the SHAPE tells
    them apart. What tells them apart is `core.amount_status_pairs`, where each
    pair names exactly ONE `unresolved_status`, and both sibling triggers
    whitelist that one rather than blacklisting `known`.

    This class is that whitelist at the receipt. Its absence was a live hole and
    not a hypothetical one: `pricing_service` writes a `not_applicable` costing
    status today, the same status rides into the receipt's section, and a
    receipt-only `UPDATE` fires neither sibling rule — so the record could be
    made to assert a charged amount while the column beside it still said no
    revenue arises. That is two authorities that can disagree, which is the
    shape the receipt exists to remove.
    """

    REFUSAL_NAMES = RECEIPT

    def test_a_waived_price_is_never_a_completion_candidate(self):
        """Ruling 12c at the receipt, not only at the column.

        `waived` is a decision somebody made not to pursue a charge; `unknown`
        is information UBB does not have. If the record admitted the first as a
        completion source, the difference would survive only as long as everyone
        remembered the selector.
        """
        self._refused_by_the_trigger(
            _holding(lambda: _receipt(pricing=WAIVED_PRICE)), RESOLVE_ONCE,
            **{RECEIPT: _priced_at(4_800)})

    def test_a_not_applicable_price_never_acquires_an_amount(self):
        """A subject that generates no customer revenue does not grow some."""
        self._refused_by_the_trigger(
            _holding(lambda: _receipt(pricing=NOT_APPLICABLE_PRICE)),
            RESOLVE_ONCE, **{RECEIPT: _priced_at(4_800)})

    def test_a_not_applicable_cost_never_acquires_an_amount(self):
        """The same rule on the side where the status is written today."""
        self._refused_by_the_trigger(
            _holding(lambda: _receipt(costing=NOT_APPLICABLE_COST)),
            RESOLVE_ONCE, **{RECEIPT: _receipt()})

    def test_a_terminal_section_cannot_be_relabelled_as_unresolved(self):
        """The other way in, and it is closed.

        Moving `waived` to `unknown` would make the section completable by the
        next statement — a two-step route to the write the case above refuses,
        which is the shape a rule guarding only the destination would miss.
        """
        self._refused_by_the_trigger(
            _holding(lambda: _receipt(pricing=WAIVED_PRICE)), RESOLVE_ONCE,
            **{RECEIPT: _with_an_unknown_price()})


class AFieldThatWasNeverUnresolvedIsNotWritableTest(TransitionRefusalMixin,
                                                    TestCase):
    """The record's own identity, which no completion may touch.

    These fields are never null and never unresolved, so there is no state from
    which the rule could read a write to them as a completion. They are refused
    on a sealed receipt and on an unresolved one alike — the second is the case
    that matters, because that is the row a recovery run is holding.
    """

    REFUSAL_NAMES = RECEIPT

    def test_the_instant_the_resolution_was_made_as_of_cannot_move(self):
        self._refused_by_the_trigger(
            _holding(_with_an_unknown_price), RESOLVE_ONCE,
            **{RECEIPT: _receipt(pricing=UNKNOWN_PRICE,
                                 effective_at="2020-01-01T00:00:00+00:00")})

    def test_the_currency_cannot_be_changed(self):
        self._refused_by_the_trigger(
            _holding(_with_an_unknown_price), RESOLVE_ONCE,
            **{RECEIPT: _receipt(pricing=UNKNOWN_PRICE, currency="eur")})

    def test_the_subject_cannot_be_re_pointed(self):
        """What a receipt explains is decided when it is built.

        The subject is an INPUT to resolution rather than something assembled
        afterwards, so a receipt that could be re-pointed would be a record
        about whatever the last writer had to hand.
        """
        self._refused_by_the_trigger(
            _holding(_with_an_unknown_price), RESOLVE_ONCE,
            **{RECEIPT: _receipt(
                pricing=UNKNOWN_PRICE,
                subject=ReceiptSubject(
                    subject_type=SUBJECT.subject_type,
                    subject_id="22222222-2222-2222-2222-222222222222"))})

    def test_the_engine_that_computed_it_cannot_be_restamped(self):
        """Which code produced this number is a fact about the past."""
        self._refused_by_the_trigger(
            _holding(_with_an_unknown_price), RESOLVE_ONCE,
            **{RECEIPT: _receipt(pricing=UNKNOWN_PRICE,
                                 pricing_engine_version="9.9.9")})

    def test_a_completion_cannot_carry_an_edit_alongside_it(self):
        """⚠ The branch a rule checking only the completed section would miss.

        This statement IS a legal completion of the price side. It is refused
        because it also moves the instant — and a rule that stopped at *is this
        a completion?* would admit every edit in this class as long as one
        blank was filled in on the same write, which is precisely what a
        recovery run is in a position to do.
        """
        self._refused_by_the_trigger(
            _holding(_with_an_unknown_price), RESOLVE_ONCE,
            **{RECEIPT: _receipt(effective_at="2020-01-01T00:00:00+00:00")})

    def test_a_completion_cannot_edit_the_other_sections_settled_amount(self):
        """The same trap, one section over: complete the price, correct the cost."""
        self._refused_by_the_trigger(
            _holding(_with_an_unknown_price), RESOLVE_ONCE,
            **{RECEIPT: _receipt(costing=Resolution(
                method=COSTING_METHOD_CALCULATED, status=COSTING_STATUS_KNOWN,
                amount_micros=1, detail={"components": []}))})

    def test_a_completion_cannot_drop_a_recorded_cross_reference(self):
        """Provenance may gain, and only gain.

        Containment is the whole of that claim: what has been recorded stays
        recorded, at every depth, and a completion adds beside it.
        """
        self._refused_by_the_trigger(
            _holding(_with_an_unknown_price), RESOLVE_ONCE,
            **{RECEIPT: _receipt(provenance={"resolution_run_id": "run-1"})})


class AReceiptWithNothingToCompleteIsFrozenWholeTest(TransitionRefusalMixin,
                                                     TestCase):
    """A record the rule cannot read as having an unresolved field.

    Neither of these is a gap. A record with no section to complete has no move
    this rule admits, so it has none at all — which is the first property
    applied to a record that never had the second.
    """

    REFUSAL_NAMES = RECEIPT

    def test_the_empty_default_cannot_be_filled_in_afterwards(self):
        """A posting recorded without a receipt does not acquire one by update.

        The recording path writes the receipt at insert, in the same statement
        as the posting. A column that could be filled in later would be a
        second construction boundary with no validation on it.
        """
        self._refused_by_the_trigger(
            _holding(dict), RESOLVE_ONCE, **{RECEIPT: _sealed()})

    def test_a_receipt_in_the_older_shape_is_read_never_rewritten(self):
        """The record module's own ruling, held at the table.

        A receipt records what the engine did on a day. Back-dating one into
        today's shape would make it a worse record rather than a better one, and
        what eventually removes these is the cutover squash rather than a rule
        here quietly reshaping them.
        """
        self._refused_by_the_trigger(
            _holding(lambda: {"engine_version": ENGINE,
                              "cost_source": "caller",
                              "provider_cost_micros": 4_000}),
            RESOLVE_ONCE, **{RECEIPT: _sealed()})


class ThisRuleGuardsItsOwnColumnAndNoOthersTest(TestCase):
    """The scoping half, which the admitted move does not cover.

    A rule can admit its own permitted move and still be wrong by refusing
    writes that are none of its business — and on a table carrying three rules
    there are three ways for that to happen. All of them are exercised here.
    """

    def test_a_column_the_rule_says_nothing_about_still_writes(self):
        posting = _posting(_sealed())
        _through_the_queryset(posting, balance_after_micros=17)
        posting.refresh_from_db()
        self.assertEqual(posting.balance_after_micros, 17)

    def test_the_supplier_pair_still_settles_beside_it(self):
        posting = _posting(_sealed(), **{
            COST: None, COSTING_STATUS: COSTING_STATUS_UNRESOLVED,
            "unresolved_reason": UNRESOLVED_REASON_COST_RATE_MISSING})
        _through_the_queryset(posting, **{
            COST: 7, COSTING_STATUS: COSTING_STATUS_KNOWN,
            "unresolved_reason": None})
        posting.refresh_from_db()
        self.assertEqual(getattr(posting, COST), 7)

    def test_the_price_pair_still_resolves_beside_it(self):
        posting = _posting(_sealed(), **{
            PRICE: None, PRICING_STATUS: PRICING_STATUS_UNKNOWN})
        _through_the_queryset(posting, **{
            PRICE: 9, PRICING_STATUS: PRICING_STATUS_KNOWN})
        posting.refresh_from_db()
        self.assertEqual(getattr(posting, PRICE), 9)

    def test_a_recovery_moves_the_pair_and_completes_the_receipt_at_once(self):
        """⚠ THE STATEMENT A RECOVERY RUN ACTUALLY MAKES, AND TWO RULES SEE IT.

        Resolving a price writes the amount, the status **and** the receipt in
        one `UPDATE`. The price pair's rule reads it as `unknown` → `known`;
        this one reads it as the completion of the receipt's pricing section.
        Both admit it, neither knows about the other, and the row lands with the
        column and the record agreeing.

        This is the property a merged rule would have removed, and it is the
        reason the receipt's rule is a third trigger rather than a branch in the
        second. It is asserted here rather than argued in the migration.
        """
        for name, door in DOORS:
            with self.subTest(door=name):
                posting = _posting(_with_an_unknown_price(), **{
                    PRICE: None, PRICING_STATUS: PRICING_STATUS_UNKNOWN})
                door(posting, **{PRICE: 4_800,
                                 PRICING_STATUS: PRICING_STATUS_KNOWN,
                                 RECEIPT: _receipt()})
                posting.refresh_from_db()
                self.assertEqual(getattr(posting, PRICE), 4_800)
                self.assertEqual(
                    getattr(posting, RECEIPT)["totals"][PRICE], 4_800)


class TheModelGuardIsNotTheEnforcementTest(TestCase):
    """The spec's ruling that there is no service-level seam for this rule.

    A model-level or service-level guard protects exactly the writers that go
    through it, and the migration decision already found one not binding. The
    three cases below are that finding as a test: the model's own door refuses,
    reaching around it lands on the database, and the door the guard does not
    cover at all lands there too.
    """

    def test_the_model_still_refuses_an_update_through_its_own_door(self):
        posting = _posting(_sealed())
        setattr(posting, RECEIPT, _with_an_unknown_price())
        with self.assertRaises(ValueError):
            posting.save()

    def test_reaching_around_that_guard_lands_on_the_database(self):
        posting = _posting(_sealed())
        with self.assertRaises(IntegrityError) as refusal:
            with transaction.atomic():
                _through_save(posting, **{RECEIPT: _with_an_unknown_price()})
        self.assertIn(RESOLVE_ONCE, str(refusal.exception))
        self.assertIn(RECEIPT, str(refusal.exception))

    def test_the_guard_being_absent_would_change_nothing(self):
        """`QuerySet.update()` never calls `save()`.

        If the model guard were the enforcement, this statement would land —
        which is the whole argument for putting the rule in the table.
        """
        posting = _posting(_sealed())
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _through_the_queryset(
                    posting, **{RECEIPT: _with_an_unknown_price()})


def _triggers_on_the_table():
    return rules_on_the_table()


def _this_trigger():
    """This rule's row, asked for BY NAME — never "the table's trigger"."""
    return rule_on_the_table(TRIGGER)


class TheRuleIsHeldByAThirdTriggerOnThisTableTest(TestCase):
    """The mechanism, read off the live database rather than off the migration.

    A migration that ran is not evidence that a rule is installed — it is
    evidence that a file executed.

    **The mechanism is `0037`'s and `0039`'s, extended to a third rule.** A
    `CHECK` cannot see `OLD` at all, so it can say whether a receipt is
    well-formed and can never say whether the one it replaced was; a Postgres
    `RULE` rewrites the statement rather than judging it. What was refused is a
    second KIND of mechanism over a sibling column on one table, which is how
    two rules come to disagree about one write.
    """

    def test_the_table_carries_exactly_the_three_declared_rules(self):
        """An exact set, addressed by name in both directions.

        Spelled out here rather than imported from a shared constant, for the
        reason the declaration set is: an assertion every module took from one
        place could be satisfied by editing that place, and what this line is
        for is making a rule's arrival something a reader of THIS module agrees
        to.
        """
        self.assertEqual(
            _triggers_on_the_table(),
            {"trg_posting_declared_transitions",
             "trg_posting_price_transitions", TRIGGER,
             "trg_posting_kind_frozen"})

    def test_it_fires_before_each_updated_row(self):
        """`BEFORE UPDATE ... FOR EACH ROW`, read out of `tgtype`'s bits.

        Row-level and before the write: an `AFTER` trigger would refuse by
        rolling back work already done, and a statement-level one cannot see the
        old row at all, which is the only thing this rule is about. It does not
        fire on `INSERT`, which is what leaves the record's shape to the
        construction boundary that validates it before persistence.
        """
        tgtype, _ = _this_trigger()
        self.assertTrue(tgtype & (1 << 0), "not FOR EACH ROW")
        self.assertTrue(tgtype & (1 << 1), "not BEFORE")
        self.assertTrue(tgtype & (1 << 4), "does not fire on UPDATE")
        self.assertFalse(tgtype & (1 << 2), "fires on INSERT")
        self.assertFalse(tgtype & (1 << 3), "fires on DELETE")

    def test_the_reverse_is_exercised_rather_than_merely_declared(self):
        """Forward and back, against a real database, with a real refusal.

        `docs/conventions/django-patterns.md` asks for a reverse *"that a test
        actually runs"*, and the reason is this migration's shape: a `RunPython`
        whose two halves are DDL strings, where a typo in the reverse is
        invisible until the day somebody needs it.

        Asserted by BEHAVIOUR at both ends rather than by counting catalogue
        rows, and **the two sibling rules are asserted still standing while this
        one is out**, so a reverse that took a neighbour down with it fails here
        rather than somewhere unrelated.

        ⚠ The two ends drive the same *kind* of statement — correcting a settled
        amount — at two different values. The same value twice would leave the
        second write identical to what the row already held, and the trigger's
        own `WHEN` clause fires on nothing at all in that case — so the
        re-applied half would have passed against a table carrying no rule.
        """
        migration = MigrationLoader(connection).get_migration("usage", MIGRATION)
        run_python = next(op for op in migration.operations
                          if isinstance(op, migrations.RunPython)
                          and op.code.__name__ == INSTALLING_OPERATION)
        sealed = _posting(_sealed())

        with connection.schema_editor() as editor:
            run_python.reverse_code(None, editor)
        self.assertEqual(_triggers_on_the_table(),
                         {"trg_posting_declared_transitions",
                          "trg_posting_price_transitions",
                          "trg_posting_kind_frozen"})
        _through_the_queryset(sealed, **{RECEIPT: _priced_at(9_999)})
        sealed.refresh_from_db()
        self.assertEqual(getattr(sealed, RECEIPT)["totals"][PRICE], 9_999)

        with connection.schema_editor() as editor:
            run_python.code(None, editor)
        self.assertEqual(_triggers_on_the_table(),
                         {"trg_posting_declared_transitions",
                          "trg_posting_price_transitions", TRIGGER,
                          "trg_posting_kind_frozen"})
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _through_the_queryset(
                    sealed, **{RECEIPT: _priced_at(1_000)})

    def test_the_rule_names_the_record_the_registry_and_the_shape_declare(self):
        """The tokens spelled outside their own sources, held to them.

        A trigger body is frozen SQL living in the database, so it cannot import
        `core.vocabulary` or the receipt module the way living code does. Every
        token it freezes is derived here from the source that owns it — the
        section names and amount keys from the receipt's own shape, and each
        side's settled and completable statuses from the amount/status pairs —
        so a rename in any of them turns this red rather than leaving a rule
        that quietly matches nothing.

        ⚠ THE COMPLETABLE STATUS IS ASSERTED BECAUSE ITS ABSENCE WAS THE BUG.
        A first draft of this class checked only the settled status, which a
        rule blacklisting `known` satisfies completely — and such a rule treats
        every OTHER unsettled status as completable, so `waived` and
        `not_applicable` sections could be turned into charged amounts. The
        pair is what knows which single status a completion may start from, and
        the join below is on the amount column so that neither side of it can be
        re-pointed at the other's.
        """
        _, source = _this_trigger()
        pairs = {pair.amount_column: pair
                 for pair in (SUPPLIER_COST, CUSTOMER_PRICE)}
        for section, rules in SECTIONS.items():
            self.assertIn(f"'{section}'", source)
            self.assertIn(f"'{rules.amount_key}'", source)
            self.assertIn(f"'{rules.settled}'", source)
            self.assertIn(f"'{pairs[rules.amount_key].unresolved_status}'",
                          source)


#: A replacement body that NAMES the declared column and refuses nothing.
#:
#: The `WHEN` clause on the shipped trigger is unchanged — only the function it
#: calls is swapped — so the column is still spelled in what
#: `pg_get_triggerdef` returns, and it is spelled again in the body below. That
#: is the whole of what G19's declaration check looks for.
#:
#: A deliberately *plausible* mutation rather than an empty function: this is
#: what deleting the refusals from the shipped rule leaves behind.
TOOTHLESS = f"""
CREATE OR REPLACE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.{RECEIPT} IS DISTINCT FROM OLD.{RECEIPT} THEN
        NULL;
    END IF;
    RETURN NEW;
END;
$$;
"""


class AGreenDeclarationCheckDoesNotProveTheRuleHoldsTest(TestCase):
    """Why this module exists, as a test rather than as a paragraph.

    G19 has two kinds of enforcement node. The first walks the declarations and
    asks the database whether each declared column is named by a rule on its
    table; it names no column, so it judges this slice's declarations on the day
    they are made, and that is a genuinely good edge. The second kind is the
    trio above.

    **Only the second kind proves anything about behaviour**, and this class is
    the measurement of the difference on this rule.

    Postgres runs `CREATE OR REPLACE FUNCTION` inside the transaction this
    `TestCase` rolls back, so the shipped rule is restored when the test ends
    and nothing else ever sees the toothless one.
    """

    def _install_the_toothless_rule(self):
        with connection.cursor() as cursor:
            cursor.execute(TOOTHLESS)

    def test_the_column_is_declared_into_a_class_the_database_must_defend(self):
        """The premise, established rather than assumed.

        Without this the cases below could pass on a tree where nothing was
        declared at all — a clean board over an empty walk, which is the vacuity
        the gate's own guard exists to catch.
        """
        declared = dict(
            (column, transition_class)
            for _, column, transition_class
            in columns_declared_into_defended_classes([Posting]))
        self.assertEqual(declared[RECEIPT], RESOLVE_ONCE)

    def _the_declaration_check_over_the_whole_tree(self):
        """G19's check exactly as the gate runs it — every declarer, not this one.

        `apps.get_models()` rather than `[Posting]`: the claim is about the
        GATE's answer, and a gate asked about one model is not the gate.
        """
        return columns_the_database_does_not_defend(
            columns_declared_into_defended_classes(apps.get_models()),
            declaring_models_by_table())

    def test_the_shipped_rule_passes_the_declaration_check_and_holds(self):
        """Both halves true at once, which is the state to compare against."""
        self.assertEqual(self._the_declaration_check_over_the_whole_tree(), [])
        for name, door in DOORS:
            with self.subTest(door=name):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        door(_posting(_sealed()),
                             **{RECEIPT: _with_an_unknown_price()})

    def test_a_rule_that_refuses_nothing_still_passes_the_declaration_check(self):
        """⚠ The sentence this module exists for, measured.

        A green G19 says the column is NAMED by a rule. It does not say the rule
        holds, and here is a database where the first is true and the second is
        false.
        """
        self._install_the_toothless_rule()
        self.assertEqual(self._the_declaration_check_over_the_whole_tree(), [])

    def test_and_the_trio_above_goes_red_against_that_same_rule(self):
        """The other half — the refusals stop refusing, through every door.

        Four shapes the trio refuses are driven against the toothless rule and
        each is ADMITTED: a settled amount edited, a sealed receipt unsettled,
        an identity field moved on a completion, and a second completion of a
        field that already completed. All four go through **all three doors**,
        because "the trio goes red" is a claim about the trio and the trio is
        three doors.

        The admitted move is checked here too and still works: a mutation that
        broke it would make the trio fail for a reason unrelated to the
        refusals, which is exactly the two-cause fault that reads like a vacuous
        control.

        ⚠ **ONE SHAPE STAYS REFUSED, AND IT BELONGS TO A DIFFERENT RULE.** A
        statement that edits a sealed receipt *and* corrects a resolved price is
        refused by `trg_posting_price_transitions` whatever this trigger does.
        It is asserted below so the two failure sets stay distinguishable:
        gutting this rule does not gut its neighbour, and a reader should not
        come away thinking it did.
        """
        self._install_the_toothless_rule()

        for name, door in DOORS:
            with self.subTest(door=name):
                edited = _posting(_sealed())
                door(edited, **{RECEIPT: _priced_at(9_999)})
                edited.refresh_from_db()
                self.assertEqual(
                    getattr(edited, RECEIPT)["totals"][PRICE], 9_999)

                unsealed = _posting(_sealed())
                door(unsealed, **{RECEIPT: _with_an_unknown_price()})
                unsealed.refresh_from_db()
                self.assertEqual(
                    getattr(unsealed, RECEIPT)["pricing"]["status"],
                    PRICING_STATUS_UNKNOWN)

                moved = _posting(_with_an_unknown_price())
                door(moved, **{RECEIPT: _receipt(
                    effective_at="2020-01-01T00:00:00+00:00")})
                moved.refresh_from_db()
                self.assertEqual(getattr(moved, RECEIPT)["effective_at"],
                                 "2020-01-01T00:00:00+00:00")

                twice = _posting(_with_an_unknown_price())
                door(twice, **{RECEIPT: _receipt()})
                door(twice, **{RECEIPT: _priced_at(7_777)})
                twice.refresh_from_db()
                self.assertEqual(
                    getattr(twice, RECEIPT)["totals"][PRICE], 7_777)

                admitted = _posting(_with_an_unknown_price())
                door(admitted, **{RECEIPT: _receipt()})
                admitted.refresh_from_db()
                self.assertEqual(
                    getattr(admitted, RECEIPT)["totals"][PRICE], 4_800)

        neighbour = _posting(_sealed(), **{PRICE: 100,
                                           PRICING_STATUS: PRICING_STATUS_KNOWN})
        with self.assertRaises(IntegrityError) as refusal:
            with transaction.atomic():
                _through_the_queryset(
                    neighbour, **{PRICE: 999, RECEIPT: _with_an_unknown_price()})
        self.assertIn(PRICE, str(refusal.exception))

    def test_the_column_is_named_by_the_shipped_rule_in_a_refusing_branch(self):
        """The distinction the check cannot draw, drawn here by hand.

        The toothless body above and the shipped one are both bodies in which a
        word-boundary search for the column succeeds. What separates them is a
        `RAISE` reachable from the branch that names it — a property no regex
        over the concatenated definitions can express, and the reason this
        module's other classes are the evidence rather than this one.
        """
        _, shipped = _this_trigger()
        self.assertTrue(re.search(rf"\b{RECEIPT}\b", shipped))
        self.assertIn("RAISE EXCEPTION", shipped)
        self.assertNotIn("RAISE", TOOTHLESS)
