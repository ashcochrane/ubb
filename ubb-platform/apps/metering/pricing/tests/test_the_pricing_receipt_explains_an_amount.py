"""The receipt's shape, and the one boundary that refuses a record without it.

Everything here drives `build_receipt` and the reader beside it directly. That
is the point of the seam: what is worth asserting about the record — both
versions, the typed subject, the two sections, the amount/status/method
agreement, and what `provenance` may hold — is otherwise only visible through a
recording endpoint, one fixture per case, with a serialiser between the
assertion and the behaviour.

What is NOT here, deliberately: anything about persistence. Whether a receipt
can reach the column without passing through this function is a question about
the tree and about the recording path, and it is asked where the column is —
`apps/metering/usage/tests/test_the_receipt_has_one_construction_boundary.py`.
"""
import pytest

from apps.metering.pricing import receipts
from apps.metering.pricing.receipts import (
    LEGACY_SCHEMA_VERSION,
    MARKUP_TERMS_KEY,
    RECEIPT_SCHEMA_VERSION,
    REQUIRED_COMPONENT_KEYS,
    REQUIRED_MARKUP_KEYS,
    SECTIONED_SCHEMA_VERSION,
    ReceiptShapeError,
    ReceiptSubject,
    Resolution,
    build_receipt,
    pricing_method_of,
    schema_version_of,
    uncosted_quantity_keys,
)
from apps.metering.pricing.tests._helpers import markup_terms
from core.vocabulary import (
    COSTING_METHOD_CALCULATED,
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_NOT_APPLICABLE,
    COSTING_STATUS_UNRESOLVED,
    PRICING_METHOD_DIRECT_EVENT_PRICE,
    PRICING_METHOD_MARGIN_OVER_COST,
    PRICING_RECEIPT_SUBJECT_TYPE_CHARGE,
    PRICING_RECEIPT_SUBJECT_TYPE_USAGE_EVENT,
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_NOT_APPLICABLE,
    PRICING_STATUS_UNKNOWN,
)

SUBJECT = ReceiptSubject(
    subject_type=PRICING_RECEIPT_SUBJECT_TYPE_USAGE_EVENT,
    subject_id="11111111-1111-1111-1111-111111111111")

#: THE TERMS A MARGIN OVER COST HAS TO CARRY (#357), in the amounts the settled
#: fixtures below already use: 20% of a 4_000 basis is 800, so the 4_800 those
#: fixtures were written with is the sum of these terms rather than a number
#: chosen to look plausible beside them.
MARKUP_TERMS = markup_terms(4_000, micro_percent=20_000_000)

#: A receipt in the shape written before the record carried a version at all.
#: Rows like this exist and are READ, never rewritten: a receipt records what
#: the engine did on a day, and back-dating one to a shape that did not exist
#: then would make it a worse record rather than a better one.
A_RECEIPT_IN_THE_OLDER_SHAPE = {
    "engine_version": "2.1.0",
    "cost_source": "caller",
    "price_source": "markup",
    "uncosted_measurement_keys": ["image_pixels"],
    "provider_cost_micros": 4_000,
    "billed_cost_micros": 4_800,
}


def a_receipt(**overrides):
    """A settled receipt, with one field at a time moved by a caller."""
    fields = {
        "subject": SUBJECT,
        "effective_at": "2026-08-18T09:00:00+00:00",
        "currency": "usd",
        "pricing_engine_version": "2.1.0",
        "costing": Resolution(method=COSTING_METHOD_CALCULATED,
                              status=COSTING_STATUS_KNOWN, amount_micros=4_000,
                              detail={"components": [],
                                      "uncosted_measurement_keys": []}),
        "pricing": Resolution(method=PRICING_METHOD_MARGIN_OVER_COST,
                              status=PRICING_STATUS_KNOWN, amount_micros=4_800,
                              detail={"components": [],
                                      MARKUP_TERMS_KEY: MARKUP_TERMS}),
        "provenance": {"cost_rate_ids": {}, "price_rate_ids": {}},
    }
    fields.update(overrides)
    return build_receipt(**fields)


