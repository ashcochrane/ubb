"""A tenant that bills its customers somewhere other than UBB may state what
it earned, and every surface showing the number can say where it came from
(#495, slice 7 §9; Testing Decisions claims 9, 10 and 11).

The half a tenant actually touches. What each class holds:

* *The floors are the module's own* — the write at `ADMIN`, the read at `READ`,
  and a read-scoped credential refused the write **through the route**.
* *The record carries its own period* — with an end, without one, and starting
  mid-period, which is the affordance the recurring profile absorbed
  automatically and per-period rows can only express if a tenant can enter a
  partial period.
* *Both views are offered and both are labelled* — recorded and recognised
  differ exactly as the method says, every response names the basis it served,
  and the default is the view that distributes nothing.
* *Both postures survive* — a tenant that supplies nothing reads `unknown` with
  no total at all, never a zero; one that supplies a figure reads `known`.
* *It is not a Charge, in both directions* — recording one writes no charge,
  and a charge writes no supplied record.

**THE POSTURE THIS MODULE IS NOT PRIMARILY BUILT FOR IS THE ONE IT OWES A TEST
FOR**, and the ticket says so: building the supplied-revenue path only for
tenants UBB invoices is the one failure no gate in this repository can catch.
So the fixture tenant is the one whose customers UBB never bills — the platform
default — and the tenant UBB does bill appears beside it to prove the surface
does not narrow to either.
"""
import json
import uuid
from datetime import date, timedelta

from django.test import Client, TestCase
from django.utils import timezone

from apps.metering.pricing.models import Charge
from apps.platform.work.models import Task
from apps.platform.audit.actions import is_registered_action
from apps.platform.audit.models import AuditRecord
from apps.platform.membership.roles import ADMIN, READ, WRITE
from apps.platform.tenants.models import TenantApiKey
from apps.subscriptions.economics.models import TenantSuppliedRevenue
from apps.subscriptions.tests._helpers import (
    ITS_OWN_INVOICE, MONTH_CLOSES, MONTH_OPENS, SUPPLIED, a_supplied_figure,
    a_tenant_billing_its_customers_elsewhere)
from core.vocabulary import (
    AUDIT_ACTION_TENANT_SUPPLIED_REVENUE_RECORDED,
    CUSTOMER_BILLING_MODE_PREPAID, PRICING_STATUS_KNOWN, PRICING_STATUS_UNKNOWN,
    RECOGNITION_METHOD_ON_RECEIPT, RECOGNITION_METHOD_STRAIGHT_LINE,
    REVENUE_BASIS_RECOGNISED, REVENUE_BASIS_RECORDED)


class _ATenantBillingItsCustomersElsewhereMixin:
    """The platform default: UBB meters and the tenant bills somewhere UBB
    cannot see. The tenant, its customer and the period they describe come
    from `apps/subscriptions/tests/_helpers.py`, which the database half of
    this record's proof reads too — so the two halves cannot come to describe
    different records. What is this module's own is everything below: the
    credential at a role, and the two routes."""

    def setUp(self):
        self.http = Client()
        self.tenant, self.customer = a_tenant_billing_its_customers_elsewhere()
        self.key, self.raw_key = TenantApiKey.create_key(self.tenant, label="k")

    def _as(self, role):
        """The same key, at a role. The floor reads the principal's own role,
        so this is the whole of what a lower principal is."""
        TenantApiKey.objects.filter(pk=self.key.pk).update(role=role)
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def path(self, customer=None):
        target = customer or self.customer
        return f"/api/v1/margin/customers/{target.id}/supplied-revenue"

    def supply(self, role=ADMIN, customer=None, **body):
        """A write body, from the one set of defaults the database half of
        this record's proof reads too — with the two dates rendered as the
        text a request carries, which is all this seam changes."""
        stated = a_supplied_figure(**body)
        for when in ("period_start", "period_end"):
            if stated[when] is not None and not isinstance(stated[when], str):
                stated[when] = stated[when].isoformat()
        return self.http.post(self.path(customer), data=json.dumps(stated),
                              content_type="application/json", **self._as(role))

    def read(self, role=READ, customer=None, **params):
        query = "&".join(f"{name}={value}" for name, value in params.items())
        return self.http.get(f"{self.path(customer)}?{query}", **self._as(role))


