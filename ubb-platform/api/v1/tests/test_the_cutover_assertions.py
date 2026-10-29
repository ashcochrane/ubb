"""G21 — THE FIVE CUTOVER ASSERTIONS, AS BEHAVIOUR (#153 §13.5; #190 §0.3 point 10).

#153 §13.5's five sentences, verbatim, are what this module holds:

1. *No old posting reaches a balance or a report.*
2. *No undeclared measurement survives.*
3. *No legacy pricing provenance is read.*
4. *Every new event validates against its Event Type.*
5. *Every new monetary record uses the new receipt shape.*

**NONE OF THEM MAY PASS BECAUSE THE FRESH DATABASE IS EMPTY.** Each class records
through the real doors first — the recording routes, a publication, the Charge
projection, the drawdown repair — so its assertion runs over rows that exist,
and each carries a PLANTED violation that the same check reports, so the check
is shown able to fail. #1 and #3 also have a half that reads the CODE (no reader
path survives), in the Django-free contracts suite:
`tests/contracts/test_no_retired_posting_or_receipt_reader_survives.py`.

#1 is a REACHABILITY claim, and that is what it pins (§0.3 point 10): a
pre-remodel posting fact carrying distinctive money is planted where the old
model kept it — the posting's old table, `ubb_usage_event` (usage/0001 until
usage/0030) — and shown READABLE, then shown to reach neither a balance (the
prepaid wallet, through the drawdown repair that debits it from postings) nor a
report (the one economic query). "The old table is absent" is evidence; the
assertion is that no balance or report would read it if it were there.
"""
import datetime
import uuid

from django.apps import apps
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.utils import timezone

from api.v1.tests._helpers import (
    DeclaringTenantCase, OnTheSingleRoute, measure_of)
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.billing.wallets.tasks import reconcile_usage_drawdowns
from apps.metering.pricing.models import Charge
from apps.metering.pricing.receipts import (
    RECEIPT_SCHEMA_VERSION, ReceiptShapeError, completed_receipt,
    pricing_method_of, pricing_mode_of, recorded_quantities, subject_type_of,
    uncosted_quantity_keys, validate_receipt)
from apps.metering.pricing.services.charge_projection import project_the_charge
from apps.metering.pricing.tests._helpers import a_receipt_agreeing_with
from apps.metering.queries import (
    EconomicFilters, economics, get_customer_cost_totals)
from apps.metering.usage.models import Posting, PostingMeasurement
from apps.metering.usage.tests._helpers import a_posting
from apps.platform.customers.models import Customer
from apps.platform.event_types.models import (
    QuarantinedKey, ValueTypeMismatch, quantity_under)
from apps.platform.event_types.publication import last_published_declaration
from apps.platform.tenants.models import Tenant
from apps.platform.tenants.tests._rails import RailActivated
from apps.platform.work.models import Task
from core.report_windows import ReportWindow
from core.vocabulary import (
    ANALYTICS_MEASURE_CUSTOMER_REVENUE, ANALYTICS_MEASURE_SUPPLIER_COGS)

CHAT = "acme.chat"
CALLS = "calls"


# ---------------------------------------------------------------------------
# 1. No old posting reaches a balance or a report.
# ---------------------------------------------------------------------------

#: The pre-remodel posting fact's money: distinctive, so that any balance or
#: report it reached would carry digits no current posting here produces.
OLD_BILLED = 987_654_321
OLD_COST = 123_456_789

#: The current posting beside it, whose figure every read must answer exactly.
NEW_BILLED = 1_250_000
NEW_COST = 400_000