class TestTheRecordCarriesWhatExplainsAnAmount:
    def test_it_carries_both_versions_the_typed_subject_and_three_sections(self):
        receipt = a_receipt()

        assert receipt["receipt_schema_version"] == RECEIPT_SCHEMA_VERSION
        assert receipt["pricing_engine_version"] == "2.1.0"
        assert receipt["subject_type"] == PRICING_RECEIPT_SUBJECT_TYPE_USAGE_EVENT
        assert receipt["subject_id"] == SUBJECT.subject_id
        assert set(receipt["costing"]) == {"method", "status", "detail"}
        assert set(receipt["pricing"]) == {"method", "status", "detail"}
        assert set(receipt["totals"]) == {"provider_cost_micros",
                                          "billed_cost_micros"}
        assert receipt["provenance"] == {"cost_rate_ids": {},
                                         "price_rate_ids": {}}

    def test_the_two_versions_are_two_fields_and_answer_two_questions(self):
        """A reshuffled key is not a repriced event, so one field cannot say
        both. The engine's version moves with a number; the schema's moves with
        the shape, and here they differ in the same record."""
        receipt = a_receipt(pricing_engine_version="99.0.0")

        assert receipt["pricing_engine_version"] == "99.0.0"
        assert receipt["receipt_schema_version"] == RECEIPT_SCHEMA_VERSION

    def test_a_charge_is_the_other_subject_a_receipt_may_explain(self):
        receipt = a_receipt(subject=ReceiptSubject(
            subject_type=PRICING_RECEIPT_SUBJECT_TYPE_CHARGE, subject_id="c1"))

        assert receipt["subject_type"] == PRICING_RECEIPT_SUBJECT_TYPE_CHARGE

    def test_the_detail_containers_exist_even_where_nothing_fills_them(self):
        """The record's frame is fixed and its content containers are open —
        which is what lets the content obligation be written into an existing
        record rather than reshaping it a second time."""
        receipt = a_receipt(costing=Resolution(
            method=None, status=COSTING_STATUS_NOT_APPLICABLE,
            amount_micros=None, detail={}))

        assert receipt["costing"]["detail"] == {}


class TestTheRecordIsReadAtTheVersionItDeclares:
    def test_a_receipt_written_now_still_reads_when_the_code_has_moved_on(
            self, monkeypatch):
        """The reader dispatches on the RECORD's version, never on the module's.

        Simulated by moving the module's constant on and asking the same
        questions of a record written before it moved: an answer that changed
        would mean the reader was consulting the code's idea of the shape rather
        than the record's own.
        """
        written = a_receipt(costing=Resolution(
            method=None, status=COSTING_STATUS_UNRESOLVED, amount_micros=None,
            detail={"components": [],
                    "uncosted_measurement_keys": ["image_pixels"]}))
        before = uncosted_quantity_keys(written)

        monkeypatch.setattr(receipts, "RECEIPT_SCHEMA_VERSION",
                            RECEIPT_SCHEMA_VERSION + 1)

        assert schema_version_of(written) == SECTIONED_SCHEMA_VERSION
        assert uncosted_quantity_keys(written) == before

    def test_a_shape_this_code_does_not_know_is_refused_rather_than_guessed(self):
        """The other direction, and it is not symmetrical. A record written by
        something newer cannot be read by guessing — guessing turns a shape this
        code does not understand into a plausible wrong answer, or into a
        `KeyError` from the middle of a request."""
        from_the_future = dict(a_receipt(),
                               receipt_schema_version=SECTIONED_SCHEMA_VERSION + 1)

        with pytest.raises(ReceiptShapeError, match="schema version"):
            uncosted_quantity_keys(from_the_future)

    def test_a_receipt_in_the_older_shape_is_read_rather_than_refused(self):
        """The read path tolerates both shapes. Nothing rewrites the older one:
        this is the shape rows on disk are already in."""
        older = A_RECEIPT_IN_THE_OLDER_SHAPE

        assert schema_version_of(older) == LEGACY_SCHEMA_VERSION
        assert uncosted_quantity_keys(older) == ["image_pixels"]
        assert older["provider_cost_micros"] == 4_000

    def test_the_method_reader_dispatches_the_same_three_ways(self):
        """The second reader over this record, and the same three-way dispatch
        (#355) — because a reader that guessed would turn a shape it does not
        understand into a plausible wrong answer about how money was derived.

        ⚠ **AN OLDER RECEIPT ANSWERS `None`, AND THAT IS NOT A GAP.** What that
        shape recorded beside its price is the SOURCE that supplied it, which is
        a different question: a markup and a rule declaring a margin are one
        method at two sources. Reading the older field as a method would publish
        a value no writer ever recorded, under a mapping nobody ratified.
        """
        current = a_receipt()

        assert pricing_method_of(current) == PRICING_METHOD_MARGIN_OVER_COST
        assert pricing_method_of(A_RECEIPT_IN_THE_OLDER_SHAPE) is None
        assert "price_source" in A_RECEIPT_IN_THE_OLDER_SHAPE

        with pytest.raises(ReceiptShapeError, match="schema version"):
            pricing_method_of(dict(current,
                                   receipt_schema_version=
                                   SECTIONED_SCHEMA_VERSION + 1))

    def test_a_price_that_was_not_derived_reads_back_as_no_method(self):
        """AC: null means the price was NOT DERIVED, and the status says why.

        The two travel together by construction — the boundary refuses a record
        whose method and status disagree — so this asserts the pair a reader
        actually gets rather than the null alone.
        """
        not_derived = a_receipt(pricing=Resolution(
            method=None, status=PRICING_STATUS_NOT_APPLICABLE,
            amount_micros=None, detail={"components": []}))

        assert pricing_method_of(not_derived) is None
        assert (not_derived["pricing"]["status"]
                == PRICING_STATUS_NOT_APPLICABLE)

    def test_the_two_shapes_answer_the_same_questions_the_same_way(self):
        current = a_receipt(costing=Resolution(
            method=None, status=COSTING_STATUS_UNRESOLVED, amount_micros=None,
            detail={"components": [],
                    "uncosted_measurement_keys": ["image_pixels"]}))

        assert (uncosted_quantity_keys(current)
                == uncosted_quantity_keys(A_RECEIPT_IN_THE_OLDER_SHAPE))


