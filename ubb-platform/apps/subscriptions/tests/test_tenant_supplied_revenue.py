"""The supplied revenue record's own rule, at the database (#495).

`TenantSuppliedRevenue.transition_classes` declares `RECORD_RULE` throughout —
not a fifth class, but the absence of a per-column one said out loud — and
`docs/conventions/django-patterns.md` is explicit about what that costs: a
`RECORD_RULE` record sits outside G19's statement, so **nothing walks it and
its rule owes its own tests.** This module is those tests.

**The rule, as the model states it:** one row per customer per period-open per
source reference. Stating the same period from the same source again re-states
the figure; a different source adds a figure beside it. And four checks stand
behind the figure itself — the method is one the registry declares, a span that
closes opens first, a method that spreads has a span to spread across, and a
supplied figure says where it came from.

**Every refusal is driven through both write doors**, `save()` and
`QuerySet.update()`, and through raw SQL where the constraint can be reached
that way — because ADR-0007 §2's whole point is that a model-level guard is not
enforcement, and the route's friendly refusals in
`api/v1/tests/test_a_tenant_may_supply_the_revenue_ubb_cannot_see.py` are a
door rather than the line. An admitted write sits beside each refusal, so a
constraint that refused everything would fail here rather than read as strict.
"""
import uuid
from datetime import date

from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from apps.subscriptions.economics.models import TenantSuppliedRevenue
from apps.subscriptions.tests._helpers import (
    ITS_OWN_INVOICE, MONTH_CLOSES, MONTH_OPENS, SUPPLIED, a_supplied_figure,
    a_tenant_billing_its_customers_elsewhere)
from core.transitions import DATABASE_DEFENDED, RECORD_RULE
from core.vocabulary import (
    RECOGNITION_METHOD_ON_RECEIPT, RECOGNITION_METHOD_STRAIGHT_LINE)


class _ASuppliedFigureMixin:

    def setUp(self):
        self.tenant, self.customer = a_tenant_billing_its_customers_elsewhere()

    def a_figure(self, **stated):
        return TenantSuppliedRevenue.objects.create(
            tenant=self.tenant, customer=self.customer,
            **a_supplied_figure(**stated))

    def insert_through_raw_sql(self, **stated):
        """The third door: no model, no `choices=`, no `full_clean()`."""
        fields = a_supplied_figure(**stated)
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO ubb_tenant_supplied_revenue "
                "(id, created_at, updated_at, tenant_id, customer_id, "
                " amount_micros, currency, period_start, period_end, "
                " recognition_method, source_reference) "
                "VALUES (%s, NOW(), NOW(), %s, %s, %s, %s, %s, %s, %s, %s)",
                [uuid.uuid4(), self.tenant.id, self.customer.id,
                 fields["amount_micros"], fields["currency"],
                 fields["period_start"], fields["period_end"],
                 fields["recognition_method"], fields["source_reference"]])


class TheRecordsRuleIsOneFigurePerSourcePerPeriodTest(
        _ASuppliedFigureMixin, TestCase):
    """The uniqueness key IS the record's rule, so it is the one thing this
    declaration's `RECORD_RULE` points at."""

    def test_a_second_figure_from_the_same_source_for_the_same_period_is_refused(self):
        self.a_figure()

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.a_figure(amount_micros=1)

    def test_it_holds_through_raw_sql_too(self):
        self.a_figure()

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.insert_through_raw_sql(amount_micros=1)

    def test_a_different_source_covering_the_same_period_is_admitted(self):
        self.a_figure()

        self.a_figure(source_reference="INV-2026-04-0118", amount_micros=500_000)

        self.assertEqual(TenantSuppliedRevenue.objects.count(), 2)

    def test_the_same_source_covering_a_different_period_is_admitted(self):
        self.a_figure()

        self.a_figure(period_start=MONTH_CLOSES,
                      period_end=date(2026, 6, 1))

        self.assertEqual(TenantSuppliedRevenue.objects.count(), 2)

    def test_another_tenants_identical_figure_is_admitted(self):
        self.a_figure()
        elsewhere, theirs = a_tenant_billing_its_customers_elsewhere(
            name="Someone else")

        TenantSuppliedRevenue.objects.create(
            tenant=elsewhere, customer=theirs, amount_micros=SUPPLIED,
            currency="usd", period_start=MONTH_OPENS, period_end=MONTH_CLOSES,
            recognition_method=RECOGNITION_METHOD_STRAIGHT_LINE,
            source_reference=ITS_OWN_INVOICE)

        self.assertEqual(TenantSuppliedRevenue.objects.count(), 2)