class TheFloorsAreTheMarginModulesOwnTest(
        _ATenantBillingItsCustomersElsewhereMixin, TestCase):
    """Slice 7 §9's authorization ruling, argued from this module's precedent:
    every mutating operation on it is already `ADMIN` and every read `READ`."""

    def test_a_read_scoped_credential_is_refused_the_write(self):
        for role in (READ, WRITE):
            with self.subTest(role=role):
                answered = self.supply(role=role)

                self.assertEqual(answered.status_code, 403, answered.content)
                self.assertFalse(TenantSuppliedRevenue.objects.exists())

    def test_an_admin_may_write_one(self):
        answered = self.supply()

        self.assertEqual(answered.status_code, 200, answered.content)
        self.assertEqual(TenantSuppliedRevenue.objects.count(), 1)

    def test_a_read_scoped_credential_may_read(self):
        self.supply()

        # The window is stated, because an unstated one is month-to-date of
        # the month the test runs in and the figure above is April's.
        answered = self.read(role=READ, start_date=MONTH_OPENS.isoformat(),
                             end_date=MONTH_CLOSES.isoformat())

        self.assertEqual(answered.status_code, 200, answered.content)
        self.assertEqual(answered.json()["pricing_status"], PRICING_STATUS_KNOWN)


class TheRecordCarriesItsOwnPeriodTest(
        _ATenantBillingItsCustomersElsewhereMixin, TestCase):
    """#153 §19(f): retiring the recurring profile loses the *began on the
    fourteenth* semantics unless a tenant can enter the part of the period the
    figure actually covers. This is that affordance, at the write surface."""

    def test_a_partial_period_is_expressible(self):
        began = date(2026, 4, 14)

        answered = self.supply(period_start=began.isoformat(),
                               period_end=MONTH_CLOSES.isoformat(),
                               amount_micros=1_700_000)

        self.assertEqual(answered.status_code, 200, answered.content)
        body = answered.json()
        self.assertEqual(body["period_start"], began.isoformat())
        self.assertEqual(body["period_end"], MONTH_CLOSES.isoformat())
        # Seventeen days, which is the part of April a customer who began on
        # the fourteenth was billed for — stated by the tenant rather than
        # inferred by UBB from a recurring amount.
        self.assertEqual(body["amount_micros"], 1_700_000)

    def test_revenue_that_is_an_instant_carries_no_end(self):
        answered = self.supply(period_end=None,
                               recognition_method=RECOGNITION_METHOD_ON_RECEIPT)

        self.assertEqual(answered.status_code, 200, answered.content)
        self.assertIsNone(answered.json()["period_end"])

    def test_a_method_that_spreads_is_refused_without_a_span(self):
        answered = self.supply(period_end=None,
                               recognition_method=RECOGNITION_METHOD_STRAIGHT_LINE)

        self.assertEqual(answered.status_code, 422, answered.content)
        self.assertIn("period_end", answered.json()["detail"])
        self.assertFalse(TenantSuppliedRevenue.objects.exists())

    def test_a_span_that_closes_before_it_opens_is_refused(self):
        answered = self.supply(period_start=MONTH_CLOSES.isoformat(),
                               period_end=MONTH_OPENS.isoformat())

        self.assertEqual(answered.status_code, 422, answered.content)
        self.assertFalse(TenantSuppliedRevenue.objects.exists())


class TheSourceReachesEverySurfaceTest(
        _ATenantBillingItsCustomersElsewhereMixin, TestCase):
    """What the recurring profile destroyed: a revenue number nobody could
    trace. The source reference is required, and it travels."""

    def test_it_is_refused_blank(self):
        for blank in ("", "   "):
            with self.subTest(source_reference=blank):
                answered = self.supply(source_reference=blank)

                self.assertEqual(answered.status_code, 422, answered.content)
                self.assertFalse(TenantSuppliedRevenue.objects.exists())

    def test_it_comes_back_from_the_write_and_from_the_read(self):
        written = self.supply().json()

        read = self.read(start_date=MONTH_OPENS.isoformat(),
                         end_date=MONTH_CLOSES.isoformat()).json()

        self.assertEqual(written["source_reference"], ITS_OWN_INVOICE)
        self.assertEqual([row["source_reference"] for row in read["records"]],
                         [ITS_OWN_INVOICE])

    def test_the_ledger_records_one_registered_act_naming_the_source(self):
        self.supply()

        entries = AuditRecord.objects.filter(tenant_id=self.tenant.id)
        self.assertEqual([entry.action for entry in entries],
                         [AUDIT_ACTION_TENANT_SUPPLIED_REVENUE_RECORDED])
        self.assertTrue(is_registered_action(
            AUDIT_ACTION_TENANT_SUPPLIED_REVENUE_RECORDED))
        self.assertEqual(entries[0].metadata["source_reference"], ITS_OWN_INVOICE)

    def test_two_sources_covering_one_period_are_two_facts(self):
        self.supply()
        self.supply(source_reference="INV-2026-04-0118", amount_micros=500_000)

        read = self.read(start_date=MONTH_OPENS.isoformat(),
                         end_date=MONTH_CLOSES.isoformat()).json()

        self.assertEqual(len(read["records"]), 2)
        self.assertEqual(read["totals"],
                         [{"currency": "usd", "amount_micros": 3_500_000}])

    def test_restating_one_source_replaces_its_figure(self):
        self.supply()
        self.supply(amount_micros=4_000_000)

        read = self.read(start_date=MONTH_OPENS.isoformat(),
                         end_date=MONTH_CLOSES.isoformat()).json()

        self.assertEqual(len(read["records"]), 1)
        self.assertEqual(read["records"][0]["amount_micros"], 4_000_000)
        # The same act performed twice, and the ledger holds both statements.
        self.assertEqual(AuditRecord.objects.filter(tenant_id=self.tenant.id).count(), 2)