def plant_an_old_posting(tenant, customer, *, arrived):
    """The posting's OLD table, as the old model kept it, with one row of
    distinctive money for this tenant's customer — raw SQL, because no model
    names that table any more."""
    with connection.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE ubb_usage_event (
                id uuid PRIMARY KEY, tenant_id uuid NOT NULL,
                customer_id uuid NOT NULL, billing_owner_id uuid,
                idempotency_key varchar(255) NOT NULL,
                provider_cost_micros bigint, billed_cost_micros bigint,
                currency varchar(3) NOT NULL, effective_at timestamptz NOT NULL,
                created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL)
        """)
        cursor.execute("""
            INSERT INTO ubb_usage_event VALUES
              (%s, %s, %s, %s, 'pre-remodel', %s, %s, 'usd', %s, %s, %s)
        """, [uuid.uuid4(), tenant.id, customer.id, customer.id, OLD_COST,
              OLD_BILLED, arrived, arrived, arrived])


def old_money_in_the_old_table(tenant):
    with connection.cursor() as cursor:
        cursor.execute("SELECT sum(billed_cost_micros) FROM ubb_usage_event "
                       "WHERE tenant_id = %s", [tenant.id])
        return cursor.fetchone()[0]


class NoOldPostingReachesABalanceOrAReportTest(RailActivated, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.tenant = Tenant.objects.create(
            name="Cutover", products=["metering", "billing"],
            billing_mode="prepaid")
        cls.customer = Customer.objects.create(tenant=cls.tenant,
                                               external_id="c1")

    def setUp(self):
        # Arrived past the repair's grace, so the repair is entitled to it.
        self.arrived = timezone.now() - datetime.timedelta(hours=8)
        self.wallet = Wallet.objects.create(customer=self.customer,
                                            balance_micros=0)
        self.current = a_posting(
            tenant=self.tenant, customer=self.customer, idempotency_key="new",
            provider_cost_micros=NEW_COST, billed_cost_micros=NEW_BILLED,
            billing_owner_id=self.customer.id)
        Posting.objects.filter(id=self.current.id).update(
            created_at=self.arrived, effective_at=self.arrived)
        plant_an_old_posting(self.tenant, self.customer, arrived=self.arrived)

    def test_the_planted_old_posting_is_there_to_be_read(self):
        """What makes the two below evidence: the old fact EXISTS, with its
        money, in the database the balance and the report read from."""
        self.assertEqual(old_money_in_the_old_table(self.tenant), OLD_BILLED)

    def test_it_reaches_no_balance(self):
        reconcile_usage_drawdowns()

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, -NEW_BILLED)
        self.assertEqual(
            list(WalletTransaction.objects.filter(wallet=self.wallet)
                 .values_list("amount_micros", flat=True)), [-NEW_BILLED])

    def test_it_reaches_no_report(self):
        day = self.arrived.date()
        answer = economics(
            self.tenant.id,
            measures=[ANALYTICS_MEASURE_SUPPLIER_COGS,
                      ANALYTICS_MEASURE_CUSTOMER_REVENUE],
            filters=EconomicFilters(window=ReportWindow.between(
                day - datetime.timedelta(days=1), day + datetime.timedelta(days=1))),
            covered_periods=(), contributed_revenue=())

        self.assertEqual(measure_of(answer, ANALYTICS_MEASURE_CUSTOMER_REVENUE)
                         ["amount_micros"], NEW_BILLED)
        self.assertEqual(measure_of(answer, ANALYTICS_MEASURE_SUPPLIER_COGS)
                         ["amount_micros"], NEW_COST)
        self.assertNotIn(str(OLD_BILLED), repr(answer))
        # And the per-customer cost totals report, which the spend pool's
        # period basis stands on too.
        totals = get_customer_cost_totals(
            self.tenant.id, self.customer.id, day - datetime.timedelta(days=1),
            day + datetime.timedelta(days=1))
        self.assertEqual((totals["billed_cost_micros"],
                          totals["provider_cost_micros"], totals["posting_count"]),
                         (NEW_BILLED, NEW_COST, 1))

    def test_the_posting_table_holds_no_column_outside_its_model(self):
        """The other half of reachability: no retired column survives on the
        posting's own table for a raw read to find. The catalogue, not the
        model, is asked — a column the model forgot is exactly what a model
        walk cannot see."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT column_name FROM information_schema.columns "
                           "WHERE table_name = %s", [Posting._meta.db_table])
            on_disk = {row[0] for row in cursor.fetchall()}
        declared = {field.column for field in Posting._meta.concrete_fields}
        self.assertEqual(on_disk, declared)


# ---------------------------------------------------------------------------
# 2. No undeclared measurement survives.
# 4. Every new event validates against its Event Type.
# ---------------------------------------------------------------------------

def names_neither_declared_nor_held(tenant):
    """Every quantity name recorded on an event that names an Event Type which
    is neither declared by its last publication nor held as a quarantined name
    on that event. An event naming no Event Type is outside (#567)."""
    faults = []
    for measured in (PostingMeasurement.objects.filter(posting__tenant=tenant)
                     .select_related("posting")):
        posting = measured.posting
        if not posting.event_type:
            continue
        published = last_published_declaration(tenant=tenant,
                                               key=posting.event_type)
        declared = ({quantity.code for quantity in published.measurements}
                    if published else set())
        held = QuarantinedKey.objects.filter(tenant=tenant, event_id=posting.id)
        held_names = set(held.values_list("measurement_key", flat=True))
        held_whole = published is None and held.exists()
        faults += [(posting.idempotency_key, name)
                   for name in sorted(measured.measurements)
                   if name not in declared and name not in held_names
                   and not held_whole]
    return faults


