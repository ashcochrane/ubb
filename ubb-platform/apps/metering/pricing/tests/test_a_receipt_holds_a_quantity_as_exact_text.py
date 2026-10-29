"""Receipt schema v2: a component's quantity is its canonical exact
text (#603; the owner's ruling `6279966961`; ADR-0020).

The version says what a component's quantity IS. Schema 1 held a whole NUMBER and
schema 2 holds the canonical TEXT UBB makes of an admitted quantity, which the
measurement record and the acknowledgement carry too; a writer built today
emits schema 2 only. Until the cutover (#190) every reader also read the
pre-version shape and schema 1 — an old receipt was read, never rewritten — so
the recovery reader, `recorded_quantities`, knew both spellings. The cutover
deleted the older readers (ruling 8, ADR-0026): the fresh database holds no
receipt in either older shape, and every reader now refuses one rather than
reading it, which is the half of this module that inverted.

The pricing engine version moved with it, because exact negative ties and a
fixed component on a negative quantity now come out differently from what the
2.1.0 arithmetic would have made of them (receipts.py's own rule for that
version).
"""
import copy

import pytest

from apps.metering.pricing import receipts
from apps.metering.pricing.receipts import (
    PRICING_STATUS_REASON_KEY,
    QUANTITY_KEY,
    RECEIPT_SCHEMA_VERSION,
    ReceiptShapeError,
    completed_receipt,
    recorded_quantities,
    validate_receipt,
)
from apps.metering.pricing.services.pricing_service import (
    PRICING_ENGINE_VERSION, PricingSubject, resolve_price)
from apps.metering.pricing.tests._helpers import (
    a_usage_event_subject, cost_rate_in_default_book, rate_in_default_book)
from apps.platform.tenants.models import Tenant
from django.utils import timezone

THE_QUANTITIES = {"calls": "12", "seconds": "2.5", "credit": "-3",
                  "none": "0", "uncosted": "9007199254740993"}

#: The version the sectioned shape carried before #603 made a quantity text —
#: spelled, because the constant naming it was deleted with its reader (#190).
SCHEMA_ONE = 1


def a_receipt_resolved_today(tenant):
    """A receipt the engine builds today, over every shape of quantity: two
    costed and priced, one costed only, one priced only — and one no rule
    costs, so it is kept in the uncosted mapping."""
    for code in ("calls", "seconds", "credit"):
        cost_rate_in_default_book(tenant, measurement_key=code,
                                  rate_per_unit_micros=1, unit_quantity=1)
    for code in ("calls", "none"):
        rate_in_default_book(tenant, measurement_key=code,
                             rate_per_unit_micros=10, unit_quantity=1)
    return resolve_price(
        PricingSubject(
            receipt_subject=a_usage_event_subject(), tenant=tenant,
            customer=None, selectors={}, measurements=dict(THE_QUANTITIES),
            currency="usd"),
        timezone.now())


def as_schema_1(receipt):
    """The same record as schema 1 held it: each quantity a whole number.

    Built by moving a schema-2 record back rather than by hand, so the two
    differ in exactly the spelling the version names. Only whole quantities
    are carried — schema 1 could hold nothing else.
    """
    older = copy.deepcopy(receipt)
    older["receipt_schema_version"] = SCHEMA_ONE
    for name in ("costing", "pricing"):
        older[name]["detail"]["components"] = [
            {**component, QUANTITY_KEY: int(component[QUANTITY_KEY])}
            for component in older[name]["detail"].get("components", [])
            if "." not in component[QUANTITY_KEY]]
    detail = older["costing"]["detail"]
    detail["uncosted_quantities"] = {
        key: int(value) for key, value in detail["uncosted_quantities"].items()}
    return older


