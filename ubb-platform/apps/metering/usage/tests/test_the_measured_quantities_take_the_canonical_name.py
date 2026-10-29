"""The measured-quantity bag takes the canonical measurement name (#274).

The bag was named for the act of metering. It is now named for the thing each
of its keys is a key **into** — the declarations #263 built beneath an Event
Type — and that is the whole point of the rename: a declared quantity is
*costable*, and an undeclared one is merely carried. The old name described a
container; the new one names a lookup.

**Nothing behavioural moves with it.** An unmatched quantity still meets a
`continue` on the price side and still contributes nothing, silently. Naming the
field for the declaration it keys into is what makes that mismatch *describable*;
slice 3 is what makes it *visible*. This module is deliberately quiet about it —
what a caller may still send is `api/v1/tests/test_a_recorded_quantity_is_exact_text.py`'s
subject (the module this once cited went with #603, which admitted negatives).

**THE RETIRED NAMES ARE NEVER SPELLED HERE.** They are read off the registry
that retired them instead — `retired.yaml`'s `measurement_key`, whose
`retired_aliases` include the bag's old name — through
`api.v1.tests._helpers.retired_aliases`. Every alias of the concept is asserted
absent, which is wider than the one column name the rename moved and is the
true claim: the bag answers to none of them. The reason for not spelling one is
about *this* file: a test module is a living surface, so spelling a retired
word here would re-open an extent that was paid off, and the choice would then
be a hand-written exclusion or a false ledger count.

Before the cutover (#190) the old name was read off `usage/0034`'s
`RenameField`, and a class here held that migration to ADR-0007 §1 — a rename
and never an add-plus-remove, with a row written before it read after it. Those
were facts about one migration's operations, and they retired with the chain.
"""

from functools import cache
from unittest.mock import patch

from django.core.exceptions import FieldDoesNotExist
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from api.v1.openapi_export import GIT_ROOT
from api.v1.tests._helpers import retired_aliases
from apps.metering.usage.models import Posting, PostingMeasurement
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.customers.models import Customer
from apps.platform.event_types.tests._helpers import (
    DECLARED, declares_a_caller_supplied_cost)
from apps.platform.event_types.models import Measurement
from apps.platform.tenants.models import Tenant, TenantApiKey

import json
from apps.metering.usage.tests._helpers import a_posting

#: The canonical name, which is free to be written down.
CANONICAL_COLUMN = "measurements"

#: The retired names, read off the registry — every alias the concept retired,
#: the bag's old column name among them. A tuple, so a case asks about each.
RETIRED_COLUMNS = tuple(retired_aliases("retired", "measurement_key"))

#: The three published schemas the bag appears on. Named rather than discovered:
#: a walk that found two would report success just as loudly.
PUBLISHED_SCHEMAS = (
    "RecordUsageRequest",
    "RecordUsageResponse",
    "UsageEventDetailOut",
)

@cache
def schemas():
    """The published contract's schema block.

    Read on first use rather than at import, because another test module
    imports `RETIRED_COLUMNS` from here and should not acquire a dependency on
    the spec file to get it.
    """
    return json.loads(
        (GIT_ROOT / "openapi" / "v1.json").read_text(encoding="utf-8")
    )["components"]["schemas"]


# A `correlation_field()` helper stood here, and #411 deleted it with its
# subject. It read the recording request's OTHER required identifier off the
# published contract rather than writing it down, because that word was retired
# and under a spread ceiling a later ticket owned. That ticket has landed: the
# field is gone, `customer_id` and `idempotency_key` are the whole required set,
# and the helper's one-element unpack — its own guard against a fourth required
# field arriving unnoticed — had nothing left to unpack.


def _tenant_and_customer():
    tenant = Tenant.objects.create(name="T")
    return tenant, Customer.objects.create(tenant=tenant, external_id="c1")


def _live_columns():
    with connection.cursor() as cursor:
        return {column.name for column in
                connection.introspection.get_table_description(
                    cursor, PostingMeasurement._meta.db_table)}