class BothViewsAreOfferedAndBothAreLabelledTest(
        _ATenantBillingItsCustomersElsewhereMixin, TestCase):
    """Slice 7 §5. Recognised is the only behaviour UBB had and it was
    unlabelled and unconditional; recorded is the view that was missing."""

    def setUp(self):
        super().setUp()
        self.supply()
        self.first_week = {"start_date": MONTH_OPENS.isoformat(),
                           "end_date": (MONTH_OPENS + timedelta(days=7)).isoformat()}

    def test_every_response_names_the_basis_it_served(self):
        for basis in (REVENUE_BASIS_RECORDED, REVENUE_BASIS_RECOGNISED):
            with self.subTest(basis=basis):
                answered = self.read(basis=basis, **self.first_week)

                self.assertEqual(answered.json()["basis"], basis)

    def test_the_default_is_the_view_that_distributes_nothing(self):
        answered = self.read(**self.first_week)

        body = answered.json()
        self.assertEqual(body["basis"], REVENUE_BASIS_RECORDED)
        self.assertEqual(body["records"][0]["attributed_amount_micros"], SUPPLIED)

    def test_the_two_views_differ_exactly_as_the_method_says(self):
        recorded = self.read(basis=REVENUE_BASIS_RECORDED, **self.first_week).json()
        recognised = self.read(basis=REVENUE_BASIS_RECOGNISED, **self.first_week).json()

        # Recorded places the whole figure on the day the period opens.
        self.assertEqual(recorded["totals"],
                         [{"currency": "usd", "amount_micros": SUPPLIED}])
        # Recognised divides it by day across the thirty days the record
        # itself declares: seven of them, at 100,000 micros each.
        self.assertEqual(recognised["totals"],
                         [{"currency": "usd", "amount_micros": 700_000}])

    def test_a_method_that_never_distributes_reads_the_same_both_ways(self):
        TenantSuppliedRevenue.objects.all().delete()
        self.supply(recognition_method=RECOGNITION_METHOD_ON_RECEIPT)

        recorded = self.read(basis=REVENUE_BASIS_RECORDED, **self.first_week).json()
        recognised = self.read(basis=REVENUE_BASIS_RECOGNISED, **self.first_week).json()

        self.assertEqual(recorded["totals"], recognised["totals"])
        self.assertEqual(recognised["totals"],
                         [{"currency": "usd", "amount_micros": SUPPLIED}])

    def test_a_basis_nobody_declared_is_refused_rather_than_guessed(self):
        answered = self.read(basis="accrual", **self.first_week)

        self.assertEqual(answered.status_code, 422, answered.content)

    def test_a_window_after_the_period_opens_sees_nothing_recorded(self):
        later = {"start_date": (MONTH_OPENS + timedelta(days=7)).isoformat(),
                 "end_date": MONTH_CLOSES.isoformat()}

        recorded = self.read(basis=REVENUE_BASIS_RECORDED, **later).json()
        recognised = self.read(basis=REVENUE_BASIS_RECOGNISED, **later).json()

        # The figure was stated against the first of the month, so a window
        # opening later gets none of it recorded — and is told so as `unknown`
        # rather than as nil.
        self.assertEqual(recorded["pricing_status"], PRICING_STATUS_UNKNOWN)
        self.assertEqual(recorded["totals"], [])
        # Recognised still sees the twenty-three days of the span it overlaps.
        self.assertEqual(recognised["totals"],
                         [{"currency": "usd", "amount_micros": 2_300_000}])