@pytest.mark.django_db
class TestAWriterEmitsSchemaTwo:

    def test_the_versions_are_the_ones_the_rulings_set(self):
        """The schema is the owner's ruling on #603, and since the cutover
        (#190, ruling 8) it is the only one: the readable set beside it, which
        held the pre-version shape and schema 1 too, is deleted with their
        readers. The engine moved again after #603 — 2.2.0 to 3.0.0, #568's —
        under the rule its own constant states: a held name now computes
        differently for inputs that were legal before."""
        assert RECEIPT_SCHEMA_VERSION == 2
        assert PRICING_ENGINE_VERSION == "3.0.0"

    def test_a_receipt_built_today_holds_its_quantities_as_canonical_text(
            self):
        receipt = a_receipt_resolved_today(Tenant.objects.create(name="R"))

        assert receipt["receipt_schema_version"] == 2
        assert receipt["pricing_engine_version"] == PRICING_ENGINE_VERSION
        held = {c["measurement_key"]: c[QUANTITY_KEY]
                 for name in ("costing", "pricing")
                 for c in receipt[name]["detail"]["components"]}
        assert held == {"calls": "12", "seconds": "2.5", "credit": "-3",
                         "none": "0"}
        assert all(isinstance(value, str) for value in held.values())
        assert receipt["costing"]["detail"]["uncosted_quantities"] == {
            "uncosted": "9007199254740993", "none": "0"}

    def test_the_price_section_says_why_its_status_applies(self):
        receipt = a_receipt_resolved_today(Tenant.objects.create(name="R"))

        assert PRICING_STATUS_REASON_KEY in receipt["pricing"]["detail"]
        assert receipt["pricing"]["detail"][PRICING_STATUS_REASON_KEY] is None

    def test_the_boundary_refuses_schema_two_holding_a_number(self):
        receipt = a_receipt_resolved_today(Tenant.objects.create(name="R"))
        broken = copy.deepcopy(receipt)
        broken["costing"]["detail"]["components"][0][QUANTITY_KEY] = 12

        with pytest.raises(ReceiptShapeError, match="canonical"):
            validate_receipt(broken)

    def test_the_boundary_refuses_a_quantity_that_is_not_canonical(self):
        receipt = a_receipt_resolved_today(Tenant.objects.create(name="R"))
        for spelling in ("012", "2.50", "-0", "1e3", " 1"):
            broken = copy.deepcopy(receipt)
            broken["costing"]["detail"]["components"][0][QUANTITY_KEY] = (
                spelling)
            with pytest.raises(ReceiptShapeError):
                validate_receipt(broken)


@pytest.mark.django_db
class TestTheRecoveryReaderReadsTheOneShape:
    """Schema 2 is read; the older shapes are refused, never read (#190).

    Until the cutover this class was `TestEveryReaderReadsEveryShape`: the
    recovery reader answered the same exact bag for schema 1 and schema 2, the
    pre-version shape answered an empty one, and an older receipt was read but
    never completed. Ruling 8 deleted the older readers, so each of those reads
    became a refusal by the guard every reader shares.
    """

    def test_the_recovery_reader_answers_the_exact_bag_and_refuses_schema_one(
            self):
        current = a_receipt_resolved_today(Tenant.objects.create(name="R"))

        assert recorded_quantities(current) == THE_QUANTITIES
        with pytest.raises(ReceiptShapeError, match="schema version 1;"):
            recorded_quantities(as_schema_1(current))

    def test_the_pre_version_shape_is_refused(self):
        for older in ({"uncosted_measurement_keys": ["x"],
                       "provider_cost_micros": 4},
                      {"receipt_schema_version": 0}):
            with pytest.raises(ReceiptShapeError, match="schema version"):
                recorded_quantities(older)

    def test_an_older_receipt_is_neither_read_nor_completed(self):
        """Read, never rewritten (#148 §4.6) was the older shape's whole
        treatment; since the cutover it is not read either, and the
        completion boundary refuses it by the same guard the readers share
        (`receipts._a_receipt`) — so a run meeting one raises rather than
        leaving the posting alone. The current shape is the control."""
        current = a_receipt_resolved_today(Tenant.objects.create(name="R"))
        older = as_schema_1(current)

        with pytest.raises(ReceiptShapeError, match="schema version 1;"):
            receipts.uncosted_quantity_keys(older)
        with pytest.raises(ReceiptShapeError, match="schema version 1;"):
            completed_receipt(older, sections={})
        assert completed_receipt(current, sections={}) == current