class TheNameIsTheDeclarationsOwnTest(TestCase):
    """The rename's actual claim, and the only one worth making about a word.

    A rename that merely swapped one invented noun for another would satisfy the
    forbidden-term sweep and mean nothing. What makes this one true is that the
    bag now carries **the same name the declarations already carry**: the keys in
    it are codes of `Measurement` records hanging off an Event Type, and the
    accessor that reaches those records from the other direction is spelled the
    same way. Read from the declaration's own relation rather than typed twice,
    so that renaming either one without the other fails here.
    """

    def test_the_bag_is_named_for_what_it_is_a_key_into(self):
        accessor = (Measurement._meta.get_field("event_type")
                    .remote_field.get_accessor_name())
        self.assertEqual(CANONICAL_COLUMN, accessor)


class TheColumnCarriesTheCanonicalNameTest(TestCase):

    def test_the_record_declares_the_canonical_column(self):
        field = PostingMeasurement._meta.get_field(CANONICAL_COLUMN)
        self.assertEqual(field.get_internal_type(), "JSONField")

    def test_the_retired_column_is_gone_from_the_model(self):
        for retired in RETIRED_COLUMNS:
            with self.subTest(retired=retired):
                with self.assertRaises(FieldDoesNotExist):
                    PostingMeasurement._meta.get_field(retired)

    def test_the_table_carries_the_canonical_column_and_not_the_retired_one(self):
        """The model and the table are two separate claims.

        A field named on the model one way while the schema carries another
        leaves the old column in the database, where a raw query would still
        find it.
        """
        columns = _live_columns()
        self.assertIn(CANONICAL_COLUMN, columns)
        for retired in RETIRED_COLUMNS:
            with self.subTest(retired=retired):
                self.assertNotIn(retired, columns)

    # The column's ADR-0007 §2 transition class is NOT re-asserted here.
    # `test_posting_measurement.py::TransitionClassesAreDeclaredTest` already
    # compares the declaration against `_meta.fields`, so a rename that moved
    # the field and not its declaration fails there — in the module that owns
    # the record. A second copy would fail in two places for one cause and
    # would be the one likelier to rot.


class ThePostingReadsItsQuantitiesUnderTheCanonicalNameTest(TestCase):
    """The read-only accessor #270 left on the posting moves with the column."""

    def setUp(self):
        self.tenant, self.customer = _tenant_and_customer()
        self.posting = a_posting(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="idem_1", provider_cost_micros=1_000_000)

    def _measure(self, quantities):
        return PostingMeasurement.objects.create(
            posting=self.posting, recorded_at=timezone.now(),
            **{CANONICAL_COLUMN: quantities})

    def test_the_accessor_serves_the_childs_bag(self):
        self._measure({"input_tokens": "1200"})
        self.assertEqual(getattr(self.posting, CANONICAL_COLUMN),
                         {"input_tokens": "1200"})

    def test_the_retired_accessor_is_gone(self):
        self._measure({"input_tokens": "1200"})
        for retired in RETIRED_COLUMNS:
            with self.subTest(retired=retired):
                self.assertFalse(hasattr(self.posting, retired))

    def test_the_accessor_is_still_read_only(self):
        """One encoding of the quantities, and it lives on the child.

        ADR-0006 §4 is why this may be served and never written back; a writer
        that quietly succeeded here would be filling a column that is not there.
        """
        self._measure({"input_tokens": "1200"})
        with self.assertRaises(AttributeError):
            setattr(self.posting, CANONICAL_COLUMN, {"input_tokens": "9"})

    def test_an_absent_child_still_answers_an_empty_bag(self):
        self.assertEqual(getattr(self.posting, CANONICAL_COLUMN), {})


class TheRecordingPathWritesTheCanonicalColumnTest(TestCase):
    """End to end through the keyword surface both recording endpoints speak."""

    def setUp(self):
        self.tenant, self.customer = _tenant_and_customer()

    def test_the_quantities_reach_the_child_record(self):
        # Three positional arguments, and the third is the idempotency key.
        # There was a fourth until #411 — a second correlation value passed
        # positionally here precisely so this file never named it, while its
        # ledger entry still capped how many files could. The field is gone and
        # so is the entry, so the key below is simply the argument it looks like.
        result = UsageService.record_usage(
            self.tenant, self.customer, "idem_recorded",
            provider_cost_micros=1_000_000,
            **{CANONICAL_COLUMN: {"input_tokens": "1200", "output_tokens": "480"}})
        posting = Posting.objects.get(id=result["event_id"])
        self.assertEqual(
            getattr(posting.measurement, CANONICAL_COLUMN),
            {"input_tokens": "1200", "output_tokens": "480"})

    def test_the_acknowledgement_answers_under_the_canonical_name(self):
        result = UsageService.record_usage(
            self.tenant, self.customer, "idem_acked",
            provider_cost_micros=1_000_000,
            **{CANONICAL_COLUMN: {"input_tokens": "7"}})
        self.assertEqual(result[CANONICAL_COLUMN], {"input_tokens": "7"})
        for retired in RETIRED_COLUMNS:
            with self.subTest(retired=retired):
                self.assertNotIn(retired, result)