def quantities_their_publication_refuses(tenant):
    """Every recorded quantity, on an event naming a published Event Type,
    whose value that publication's declared value type refuses."""
    faults = []
    for measured in (PostingMeasurement.objects.filter(posting__tenant=tenant)
                     .select_related("posting")):
        posting = measured.posting
        published = (last_published_declaration(tenant=tenant,
                                                key=posting.event_type)
                     if posting.event_type else None)
        if published is None:
            continue
        value_types = {quantity.code: quantity.value_type
                       for quantity in published.measurements}
        for name, value in sorted(measured.measurements.items()):
            if name not in value_types:
                continue
            try:
                quantity_under(name, value_types[name], value)
            except ValueTypeMismatch:
                faults.append((posting.idempotency_key, name, value))
    return faults


def a_measured_posting_planted_past_the_door(tenant, customer, key, quantities):
    posting = a_posting(tenant=tenant, customer=customer, idempotency_key=key,
                        event_type=CHAT)
    PostingMeasurement.objects.create(posting=posting, measurements=quantities,
                                      recorded_at=posting.effective_at)
    return posting


class _ADeclaringTenantTestCase(OnTheSingleRoute, DeclaringTenantCase):
    """A declaring tenant and the single recording route — named for what it
    is so the gate programme reads every subclass as a collected case."""


class NoUndeclaredMeasurementSurvivesTest(_ADeclaringTenantTestCase):

    def setUp(self):
        super().setUp()
        self.declared(CHAT, quantities=(CALLS,))

    def test_every_recorded_name_is_declared_or_held(self):
        self.send("declared", event_type=CHAT, measurements={CALLS: "3"})
        self.send("undeclared", event_type=CHAT,
                  measurements={CALLS: "1", "ghost": "2"})
        self.send("no-publication", event_type="acme.never_declared",
                  measurements={CALLS: "1"})

        # Non-vacuous: the undeclared names are recorded, and held.
        self.assertTrue(PostingMeasurement.objects.filter(
            posting__tenant=self.tenant, measurements__has_key="ghost").exists())
        self.assertIn("ghost", {row.measurement_key for row in self.held()})
        self.assertEqual(names_neither_declared_nor_held(self.tenant), [])

    def test_planted_an_undeclared_name_nobody_held_is_reported(self):
        a_measured_posting_planted_past_the_door(
            self.tenant, self.customer, "planted",
            {CALLS: "1", "phantom": "5"})
        self.assertEqual(names_neither_declared_nor_held(self.tenant),
                         [("planted", "phantom")])


class EveryNewEventValidatesAgainstItsEventTypeTest(_ADeclaringTenantTestCase):

    def setUp(self):
        super().setUp()
        self.declared(CHAT, quantities=(CALLS,))

    def test_every_event_naming_a_published_event_type_validates(self):
        self.send("whole", event_type=CHAT, measurements={CALLS: "3"})
        # The door refuses a value the publication's type does not admit, and
        # records nothing for it.
        self.refused("fraction", event_type=CHAT, measurements={CALLS: "1.5"})
        self.assertFalse(Posting.objects.filter(idempotency_key="fraction")
                         .exists())
        # An event naming no Event Type stays outside (#567), unvalidated.
        self.send("outside", measurements={CALLS: "1.5"})

        self.assertEqual(PostingMeasurement.objects.filter(
            posting__tenant=self.tenant).count(), 2)
        self.assertEqual(quantities_their_publication_refuses(self.tenant), [])

    def test_planted_an_event_its_publication_refuses_is_reported(self):
        a_measured_posting_planted_past_the_door(
            self.tenant, self.customer, "planted", {CALLS: "2.5"})
        self.assertEqual(quantities_their_publication_refuses(self.tenant),
                         [("planted", CALLS, "2.5")])


# ---------------------------------------------------------------------------
# 3. No legacy pricing provenance is read.
# 5. Every new monetary record uses the new receipt shape.
# ---------------------------------------------------------------------------

def an_older_receipt(version):
    """A receipt in a shape before the current one: version 1 declared, or —
    the pre-version shape — no version at all."""
    receipt = a_receipt_agreeing_with(provider_cost_micros=NEW_COST,
                                      billed_cost_micros=NEW_BILLED)
    if version is None:
        del receipt["receipt_schema_version"]
    else:
        receipt["receipt_schema_version"] = version
    return receipt