class TestTheBoundaryRefusesARecordThatExplainsNothing:
    def test_an_unknown_top_level_key_is_refused(self):
        receipt = a_receipt()
        receipt["notes"] = "hello"

        with pytest.raises(ReceiptShapeError, match="exactly"):
            receipts.validate_receipt(receipt)

    def test_a_record_declaring_another_schema_version_is_refused(self):
        receipt = a_receipt()
        receipt["receipt_schema_version"] = RECEIPT_SCHEMA_VERSION + 1

        with pytest.raises(ReceiptShapeError, match="receipt_schema_version"):
            receipts.validate_receipt(receipt)

    def test_a_subject_type_outside_the_ratified_two_is_refused(self):
        with pytest.raises(ReceiptShapeError, match="subject_type"):
            a_receipt(subject=ReceiptSubject(subject_type="invoice_line",
                                             subject_id="x"))

    def test_a_subject_with_no_id_is_refused(self):
        with pytest.raises(ReceiptShapeError, match="subject_id"):
            a_receipt(subject=ReceiptSubject(
                subject_type=PRICING_RECEIPT_SUBJECT_TYPE_USAGE_EVENT,
                subject_id=""))

    def test_a_section_whose_detail_is_not_a_record_is_refused(self):
        with pytest.raises(ReceiptShapeError, match="detail"):
            a_receipt(pricing=Resolution(
                method=PRICING_METHOD_DIRECT_EVENT_PRICE,
                status=PRICING_STATUS_KNOWN, amount_micros=1,
                detail=["components"]))

    def test_a_status_outside_its_own_vocabulary_is_refused(self):
        with pytest.raises(ReceiptShapeError, match="pricing.status"):
            a_receipt(pricing=Resolution(
                method=PRICING_METHOD_DIRECT_EVENT_PRICE, status="settled",
                amount_micros=1, detail={}))

    def test_a_cost_status_is_not_a_price_status(self):
        """The two vocabularies are not interchangeable and the boundary knows
        which section it is asking about — `unresolved` is a costing answer and
        says nothing about a customer price."""
        with pytest.raises(ReceiptShapeError, match="pricing.status"):
            a_receipt(pricing=Resolution(
                method=None, status=COSTING_STATUS_UNRESOLVED,
                amount_micros=None, detail={}))


