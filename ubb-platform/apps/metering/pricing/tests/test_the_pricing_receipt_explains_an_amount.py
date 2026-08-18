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
    RECEIPT_SCHEMA_VERSION,
    SECTIONED_SCHEMA_VERSION,
    ReceiptShapeError,
    ReceiptSubject,
    Resolution,
    build_receipt,
    schema_version_of,
    uncosted_quantity_keys,
)
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
                              detail={"components": []}),
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
