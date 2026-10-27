"""UBB v1 is US dollars only, and the database holds it (ADR-0023, #555).

The doors refuse another currency through `core.currency_policy.admit_currency`
— the route tests prove that, each at its own route. This module is the half a
door cannot be: every currency column UBB's economics admit carries a `CHECK`
holding it to `usd`, and every write that goes round the doors meets it.

Three claims, one class each:

1. **Every currency column is accounted for.** It carries the policy's `CHECK`,
   or its model declares it a column that records what an external integration
   SENT (`SOURCE_CURRENCY_COLUMNS`), which the `CHECK` must spare so #564's
   quarantine can keep a foreign code truthfully. Nothing else: a new currency
   column that does neither goes red here, which is what retires the old
   `UNOWNED_CURRENCY_COLUMNS` inventory — the debt it recorded is paid, and a new
   one cannot open silently.
2. **The database refuses another currency through every door** — a new row
   through `objects.create()` and through raw SQL, and an existing row through
   `QuerySet.update()` and raw SQL — and each refusal names the `CHECK` it
   belongs to, never "something refused this" (several rules share these
   tables). The stored row is read back unchanged each time: every one of these
   columns defaults to `usd`, so a test that only watched for an error could be
   passed by a write that never happened.
3. **A tenant's own `save()` refuses by the domain rule**, so the admin form and
   a seed meet a named validation error rather than a database exception.
"""

import uuid
from datetime import date

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, models, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase
from django.utils import timezone

from apps.billing.invoicing.models import CustomerUsageInvoice
from apps.billing.wallets.models import CreditGrant, Wallet
from apps.metering.pricing.models import Charge, CostBook, Rate
from apps.metering.pricing.services.charge_service import derived_key
from apps.metering.pricing.tests._helpers import (
    a_price_for_whole_work,
    cost_book,
    rate_in_default_book,
)
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.event_types.models import ReportedCostMapping
from apps.platform.event_types.tests._helpers import declares_a_caller_supplied_cost
from apps.platform.tenants.models import Tenant
from apps.platform.work.models import Task
from apps.subscriptions.economics.models import TenantSuppliedRevenue
from core.currency_policy import ECONOMIC_CURRENCY, SOURCE_CURRENCY_COLUMNS
from core.vocabulary import (
    PRICING_MODE_FIXED,
    RECOGNITION_METHOD_ON_RECEIPT,
    TASK_STATUS_COMPLETED,
)

#: A currency UBB can REPRESENT (`core.money` knows its minor unit) and does not
#: ADMIT, so every refusal below is the policy's and never "an unknown code".
FOREIGN = "eur"

#: Every currency column in the tree, and what holds it. A literal, so a column
#: that arrives or leaves is read by a person: the walk below derives the same
#: map from the models and the two must agree.
HELD_BY = {
    ("ubb_tenant", "default_currency"): "ck_tenant_default_currency_usd",
    ("ubb_wallet", "currency"): "ck_wallet_currency_usd",
    ("ubb_credit_grant", "currency"): "ck_credit_grant_currency_usd",
    ("ubb_rate", "currency"): "ck_rate_currency_usd",
    ("ubb_charge", "currency"): "ck_charge_currency_usd",
    ("ubb_cost_book", "currency"): "ck_cost_book_currency_usd",
    ("ubb_posting", "currency"): "ck_posting_currency_usd",
    ("ubb_reported_cost_mapping", "currency"): "ck_reported_cost_currency_usd",
    ("ubb_tenant_supplied_revenue", "currency"): "ck_supplied_revenue_currency_usd",
    ("ubb_customer_usage_invoice", "currency"): "ck_usage_invoice_currency_usd",
}

#: The columns that record what Stripe SENT (#564), spared the `CHECK`.
SOURCE_FACTS = {
    ("ubb_stripe_subscription", "currency"),
    ("ubb_subscription_invoice", "currency"),
}