class BothPosturesSurviveTest(
        _ATenantBillingItsCustomersElsewhereMixin, TestCase):
    """#153 §3.2: cost-tracking alone and cost tracking plus a supplied figure
    are both legitimate, and this slice must not build only the second.

    ⚠ **ONE HALF OF THE CRITERION IS ASSERTED HERE AND THE OTHER IS NOT THIS
    SURFACE'S, so this says which.** The criterion is *"revenue `unknown` and
    margin unavailable — never zero"*. The revenue half is this surface's and
    is proved below: `unknown`, an empty totals list, and no scalar amount in
    the answer at all. **The margin half had no surface to be asserted against
    when #495 wrote this** — margin was then
    `CustomerEconomics.gross_margin_micros`, which defaulted to zero and was
    computed from the recurring profile #496 deleted, and the scope rule that
    makes a margin *unavailable* rather than nil is slice 7 §5's, built by the
    tickets that collapsed the nine routes into the one query. It has one now:
    the one economic query derives a margin at read time from both of its
    inputs, and over usage nobody priced it publishes a FLOOR labelled
    `incomplete` beside the count that says how far short it falls — never
    `known`, the one state under which a reader could take a zero for a figure.
    That is claim 9 in the query's own states rather than in its words, which
    say *unavailable*. The flip (#512) found that half unasserted and asserted
    it through the route, in
    `test_the_one_economic_query.py::TestUsageNobodyPricedIsNeverAKnownFigure`.

    What this record guarantees is the input side: **nothing downstream can
    read a zero off it**, because its surface publishes no amount to read when
    there is nothing supplied."""

    def test_with_nothing_supplied_revenue_is_unknown_and_never_zero(self):
        body = self.read(start_date=MONTH_OPENS.isoformat(),
                         end_date=MONTH_CLOSES.isoformat()).json()

        self.assertEqual(body["pricing_status"], PRICING_STATUS_UNKNOWN)
        self.assertEqual(body["totals"], [])
        self.assertEqual(body["records"], [])
        # THE ONE ASSERTION THIS CLASS EXISTS FOR, and it is about the SHAPE
        # rather than about a value: the answer carries no scalar amount at
        # all, so there is nothing that could be serving a zero in place of a
        # number UBB does not have. A response that grew one would fail here
        # before anybody had to notice what it contained.
        self.assertFalse([key for key in body if key.endswith("_micros")],
                         sorted(body))

    def test_a_deliberate_zero_is_a_known_figure_and_not_an_absent_one(self):
        self.supply(amount_micros=0)

        body = self.read(start_date=MONTH_OPENS.isoformat(),
                         end_date=MONTH_CLOSES.isoformat()).json()

        self.assertEqual(body["pricing_status"], PRICING_STATUS_KNOWN)
        self.assertEqual(body["totals"],
                         [{"currency": "usd", "amount_micros": 0}])

    def test_the_tenant_ubb_does_bill_gets_the_same_surface(self):
        # The other posture, built here rather than by the shared helper
        # because the helper's whole subject is the tenant UBB never bills.
        # Everything after the fixture is this class's ordinary path — the
        # point being that the surface does not narrow to either posture.
        self.tenant.billing_mode = CUSTOMER_BILLING_MODE_PREPAID
        self.tenant.products = ["metering", "billing"]
        self.tenant.save(update_fields=["billing_mode", "products",
                                        "updated_at"])

        written = self.supply(recognition_method=RECOGNITION_METHOD_ON_RECEIPT)

        self.assertEqual(written.status_code, 200, written.content)
        read = self.read(start_date=MONTH_OPENS.isoformat(),
                         end_date=MONTH_CLOSES.isoformat())
        self.assertEqual(read.json()["pricing_status"], PRICING_STATUS_KNOWN)

    def test_a_figure_covering_part_of_the_window_reads_known_not_settled(self):
        """`known` says a supplied figure is attributable here — it does NOT
        say the window is covered, and it cannot: UBB has no way to tell a
        period nobody has supplied yet from one that earned nothing. The
        coverage a caller actually needs is in the rows, so this pins both
        halves of that at once."""
        self.supply()

        body = self.read(start_date=date(2026, 1, 1).isoformat(),
                         end_date=date(2027, 1, 1).isoformat()).json()

        self.assertEqual(body["pricing_status"], PRICING_STATUS_KNOWN)
        # One April in a whole year, and the row says which April.
        self.assertEqual([(row["period_start"], row["period_end"])
                          for row in body["records"]],
                         [(MONTH_OPENS.isoformat(), MONTH_CLOSES.isoformat())])