class TestAnAmountItsStatusAndItsMethodMoveTogether:
    def test_a_price_that_was_not_derived_names_no_method(self):
        receipt = a_receipt(pricing=Resolution(
            method=None, status=PRICING_STATUS_UNKNOWN, amount_micros=None,
            detail={"components": []}))

        assert receipt["pricing"]["method"] is None
        assert receipt["pricing"]["status"] == PRICING_STATUS_UNKNOWN
        assert receipt["totals"]["billed_cost_micros"] is None

    def test_a_price_that_was_not_derived_may_not_name_one_anyway(self):
        with pytest.raises(ReceiptShapeError, match="pricing.method"):
            a_receipt(pricing=Resolution(
                method=PRICING_METHOD_MARGIN_OVER_COST,
                status=PRICING_STATUS_NOT_APPLICABLE, amount_micros=None,
                detail={}))

    def test_a_settled_price_has_to_say_how_it_was_derived(self):
        with pytest.raises(ReceiptShapeError, match="pricing.method"):
            a_receipt(pricing=Resolution(
                method=None, status=PRICING_STATUS_KNOWN, amount_micros=1,
                detail={}))

    def test_no_fourth_method_value_stands_in_for_none(self):
        """A method meaning "there wasn't one" is a second encoding of the
        status, and the day the two disagree nothing says which is right."""
        with pytest.raises(ReceiptShapeError, match="pricing.method"):
            a_receipt(pricing=Resolution(
                method="none", status=PRICING_STATUS_KNOWN, amount_micros=1,
                detail={}))

    def test_an_amount_beside_an_unsettled_status_is_refused(self):
        with pytest.raises(ReceiptShapeError, match="billed_cost_micros"):
            a_receipt(pricing=Resolution(
                method=None, status=PRICING_STATUS_UNKNOWN, amount_micros=0,
                detail={}))

    def test_a_settled_status_with_no_amount_is_refused(self):
        with pytest.raises(ReceiptShapeError, match="provider_cost_micros"):
            a_receipt(costing=Resolution(
                method=COSTING_METHOD_CALCULATED, status=COSTING_STATUS_KNOWN,
                amount_micros=None, detail={}))

    def test_a_settled_zero_is_an_amount(self):
        """A call that genuinely cost nothing is resolved, not missing."""
        receipt = a_receipt(costing=Resolution(
            method=COSTING_METHOD_CALCULATED, status=COSTING_STATUS_KNOWN,
            amount_micros=0, detail={}))

        assert receipt["totals"]["provider_cost_micros"] == 0

    def test_an_amount_that_is_not_a_whole_number_of_micros_is_refused(self):
        with pytest.raises(ReceiptShapeError, match="provider_cost_micros"):
            a_receipt(costing=Resolution(
                method=COSTING_METHOD_CALCULATED, status=COSTING_STATUS_KNOWN,
                amount_micros="4000", detail={}))


class TestProvenanceCarriesIdsAndNothingElse:
    def test_a_figure_in_provenance_is_refused(self):
        """The section's whole job is to be the part of the record nobody can
        reconstruct an amount from. Refusing a number is the strongest form of
        that: there is nothing in there to read back."""
        with pytest.raises(ReceiptShapeError, match="provenance"):
            a_receipt(provenance={"cost_rate_ids": {"tok": "id-1"},
                                  "resolved_micros": 4_000})

    def test_a_figure_nested_inside_provenance_is_refused_too(self):
        with pytest.raises(ReceiptShapeError, match="provenance"):
            a_receipt(provenance={"cost_rate_ids": {"tok": 4_000}})

    def test_ids_keyed_by_what_they_priced_are_what_it_is_for(self):
        receipt = a_receipt(provenance={
            "cost_rate_ids": {"input_tokens": "rate-1"},
            "price_rate_ids": {}})

        assert receipt["provenance"]["cost_rate_ids"] == {
            "input_tokens": "rate-1"}


#: A component carrying every term the record requires, BUILT FROM THE
#: DECLARATION rather than transcribed beside it.
#:
#: Two spellings of one set drift, and the one that drifts is the one nobody is
#: looking at — so the fixture that must satisfy the rule is derived from the
#: rule. The values are placeholders: every assertion below is about which keys
#: are present, and a fixture whose arithmetic had to be consistent would be
#: asserting the engine rather than the boundary.
A_WHOLE_COMPONENT = {key: 1 for key in REQUIRED_COMPONENT_KEYS}