def _currency_columns():
    """``{(table, column): model}`` for every currency column the models declare."""
    found = {}
    for model in apps.get_models():
        if model._meta.abstract or model._meta.proxy or not model._meta.managed:
            continue
        for field in model._meta.concrete_fields:
            if (isinstance(field, models.CharField)
                    and (field.name == "currency" or field.name.endswith("_currency"))):
                found[(model._meta.db_table, field.column)] = model
    return found


def _checks_on(table, column):
    """``{name: definition}`` for every CHECK the catalogue holds over a column."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT c.conname, pg_get_constraintdef(c.oid)
            FROM pg_constraint c
            JOIN pg_attribute a
              ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
            WHERE c.contype = 'c' AND c.conrelid = %s::regclass
              AND a.attname = %s
        """, [table, column])
        return dict(cursor.fetchall())


class EveryCurrencyColumnIsAccountedForTest(TestCase):
    """Claim 1."""

    def test_the_models_declare_exactly_the_columns_this_module_names(self):
        """The vacuity guard: the walk finds every column the literal names and
        nothing beside them."""
        self.assertEqual(set(_currency_columns()), set(HELD_BY) | SOURCE_FACTS)

    def test_every_economic_column_carries_the_policys_check(self):
        for (table, column), name in HELD_BY.items():
            with self.subTest(table=table):
                checks = _checks_on(table, column)
                self.assertIn(name, checks)
                self.assertIn(f"'{ECONOMIC_CURRENCY}'", checks[name])

    def test_the_source_facts_are_declared_on_their_models_and_spared(self):
        """Declared where the column lives, so the next reader of the model
        sees why no CHECK holds it — and the catalogue agrees that none does.
        A CHECK there would refuse the evidence #564's quarantine keeps."""
        columns = _currency_columns()
        for table, column in sorted(SOURCE_FACTS):
            with self.subTest(table=table):
                model = columns[(table, column)]
                self.assertIn(column, getattr(model, SOURCE_CURRENCY_COLUMNS))
                self.assertEqual(_checks_on(table, column), {})

    def test_no_economic_model_declares_a_source_fact(self):
        """The declaration is the CHECK's only exemption, so it is held to the
        two models whose column Stripe writes."""
        columns = _currency_columns()
        for (table, column) in HELD_BY:
            with self.subTest(table=table):
                self.assertNotIn(column, getattr(
                    columns[(table, column)], SOURCE_CURRENCY_COLUMNS, ()))