#: The planted shapes no reader may read: two older ones, and the empty record
#: the column's default once supplied, which is not a receipt at all.
NOT_A_CURRENT_RECEIPT = {"version 1": an_older_receipt(1),
                         "no version": an_older_receipt(None),
                         "the empty record": {}}

READERS = (uncosted_quantity_keys, recorded_quantities, pricing_method_of,
           pricing_mode_of, subject_type_of)


class NoLegacyPricingProvenanceIsReadTest(_ADeclaringTenantTestCase):

    def test_every_reader_refuses_a_record_not_in_the_one_shape(self):
        current = a_receipt_agreeing_with(provider_cost_micros=NEW_COST,
                                          billed_cost_micros=NEW_BILLED)
        for reader in READERS:
            reader(current)  # the one shape reads
        for label, planted in NOT_A_CURRENT_RECEIPT.items():
            for reader in READERS:
                with self.subTest(shape=label, reader=reader.__name__):
                    with self.assertRaises(ReceiptShapeError):
                        reader(planted)
            with self.subTest(shape=label, reader="completed_receipt"):
                with self.assertRaises(ReceiptShapeError):
                    completed_receipt(planted, sections={})

    def test_a_planted_legacy_receipt_is_refused_by_the_public_read(self):
        """A posting carrying an older receipt is not served as if it were
        current: the event read refuses rather than translating it."""
        self.client.raise_request_exception = False
        for label, planted in NOT_A_CURRENT_RECEIPT.items():
            posting = a_posting(tenant=self.tenant, customer=self.customer,
                                idempotency_key=label, pricing_receipt=planted)
            with self.subTest(shape=label):
                response = self.http.get(
                    f"/api/v1/metering/usage/{posting.id}",
                    HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
                self.assertEqual(response.status_code, 500, response.content)
                self.assertNotIn(b"receipt_schema_version", response.content)


def receipt_owning_models():
    """The records that own a Pricing Receipt: every model declaring the
    receipt column. Derived, not listed (§0.3 point 10): a wallet or invoice
    record is monetary and owns no Pricing Receipt, and none is invented
    for it."""
    return [model for model in apps.get_models()
            if getattr(model, "RECEIPT_COLUMN", None)]


def receipts_not_in_the_one_shape():
    faults = []
    for model in receipt_owning_models():
        for key, receipt in model.objects.values_list(
                "idempotency_key", model.RECEIPT_COLUMN):
            try:
                validate_receipt(receipt)
            except ReceiptShapeError:
                faults.append((model.__name__, key))
    return sorted(faults)


class EveryNewMonetaryRecordUsesTheNewReceiptShapeTest(_ADeclaringTenantTestCase):

    def test_the_covered_records_are_the_postings(self):
        self.assertEqual(receipt_owning_models(), [Posting])

    def test_every_record_written_through_a_door_holds_the_one_shape(self):
        self.declared(CHAT, quantities=(CALLS,))
        self.send("recorded", event_type=CHAT, measurements={CALLS: "2"})
        task = Task.objects.create(tenant=self.tenant, customer=self.customer,
                                   balance_snapshot_micros=0)
        charge = Charge.objects.create(
            tenant=self.tenant, task=task, amount_micros=2_500_000,
            currency="usd", agreed_price_line_id=uuid.uuid4(), book_version=1,
            resolved_at=timezone.now(), charged_at=timezone.now(),
            idempotency_key="charged")
        project_the_charge(charge)

        written = list(Posting.objects.filter(tenant=self.tenant)
                       .values_list("pricing_receipt", flat=True))
        self.assertEqual(len(written), 2)
        self.assertEqual({receipt["receipt_schema_version"]
                          for receipt in written}, {RECEIPT_SCHEMA_VERSION})
        self.assertEqual(receipts_not_in_the_one_shape(), [])

    def test_planted_records_in_another_shape_are_reported(self):
        for label, planted in NOT_A_CURRENT_RECEIPT.items():
            a_posting(tenant=self.tenant, customer=self.customer,
                      idempotency_key=label, pricing_receipt=planted)
        self.assertEqual(receipts_not_in_the_one_shape(), sorted(
            ("Posting", label) for label in NOT_A_CURRENT_RECEIPT))

    def test_an_omitted_receipt_fails_at_its_insert(self):
        """`{}` is no longer the column's default (§0.3 point 8): a creator
        that forgets the receipt is refused at its insert instead of
        persisting a record that explains nothing."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            Posting.objects.create(tenant=self.tenant, customer=self.customer,
                                   idempotency_key="forgot")