def _resolution_with(section, components):
    """One section's settled resolution, with its components replaced.

    Both are built here rather than one being derived from the other, because
    the sections' value sets are deliberately not assumed to be spelled alike —
    the same reason the boundary asks its rule of each section with that
    section's own rules.
    """
    if section == "costing":
        return Resolution(method=COSTING_METHOD_CALCULATED,
                          status=COSTING_STATUS_KNOWN, amount_micros=4_000,
                          detail={"components": components,
                                  "uncosted_measurement_keys": []})
    return Resolution(method=PRICING_METHOD_MARGIN_OVER_COST,
                      status=PRICING_STATUS_KNOWN, amount_micros=4_800,
                      detail={"components": components,
                              MARKUP_TERMS_KEY: MARKUP_TERMS})


class TestAComponentExplainsItsOwnAmount:
    """The content obligation, at the boundary that refuses (#350).

    The measured detail behind a posting expires and this record does not, so a
    component that does not carry its terms is a line nobody can explain six
    years from now. It is refused where the record is built, rather than left to
    a reader to discover it cannot answer.
    """

    def test_the_declaration_names_the_denominator(self):
        """The vacuity guard, and it names the term most easily forgotten.

        Every case below is derived from `REQUIRED_COMPONENT_KEYS`, so an empty
        or gutted declaration would make all of them pass while proving
        nothing. The denominator is what the assertion anchors on because a
        component holding a rate without the quantity it is per cannot be
        recomputed at all — the rounding is half-up on that number, so the last
        micro of the answer depends on it.
        """
        assert "unit_quantity" in REQUIRED_COMPONENT_KEYS
        assert len(REQUIRED_COMPONENT_KEYS) > 1

    @pytest.mark.parametrize("section", ["costing", "pricing"])
    def test_a_whole_component_is_admitted(self, section):
        receipt = a_receipt(**{section: _resolution_with(
            section, [A_WHOLE_COMPONENT])})

        assert receipt[section]["detail"]["components"] == [A_WHOLE_COMPONENT]

    @pytest.mark.parametrize("section", ["costing", "pricing"])
    @pytest.mark.parametrize("missing", sorted(REQUIRED_COMPONENT_KEYS))
    def test_a_component_missing_any_term_is_refused_in_both_sections(
            self, section, missing):
        """One rule, asked of both sections.

        The price side is not assumed to be checked because the cost side is:
        the two are separate resolutions built in separate branches, and a rule
        applied to one of them is exactly how the sides come to differ where a
        reader compares them.
        """
        short = {key: value for key, value in A_WHOLE_COMPONENT.items()
                 if key != missing}

        with pytest.raises(ReceiptShapeError, match=missing):
            a_receipt(**{section: _resolution_with(section, [short])})

    def test_a_section_that_priced_no_quantity_is_not_a_fault(self):
        """A cost the caller supplied, a declaration that says there is no cost
        and a margin over one all reach an amount without pricing a single
        quantity. What is refused is a component that claims to explain one and
        does not — not the absence of components."""
        receipt = a_receipt()

        assert receipt["costing"]["detail"]["components"] == []
        assert receipt["pricing"]["detail"]["components"] == []

    @pytest.mark.parametrize(
        "not_a_list", [{"input_tokens": 1}, {}, 0, False, "", None])
    def test_something_that_is_not_a_list_of_components_is_refused(
            self, not_a_list):
        """⚠ THE FALSY ONES ARE THE POINT, AND A NON-EMPTY DICT CANNOT FIND THEM.

        The first draft read the key as `detail.get("components") or []`, which
        turns every falsy non-list into "this section priced nothing" on its way
        past the refusal — so an empty record, a zero, a `False` and a `None` all
        sailed through while a populated dict was caught. A control that only
        ever passed the populated one would have been green over the hole.
        """
        with pytest.raises(ReceiptShapeError, match="components"):
            a_receipt(costing=_resolution_with("costing", not_a_list))

    def test_a_section_with_no_components_key_at_all_is_not_a_fault(self):
        """Absent is not the same as malformed.

        A caller-supplied cost prices no quantity and has nothing to say about
        components; the rule above is about what a `components` key CONTAINS,
        not about it being there.
        """
        receipt = a_receipt(costing=Resolution(
            method=COSTING_METHOD_CALCULATED, status=COSTING_STATUS_KNOWN,
            amount_micros=4_000, detail={"uncosted_measurement_keys": []}))

        assert "components" not in receipt["costing"]["detail"]