class _Rows:
    """One saved USD row per economic column, built the way a route builds it."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Dollars", products=["metering"])
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")

    def _a_customer(self):
        return Customer.objects.create(tenant=self.tenant,
                                       external_id=f"c-{uuid.uuid4()}")

    def _wallet(self):
        return Wallet.objects.create(customer=self._a_customer())

    def _credit_grant(self):
        return CreditGrant.objects.create(
            tenant=self.tenant, wallet=self._wallet(), kind="paid",
            granted_micros=1_000_000, remaining_micros=1_000_000)

    def _rate(self):
        return rate_in_default_book(self.tenant, rate_per_unit_micros=1)

    def _charge(self):
        line = a_price_for_whole_work(self.tenant, task_type="whole",
                                      agreed_price_micros=5_000_000)
        work = Task.objects.create(
            tenant=self.tenant, customer=self.customer,
            balance_snapshot_micros=0, task_type="whole",
            pricing_mode=PRICING_MODE_FIXED, agreed_price_micros=5_000_000,
            agreed_price_line_id=line.id,
            agreed_price_book_version=line.pricing_book.version,
            status=TASK_STATUS_COMPLETED, completed_at=timezone.now())
        return Charge.objects.create(
            tenant=self.tenant, task=work, amount_micros=5_000_000,
            currency=ECONOMIC_CURRENCY, agreed_price_line_id=line.id,
            book_version=line.pricing_book.version,
            resolved_at=work.created_at, charged_at=work.completed_at,
            idempotency_key=derived_key(work.id))

    def _cost_book(self):
        return cost_book(self.tenant)

    def _posting(self):
        return Posting.objects.create(tenant=self.tenant, customer=self.customer,
                                      idempotency_key=f"i-{uuid.uuid4()}")

    def _reported_cost_mapping(self):
        declares_a_caller_supplied_cost(self.tenant, "reported")
        return ReportedCostMapping.objects.get(event_type__tenant=self.tenant)

    def _supplied_revenue(self):
        return TenantSuppliedRevenue.objects.create(
            tenant=self.tenant, customer=self.customer, amount_micros=1_000_000,
            currency=ECONOMIC_CURRENCY, period_start=date(2026, 1, 1),
            recognition_method=RECOGNITION_METHOD_ON_RECEIPT,
            source_reference="inv-1")

    def _usage_invoice(self):
        return CustomerUsageInvoice.objects.create(
            tenant=self.tenant, customer=self.customer,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1))


#: ``(table, builder, column)`` — the tenant's own column is claim 3's.
ROWS = (
    ("ubb_wallet", "_wallet", "currency"),
    ("ubb_credit_grant", "_credit_grant", "currency"),
    ("ubb_rate", "_rate", "currency"),
    ("ubb_charge", "_charge", "currency"),
    ("ubb_cost_book", "_cost_book", "currency"),
    ("ubb_posting", "_posting", "currency"),
    ("ubb_reported_cost_mapping", "_reported_cost_mapping", "currency"),
    ("ubb_tenant_supplied_revenue", "_supplied_revenue", "currency"),
    ("ubb_customer_usage_invoice", "_usage_invoice", "currency"),
)

#: The one table whose UPDATE doors meet a rule ahead of the CHECK: a charge's
#: currency is FROZEN by `trg_charge_declared_transitions`, a BEFORE trigger
#: (`pricing/0031`), so an existing charge is refused by that rule first. The
#: INSERT doors are the CHECK's alone, and they are what proves it here.
UPDATE_REFUSED_FIRST_BY = {"ubb_charge": r"frozen.*\bcurrency\b"}


def _insert_a_copy(record, **columns):
    """Raw SQL INSERT of a new row: ``record``'s columns, a fresh id, and
    ``columns`` over them, each value prepared the way its field takes it."""
    model = type(record)
    names, values = [], []
    for field in model._meta.concrete_fields:
        value = getattr(record, field.attname)
        if field.primary_key:
            value = uuid.uuid4()
        value = columns.get(field.name, value)
        names.append(field.column)
        values.append(field.get_db_prep_save(value, connection))
    placeholders = ", ".join(["%s"] * len(names))
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {model._meta.db_table} ({', '.join(names)}) "
            f"VALUES ({placeholders})", values)


def _create_a_copy(record, **columns):
    """`objects.create()` of a new row from ``record``'s columns."""
    model = type(record)
    fields = {field.attname: getattr(record, field.attname)
              for field in model._meta.concrete_fields
              if not field.primary_key}
    fields.update({model._meta.get_field(name).attname: value
                   for name, value in columns.items()})
    model.objects.create(**fields)


def _update_through_the_queryset(record, **columns):
    type(record).objects.filter(pk=record.pk).update(**columns)


def _update_through_raw_sql(record, **columns):
    """Each value prepared the way its own column takes it (a `jsonb` column
    is not handed a bare list)."""
    model = type(record)
    fields = [model._meta.get_field(name) for name in columns]
    assignments = ", ".join(f"{field.column} = %s" for field in fields)
    values = [field.get_db_prep_save(value, connection)
              for field, value in zip(fields, columns.values())]
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {model._meta.db_table} SET {assignments} WHERE id = %s",
            [*values, str(record.pk)])


BIRTH_DOORS = (("objects.create()", _create_a_copy),
               ("raw SQL INSERT", _insert_a_copy))
CHANGE_DOORS = (("QuerySet.update()", _update_through_the_queryset),
                ("raw SQL UPDATE", _update_through_raw_sql))


