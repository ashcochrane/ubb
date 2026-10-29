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

Before the cutover (#190) a fourth class drove the seven migrations that
installed these `CHECK`s (R10-W3) through the executor, proving each stopped on
a foreign row, named it and relabelled nothing. A fresh database is created
with every `CHECK` in place, so no row can predate one; the inventory above and
the doors below are the end state those migrations reached.
"""

import uuid
from datetime import date

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, models, transaction
from django.test import TestCase
from django.utils import timezone

from apps.billing.invoicing.models import CustomerUsageInvoice
from apps.billing.tenant_billing.models import TenantBillingPeriod
from apps.billing.wallets.models import CreditGrant, Wallet
from apps.metering.pricing.models import Charge, CostBook, Rate
from apps.metering.pricing.services.charge_service import derived_key
from apps.metering.pricing.tests._helpers import (
    a_price_for_whole_work,
    cost_book,
    rate_in_default_book,
)
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
from apps.metering.usage.tests._helpers import a_posting

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
    ("ubb_tenant_billing_period", "currency"): "ck_billing_period_currency_usd",
}

#: The columns that record what Stripe SENT (#564), spared the USD `CHECK` —
#: and the one rule each does carry, which holds no currency to US dollars:
#: it pairs the economic amount with the source currency, so a foreign code
#: is kept and a relabelled dollar amount beside it is refused.
SOURCE_FACTS = {
    ("ubb_stripe_subscription", "currency"):
        "ck_subscription_economic_amount_only_in_usd",
    ("ubb_subscription_invoice", "currency"):
        "ck_subscription_invoice_economic_amount_only_in_usd",
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
        self.assertEqual(set(_currency_columns()),
                         set(HELD_BY) | set(SOURCE_FACTS))

    def test_every_economic_column_carries_the_policys_check(self):
        for (table, column), name in HELD_BY.items():
            with self.subTest(table=table):
                checks = _checks_on(table, column)
                self.assertIn(name, checks)
                self.assertIn(f"'{ECONOMIC_CURRENCY}'", checks[name])

    def test_the_source_facts_are_declared_on_their_models_and_spared(self):
        """Declared where the column lives, so the next reader of the model
        sees why no USD CHECK holds it — and the catalogue agrees: the one
        rule over each is the pairing, which admits a foreign code. A USD
        CHECK there would refuse the evidence #564's quarantine keeps."""
        columns = _currency_columns()
        for (table, column), pairing in sorted(SOURCE_FACTS.items()):
            with self.subTest(table=table):
                model = columns[(table, column)]
                self.assertIn(column, getattr(model, SOURCE_CURRENCY_COLUMNS))
                self.assertEqual(set(_checks_on(table, column)), {pairing})

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
        return a_posting(tenant=self.tenant, customer=self.customer,
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

    def _billing_period(self):
        return TenantBillingPeriod.objects.create(
            tenant=self.tenant, period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1))

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
    ("ubb_tenant_billing_period", "_billing_period", "currency"),
)

#: The one table whose UPDATE doors meet a rule ahead of the CHECK: a charge's
#: currency is FROZEN by `trg_charge_declared_transitions`, a BEFORE trigger
#: (`pricing/0002_the_database_rules`), so an existing charge is refused by that
#: rule first. The INSERT doors are the CHECK's alone, and they are what proves
#: it here.
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


class TheSourceFactsPairTheirAmountWithTheirCurrencyTest(TestCase):
    """The one rule over a source fact (#564), proved rather than named.

    `SOURCE_FACTS` above pins each pairing CHECK by name; this proves what
    each refuses, through every door that skips the writers: a dollar amount
    beside a foreign code (a relabel — the quarantine undone), and a dollar
    code with no dollar amount (a dollar subscription that drops out of
    revenue unnoticed). The admitted pair on either side is the control.
    """

    def setUp(self):
        from django.utils import timezone

        from apps.platform.customers.models import Customer
        from apps.platform.tenants.models import Tenant
        from apps.subscriptions.models import SubscriptionInvoice
        from apps.subscriptions.tests._helpers import a_mirrored_subscription

        now = timezone.now()
        tenant = Tenant.objects.create(name="Mirror", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="m1")
        self.subscription = a_mirrored_subscription(
            tenant=tenant, customer=customer, stripe_subscription_id="sub_eur",
            stripe_product_name="Pro", status="active", amount_micros=None,
            source_amount_minor=1999, quantity=1, currency="eur",
            interval="month", current_period_start=now, current_period_end=now,
            last_synced_at=now)
        self.invoice = SubscriptionInvoice.objects.create(
            tenant=tenant, customer=customer, stripe_subscription=self.subscription,
            stripe_invoice_id="in_eur", amount_paid_micros=None,
            source_amount_paid_minor=1999, currency="eur",
            period_start=now, period_end=now, paid_at=now)

    def _doors(self, row, **columns):
        table = row._meta.db_table
        sets = ", ".join(f"{column} = %s" for column in columns)
        return {
            "QuerySet.update()": lambda: type(row).objects.filter(
                pk=row.pk).update(**columns),
            "raw SQL": lambda: connection.cursor().execute(
                f"UPDATE {table} SET {sets} WHERE id = %s",
                [*columns.values(), str(row.pk)]),
        }

    def test_neither_half_of_the_pair_moves_without_the_other(self):
        cases = {
            "a dollar amount beside a foreign code": (
                (self.subscription, "ck_subscription_economic_amount_only_in_usd",
                 {"amount_micros": 19_990_000}),
                (self.invoice, "ck_subscription_invoice_economic_amount_only_in_usd",
                 {"amount_paid_micros": 19_990_000})),
            "a dollar code with no dollar amount": (
                (self.subscription, "ck_subscription_economic_amount_only_in_usd",
                 {"currency": "usd"}),
                (self.invoice, "ck_subscription_invoice_economic_amount_only_in_usd",
                 {"currency": "usd"})),
        }
        for case, rows in cases.items():
            for row, check, columns in rows:
                for door, write in self._doors(row, **columns).items():
                    with self.subTest(case=case, table=row._meta.db_table, door=door):
                        with self.assertRaisesRegex(IntegrityError, check):
                            with transaction.atomic():
                                write()

    def test_the_admitted_pair_moves_together(self):
        """THE CONTROL: the same doors, both halves at once."""
        for row, columns in (
                (self.subscription, {"currency": "usd", "amount_micros": 19_990_000}),
                (self.invoice, {"currency": "usd", "amount_paid_micros": 19_990_000})):
            for door, write in self._doors(row, **columns).items():
                with self.subTest(table=row._meta.db_table, door=door):
                    write()