class TheContractCarriesTheFinalNameTest(SimpleTestCase):
    """ADR-0007 §3: the final name, on the published document, in this slice.

    The sweep proves the retired word has left the contract. It cannot prove the
    canonical one arrived — a rename that dropped the property altogether would
    clear the extent just as cleanly, and every client generated from the
    document would silently stop sending a quantity.
    """

    def test_every_published_schema_carries_the_canonical_property(self):
        for name in PUBLISHED_SCHEMAS:
            with self.subTest(schema=name):
                self.assertIn(CANONICAL_COLUMN, schemas()[name]["properties"])

    def test_no_published_schema_carries_the_retired_property(self):
        for name, schema in schemas().items():
            for retired in RETIRED_COLUMNS:
                with self.subTest(schema=name, retired=retired):
                    self.assertNotIn(retired, schema.get("properties", {}))

    def test_the_detail_response_pairs_the_bag_with_its_status(self):
        """The status field was named for this bag before the bag was.

        `measurements_status` says what an empty bag MEANS — pruned, never
        applicable, or genuinely empty. Until now it sat beside a differently
        named field and a reader had to be told they were about the same thing.
        """
        properties = schemas()["UsageEventDetailOut"]["properties"]
        self.assertIn(CANONICAL_COLUMN, properties)
        self.assertIn(f"{CANONICAL_COLUMN}_status", properties)


class TheStaleCallerIsAcceptedAndItsQuantitiesAreDroppedTest(TestCase):
    """WHAT THE RENAME COSTS A CALLER THAT HAS NOT MIGRATED YET.

    Taking the property off the request schema does **not** make a stale request
    fail. django-ninja keeps pydantic's `extra="ignore"`, so the retired key is
    accepted and thrown away, and the posting records with no quantities at all.

    **This one costs money, and the block in `oasdiff-warn-ignore.txt` says so.**
    Where the fold before it dropped labels, this drops the numbers the engine
    prices from: a caller relying on server-side pricing is charged as though it
    measured nothing. `test_record_usage_pricing.py` runs that end to end against
    a real cost card rather than leaving it as an inference from here.

    Pinned rather than repaired. Refusing an unknown field is a decision about
    every schema on the contract, and this ticket owns one field on three of
    them; the pre-live window (ADR-0007 §5) is what makes the break free, and the
    migration is a one-line rename in the caller.
    """

    def setUp(self):
        self.tenant, self.customer = _tenant_and_customer()
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        # The body below states the supplier's own cost, admissible only
        # against an Event Type that declares it arrives on the call (#324).
        declares_a_caller_supplied_cost(self.tenant, DECLARED)

    def _post(self, bag_key):
        return self.client.post(
            "/api/v1/metering/usage",
            data=json.dumps({
                "customer_id": str(self.customer.id),
                "idempotency_key": f"idem_{bag_key}",
                "event_type": DECLARED,
                "provider_cost_micros": 1_000_000,
                bag_key: {"input_tokens": "1200"},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_the_retired_key_is_ignored_rather_than_refused(self, mock_process):
        for retired in RETIRED_COLUMNS:
            with self.subTest(retired=retired):
                response = self._post(retired)

                self.assertEqual(response.status_code, 200)
                posting = Posting.objects.get(idempotency_key=f"idem_{retired}")
                self.assertEqual(getattr(posting, CANONICAL_COLUMN), {})

    @patch("apps.platform.events.tasks.process_single_event")
    def test_the_canonical_key_is_the_one_that_lands(self, mock_process):
        """The control. Without it the test above passes on a broken endpoint."""
        response = self._post(CANONICAL_COLUMN)

        self.assertEqual(response.status_code, 200)
        posting = Posting.objects.get(idempotency_key=f"idem_{CANONICAL_COLUMN}")
        self.assertEqual(getattr(posting, CANONICAL_COLUMN),
                         {"input_tokens": "1200"})