class TheDatabaseRefusesAnotherCurrencyThroughEveryDoorTest(_Rows, TestCase):
    """Claim 2."""

    def _refused(self, door, record, column, refusal):
        with self.assertRaisesRegex(IntegrityError, refusal):
            with transaction.atomic():
                door(record, **{column: FOREIGN})

    def test_no_row_is_born_in_another_currency(self):
        for table, builder, column in ROWS:
            record = getattr(self, builder)()
            for name, door in BIRTH_DOORS:
                with self.subTest(table=table, door=name):
                    before = type(record).objects.count()
                    self._refused(door, record, column, HELD_BY[(table, column)])
                    self.assertEqual(type(record).objects.count(), before)

    def test_no_row_is_moved_into_another_currency(self):
        for table, builder, column in ROWS:
            record = getattr(self, builder)()
            refusal = UPDATE_REFUSED_FIRST_BY.get(table, HELD_BY[(table, column)])
            for name, door in CHANGE_DOORS:
                with self.subTest(table=table, door=name):
                    self._refused(door, record, column, refusal)
                    record.refresh_from_db()
                    self.assertEqual(getattr(record, column), ECONOMIC_CURRENCY)

    def test_the_reported_cost_may_still_name_no_code(self):
        """THE CONTROL for the one `or_blank` column: a mapping that reads its
        currency off the supplier's response pins none, and the rule must not
        refuse that shape — only another code."""
        mapping = self._reported_cost_mapping()
        _update_through_raw_sql(mapping, currency="", currency_path=["c"])
        mapping.refresh_from_db()
        self.assertEqual(mapping.currency, "")

    def test_a_usd_row_is_admitted_through_every_door(self):
        """THE CONTROL for the whole class: every refusal above would also be
        satisfied by a rule refusing every write to these tables."""
        for table, builder, column in ROWS:
            if table in UPDATE_REFUSED_FIRST_BY:
                continue
            record = getattr(self, builder)()
            with self.subTest(table=table):
                _update_through_raw_sql(record, **{column: ECONOMIC_CURRENCY})
                _update_through_the_queryset(record, **{column: ECONOMIC_CURRENCY})