class TestAMarginSaysWhatPercentageOverWhat:
    """The content obligation on the path that produces most prices (#357).

    Markup is the default pricing path — it runs wherever no rule matched — and
    the record it left said only that a margin had been taken. The percentage
    was then recoverable only by re-reading configuration that can have moved
    since, which is the exact failure the receipt exists to prevent.

    ⚠ **THE RULE BINDS THE METHOD, NOT THE RUNG.** A markup and a rule declaring
    `margin_over_cost` are one method at two rungs, so a boundary that asked
    only of the markup rung would be the second shape this ruling refuses. It
    asks nothing about WHICH rung supplied the percentage: that is a pointer and
    it lives in `provenance`, because the record it names can be edited or
    withdrawn while the terms cannot.
    """

    def _priced_by_a_margin(self, **detail):
        return a_receipt(pricing=Resolution(
            method=PRICING_METHOD_MARGIN_OVER_COST,
            status=PRICING_STATUS_KNOWN, amount_micros=4_800, detail=detail))

    def test_a_margin_carrying_its_terms_is_admitted(self):
        receipt = self._priced_by_a_margin(**{MARKUP_TERMS_KEY: MARKUP_TERMS})

        assert receipt["pricing"]["detail"][MARKUP_TERMS_KEY] == MARKUP_TERMS

    def test_a_margin_with_no_terms_at_all_is_refused(self):
        with pytest.raises(ReceiptShapeError, match=MARKUP_TERMS_KEY):
            self._priced_by_a_margin()

    @pytest.mark.parametrize("term", sorted(REQUIRED_MARKUP_KEYS))
    def test_a_margin_missing_any_one_term_is_refused(self, term):
        """Driven over the set, so a term added to it is shown to be catchable
        rather than assumed to be — and so that dropping one from the writer
        cannot leave a green control behind."""
        with pytest.raises(ReceiptShapeError, match=MARKUP_TERMS_KEY):
            self._priced_by_a_margin(**{MARKUP_TERMS_KEY: {
                name: value for name, value in MARKUP_TERMS.items()
                if name != term}})

    def test_a_fourth_term_is_refused_because_a_margin_never_composes(self):
        """The set is exact and this is the direction that makes it so.

        A floor, a cap or a second addend appearing beside the percentage is the
        chain whose middle terms are on no record — which is what the rule
        against composition exists to prevent (#147 §2), asked of the record
        rather than only of the rule.
        """
        with pytest.raises(ReceiptShapeError, match=MARKUP_TERMS_KEY):
            self._priced_by_a_margin(**{MARKUP_TERMS_KEY: {
                **MARKUP_TERMS, "floor_micros": 10}})

    @pytest.mark.parametrize("not_a_record", [[], "20%", 20_000_000, None])
    def test_terms_that_are_not_a_record_are_refused(self, not_a_record):
        with pytest.raises(ReceiptShapeError, match=MARKUP_TERMS_KEY):
            self._priced_by_a_margin(**{MARKUP_TERMS_KEY: not_a_record})

    @pytest.mark.parametrize("not_a_number", ["20", 20.5, True, None])
    def test_a_term_that_is_not_a_whole_number_is_refused(self, not_a_number):
        """A term a reader cannot do arithmetic with explains nothing, and
        `True` is here because Python would otherwise let a boolean answer for
        a percentage."""
        with pytest.raises(ReceiptShapeError, match="micro_percent"):
            self._priced_by_a_margin(**{MARKUP_TERMS_KEY: {
                **MARKUP_TERMS, "micro_percent": not_a_number}})

    def test_a_price_that_derived_nothing_owes_no_terms(self):
        """A waived or unknown price names no method, so there is no derivation
        to explain — and demanding terms of it would refuse a legitimate
        receipt, which is worse than not asking."""
        receipt = a_receipt(pricing=Resolution(
            method=None, status=PRICING_STATUS_UNKNOWN, amount_micros=None,
            detail={}))

        assert MARKUP_TERMS_KEY not in receipt["pricing"]["detail"]

    def test_the_other_method_owes_no_terms_either(self):
        """A price attached to the event has its components; it took no margin
        over anything, so the rule above is not about it."""
        receipt = a_receipt(pricing=Resolution(
            method=PRICING_METHOD_DIRECT_EVENT_PRICE,
            status=PRICING_STATUS_KNOWN, amount_micros=4_800,
            detail={"components": []}))

        assert MARKUP_TERMS_KEY not in receipt["pricing"]["detail"]