class ASuppliedFigureIsNotAChargeTest(
        _ATenantBillingItsCustomersElsewhereMixin, TestCase):
    """The distinction in both directions. UBB neither created nor invoiced
    this money, so recording it must raise nothing UBB charged — and what UBB
    charges must never appear as a figure the tenant supplied."""

    def a_charge_ubb_raised(self):
        """What UBB charged this customer for one delivered piece of work.

        Built at the two tables rather than driven through the pricing path:
        this class is about whether the two RECORDS can be mistaken for one
        another, and a charge that exists is the whole of what the second
        direction needs. Its price line and book version are arbitrary — both
        are plain columns on the charge — because nothing here reads them.
        """
        work = Task.objects.create(tenant=self.tenant, customer=self.customer,
                                   balance_snapshot_micros=0)
        return Charge.objects.create(
            tenant=self.tenant, task=work, amount_micros=SUPPLIED,
            currency="usd", agreed_price_line_id=uuid.uuid4(), book_version=1,
            resolved_at=timezone.now(), charged_at=timezone.now(),
            idempotency_key=f"charge-{uuid.uuid4()}")

    def test_recording_a_supplied_figure_charges_nobody(self):
        self.supply()

        self.assertEqual(TenantSuppliedRevenue.objects.count(), 1)
        self.assertFalse(Charge.objects.filter(tenant=self.tenant).exists())

    def test_what_ubb_charged_produces_no_supplied_record(self):
        """The other direction, and it needs a charge to actually exist.

        A commit that made the pricing path write a supplied record — the
        obvious way for UBB's own revenue to start impersonating a tenant's —
        would leave a row here and a `known` on the read below.
        """
        charged = self.a_charge_ubb_raised()

        self.assertEqual(Charge.objects.filter(tenant=self.tenant).count(), 1)
        self.assertFalse(TenantSuppliedRevenue.objects.exists())
        # And the supplied-revenue surface does not see it: a window covering
        # the instant UBB charged still reads `unknown`, because the tenant has
        # supplied nothing.
        today = charged.charged_at.date()
        body = self.read(start_date=today.isoformat(),
                         end_date=(today + timedelta(days=1)).isoformat()).json()
        self.assertEqual(body["pricing_status"], PRICING_STATUS_UNKNOWN)
        self.assertEqual(body["records"], [])

    def test_the_read_publishes_no_charge_vocabulary(self):
        self.supply()
        self.a_charge_ubb_raised()

        body = self.read(start_date=MONTH_OPENS.isoformat(),
                         end_date=MONTH_CLOSES.isoformat()).json()

        # Every key of every row, at both levels of the answer. A surface that
        # started calling this a charge would fail here before a reader ever
        # met the word — and the charge above exists while it runs, so the
        # answer is being kept clean of a record that is really there.
        keys = set(body) | {key for row in body["records"] for key in row}
        self.assertFalse({key for key in keys if "charge" in key}, sorted(keys))
        self.assertEqual([row["source_reference"] for row in body["records"]],
                         [ITS_OWN_INVOICE])


class WhatTheWriteRefusesTest(
        _ATenantBillingItsCustomersElsewhereMixin, TestCase):
    """The friendly door in front of the record's own check constraints: a
    caller is told which field to change rather than meeting an integrity
    error that names a constraint."""

    def test_a_method_nobody_declared_is_refused(self):
        answered = self.supply(recognition_method="accrual")

        self.assertEqual(answered.status_code, 422, answered.content)
        self.assertIn("recognition_method", answered.json()["detail"])

    def test_a_currency_ubb_cannot_settle_is_refused(self):
        answered = self.supply(currency="xyz")

        self.assertEqual(answered.status_code, 422, answered.content)
        self.assertEqual(answered.json()["code"], "unsupported_currency")

    def test_an_amount_that_is_not_whole_minor_currency_is_refused(self):
        answered = self.supply(amount_micros=1_000_001)

        self.assertEqual(answered.status_code, 422, answered.content)
        self.assertFalse(TenantSuppliedRevenue.objects.exists())

    def test_another_tenants_customer_is_not_found(self):
        _, theirs = a_tenant_billing_its_customers_elsewhere(
            name="Someone else")

        answered = self.supply(customer=theirs)

        self.assertEqual(answered.status_code, 404, answered.content)
