"""Receipt schema v2: a component's quantity is its canonical exact
text (#603; the owner's ruling `6279966961`; ADR-0020).

The version says what a component's quantity IS. Schema 1 holds a whole NUMBER and
schema 2 the canonical TEXT the wire, the measurement record and the
acknowledgement carry; a writer built today emits schema 2 only, and every
reader reads the pre-version shape, 1 and 2. An old receipt is read, never
rewritten — so the recovery reader, `recorded_quantities`, has to know both
spellings and answer the same exact bag for either: left reading schema 1
alone, it would have read every new receipt as holding no quantities, and a
Resolution Run would have re-resolved nothing, silently.

The pricing engine version moved with it, because exact negative ties and a
fixed component on a negative quantity now come out differently from what the
2.1.0 arithmetic would have made of them (receipts.py's own rule for that
version).
"""
import copy

import pytest

from apps.metering.pricing import receipts
from apps.metering.pricing.receipts import (
    CANONICAL_QUANTITY_SCHEMA_VERSION,
    LEGACY_SCHEMA_VERSION,
    PRICING_STATUS_REASON_KEY,
    QUANTITY_KEY,
    READABLE_SCHEMA_VERSIONS,
    RECEIPT_SCHEMA_VERSION,
    SECTIONED_SCHEMA_VERSION,
    ReceiptShapeError,
    recorded_quantities,
    validate_receipt,
    written_in_the_current_shape,
)
from apps.metering.pricing.services.pricing_service import (
    PRICING_ENGINE_VERSION, PricingSubject, resolve_price)
from apps.metering.pricing.tests._helpers import (
    a_usage_event_subject, cost_rate_in_default_book, rate_in_default_book)
from apps.platform.tenants.models import Tenant
from django.utils import timezone

THE_QUANTITIES = {"calls": "12", "seconds": "2.5", "credit": "-3",
                  "none": "0", "uncosted": "9007199254740993"}


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
    older["receipt_schema_version"] = SECTIONED_SCHEMA_VERSION
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

    def test_the_versions_are_the_ones_the_owner_ruled(self):
        assert RECEIPT_SCHEMA_VERSION == 2
        assert CANONICAL_QUANTITY_SCHEMA_VERSION == 2
        assert READABLE_SCHEMA_VERSIONS == {0, 1, 2}
        assert PRICING_ENGINE_VERSION == "2.2.0"

    def test_a_receipt_built_today_holds_its_quantities_as_canonical_text(
            self):
        receipt = a_receipt_resolved_today(Tenant.objects.create(name="R"))

        assert receipt["receipt_schema_version"] == 2
        assert receipt["pricing_engine_version"] == "2.2.0"
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
class TestEveryReaderReadsEveryShape:

    def test_the_recovery_reader_answers_the_same_exact_bag_for_one_and_two(
            self):
        current = a_receipt_resolved_today(Tenant.objects.create(name="R"))
        whole_only = {key: value for key, value in THE_QUANTITIES.items()
                      if "." not in value}
        older = as_schema_1(current)

        assert recorded_quantities(current) == THE_QUANTITIES
        assert recorded_quantities(older) == whole_only
        assert all(isinstance(v, str) for v in recorded_quantities(older)
                   .values())

    def test_the_pre_version_shape_answers_empty(self):
        assert recorded_quantities({"uncosted_measurement_keys": ["x"],
                                    "provider_cost_micros": 4}) == {}
        assert recorded_quantities(
            {"receipt_schema_version": LEGACY_SCHEMA_VERSION}) == {}

    def test_schema_one_holding_anything_but_a_whole_number_is_refused(self):
        current = a_receipt_resolved_today(Tenant.objects.create(name="R"))
        older = as_schema_1(current)
        older["costing"]["detail"]["components"][0][QUANTITY_KEY] = "12"

        with pytest.raises(ReceiptShapeError, match="whole number"):
            recorded_quantities(older)

    def test_an_older_receipt_is_read_and_never_completed(self):
        """Read, never rewritten (#148 §4.6): a schema-1 posting cannot be
        completed by a run — this tree is deployed nowhere, so the postings
        that applies to are development data only."""
        current = a_receipt_resolved_today(Tenant.objects.create(name="R"))

        assert written_in_the_current_shape(current)
        assert not written_in_the_current_shape(as_schema_1(current))
        assert receipts.uncosted_quantity_keys(as_schema_1(current)) == (
            receipts.uncosted_quantity_keys(current))