class ATenantIsRefusedByTheDomainRuleBeforeTheDatabaseTest(TestCase):
    """Claim 3, and the tenant column's own three doors."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Dollars", products=["metering"])

    def test_save_refuses_by_name_and_writes_nothing(self):
        self.tenant.default_currency = FOREIGN
        with self.assertRaises(ValidationError) as refused:
            self.tenant.save()
        self.assertIn("default_currency", refused.exception.message_dict)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.default_currency, ECONOMIC_CURRENCY)

    def test_save_stores_the_one_currency_in_its_own_spelling(self):
        self.tenant.default_currency = " USD "
        self.tenant.save()
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.default_currency, ECONOMIC_CURRENCY)

    def test_the_doors_that_skip_save_meet_the_check(self):
        name = HELD_BY[("ubb_tenant", "default_currency")]
        for door_name, door in CHANGE_DOORS:
            with self.subTest(door=door_name):
                with self.assertRaisesRegex(IntegrityError, name):
                    with transaction.atomic():
                        door(self.tenant, default_currency=FOREIGN)
                self.tenant.refresh_from_db()
                self.assertEqual(self.tenant.default_currency, ECONOMIC_CURRENCY)

    def test_a_new_tenant_cannot_be_born_in_another_currency(self):
        with self.assertRaises(ValidationError):
            Tenant.objects.create(name="Euros", products=["metering"],
                                  default_currency=FOREIGN)
        with self.assertRaisesRegex(IntegrityError,
                                    HELD_BY[("ubb_tenant", "default_currency")]):
            with transaction.atomic():
                _insert_a_copy(self.tenant, default_currency=FOREIGN)
        self.assertFalse(Tenant.objects.filter(name="Euros").exists())


#: ``(app, the migration that installs the CHECKs, its predecessor, table,
#: builder)`` — one row per app, so each reconciliation is driven for real.
#: The tenant row is the fixture's own (``None``).
INSTALLED_BY = (
    ("tenants", "0028_a_tenant_holds_usd_only",
     "0027_admission_control_comes_to_the_kernel", "ubb_tenant", None),
    ("wallets", "0012_wallet_money_is_usd_only",
     "0011_a_prepaid_start_reserves_the_agreed_price", "ubb_wallet", "_wallet"),
    ("pricing", "0033_rules_charges_and_cost_books_are_usd_only",
     "0032_an_agreed_price_is_published_with_provenance", "ubb_cost_book",
     "_cost_book"),
    ("usage", "0051_a_posting_is_usd_only",
     "0050_a_held_price_states_its_reason", "ubb_posting", "_posting"),
    ("event_types", "0013_a_reported_cost_is_pinned_to_usd_only",
     "0012_a_publication_keeps_its_supplier", "ubb_reported_cost_mapping",
     "_reported_cost_mapping"),
    ("subscriptions", "0017_supplied_revenue_is_usd_only",
     "0016_the_snapshot_stops_freezing_who_sends_the_invoice",
     "ubb_tenant_supplied_revenue", "_supplied_revenue"),
    ("invoicing", "0010_a_usage_invoice_is_usd_only",
     "0009_invoice_lines_take_the_one_grouping_vocabulary",
     "ubb_customer_usage_invoice", "_usage_invoice"),
)

#: The column each table's reconciliation reads.
HELD_BY_COLUMN = {table: column for (table, column) in HELD_BY}


def _migrate_to(app, name):
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    MigrationExecutor(connection).migrate([(app, name)])


def _stored(table, column, pk):
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {column} FROM {table} WHERE id = %s", [str(pk)])
        return cursor.fetchone()[0]


def _store(table, column, pk, value):
    with connection.cursor() as cursor:
        cursor.execute(f"UPDATE {table} SET {column} = %s WHERE id = %s",
                       [value, str(pk)])


class TheMigrationsReconcileByRefusingTest(_Rows, TestCase):
    """The reconciliation each migration runs before its `CHECK`, run for real
    — through Django's executor, back to the predecessor and forward again,
    inside the test's transaction (PostgreSQL runs the DDL transactionally, so
    it leaves with the test; `work`'s #562 module is the precedent).

    A row is planted in another currency while the `CHECK` is gone, which is
    the only state in which one could exist. The forward migration must stop
    and name it, convert nothing and relabel nothing; once a person corrects
    the row it must go through."""

    def _plant(self, app, predecessor, table, builder, value):
        record = self.tenant if builder is None else getattr(self, builder)()
        column = HELD_BY_COLUMN[table]
        _migrate_to(app, predecessor)
        _store(table, column, record.pk, value)
        return record, column

    def test_each_migration_stops_on_a_foreign_row_and_rewrites_nothing(self):
        for app, installer, predecessor, table, builder in INSTALLED_BY:
            with self.subTest(app=app):
                record, column = self._plant(app, predecessor, table, builder,
                                             FOREIGN)
                with self.assertRaisesRegex(
                        RuntimeError, rf"{table}\.{column}.*'{FOREIGN}' x1"):
                    _migrate_to(app, installer)
                self.assertEqual(_stored(table, column, record.pk), FOREIGN)
                self.assertNotIn(HELD_BY[(table, column)],
                                 _checks_on(table, column))
                _store(table, column, record.pk, ECONOMIC_CURRENCY)
                _migrate_to(app, installer)
                self.assertIn(HELD_BY[(table, column)],
                              _checks_on(table, column))

    def test_a_stored_capital_usd_is_refused_rather_than_relabelled(self):
        """`'USD'` names the right currency in another spelling, and a
        migration that lower-cased it would be deciding a row's meaning on a
        reader's behalf. It is named like any other row."""
        app, installer, predecessor, table, builder = INSTALLED_BY[1]
        record, column = self._plant(app, predecessor, table, builder, "USD")
        with self.assertRaisesRegex(RuntimeError, r"'USD' x1"):
            _migrate_to(app, installer)
        self.assertEqual(_stored(table, column, record.pk), "USD")
        _store(table, column, record.pk, ECONOMIC_CURRENCY)
        _migrate_to(app, installer)