class TheFourChecksEachRefuseSomethingDifferentTest(
        _ASuppliedFigureMixin, TestCase):
    """Each one named, each driven through the doors a model-level guard does
    not cover, and each with the write it admits beside it."""

    def test_a_method_the_registry_does_not_declare_is_refused(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.a_figure(recognition_method="accrual")

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.insert_through_raw_sql(recognition_method="accrual")

        # And an update is a door of its own: `choices=` never sees one.
        admitted = self.a_figure()
        with self.assertRaises(IntegrityError), transaction.atomic():
            TenantSuppliedRevenue.objects.filter(pk=admitted.pk).update(
                recognition_method="accrual")

    def test_a_span_that_closes_before_it_opens_is_refused(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.a_figure(period_start=MONTH_CLOSES, period_end=MONTH_OPENS)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.a_figure(period_start=MONTH_OPENS, period_end=MONTH_OPENS)

        admitted = self.a_figure()
        with self.assertRaises(IntegrityError), transaction.atomic():
            TenantSuppliedRevenue.objects.filter(pk=admitted.pk).update(
                period_end=MONTH_OPENS)

    def test_a_method_that_spreads_is_refused_without_a_span(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.a_figure(recognition_method=RECOGNITION_METHOD_STRAIGHT_LINE,
                          period_end=None)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.insert_through_raw_sql(
                recognition_method=RECOGNITION_METHOD_STRAIGHT_LINE,
                period_end=None)

        # The method that spreads nothing needs no span, and is admitted
        # without one — which is what makes the check a rule about the pair
        # rather than a requirement on the column.
        self.a_figure(recognition_method=RECOGNITION_METHOD_ON_RECEIPT,
                      period_end=None)

        self.assertEqual(TenantSuppliedRevenue.objects.count(), 1)

    def test_a_figure_that_does_not_say_where_it_came_from_is_refused(self):
        """⚠ **THREE SPACES ARE AS SILENT AS AN EMPTY STRING**, and the check
        refuses both. `<> ''` would admit the first, and the route's `strip()`
        is a door rather than the line — which is exactly the shape ADR-0007 §2
        exists to refuse, so it is driven here through the two doors the route
        is not on."""
        for says_nothing in ("", "   ", "\t\n"):
            with self.subTest(source_reference=repr(says_nothing)):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.a_figure(source_reference=says_nothing)

                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.insert_through_raw_sql(source_reference=says_nothing)

        admitted = self.a_figure()
        with self.assertRaises(IntegrityError), transaction.atomic():
            TenantSuppliedRevenue.objects.filter(pk=admitted.pk).update(
                source_reference="   ")


class TheDeclarationSaysWhatItMeansTest(_ASuppliedFigureMixin, TestCase):
    """ADR-0007 §2 asks every column *what is allowed to happen to this?* and
    this record answers with its rule rather than with a class. Asserted so
    that a later commit moving a column into a defended class has to move this
    too — at which point G19 starts walking it and a trigger becomes owed."""

    def test_every_column_declares_the_records_own_rule(self):
        declared = TenantSuppliedRevenue.transition_classes

        self.assertEqual(set(declared.values()), {RECORD_RULE})
        self.assertFalse(set(declared.values()) & DATABASE_DEFENDED)

    def test_it_declares_every_column_the_table_has(self):
        columns = {field.name for field in TenantSuppliedRevenue._meta.fields}

        self.assertEqual(set(TenantSuppliedRevenue.transition_classes), columns)
