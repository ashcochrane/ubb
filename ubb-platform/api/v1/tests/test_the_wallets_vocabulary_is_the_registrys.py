"""The wallet's own vocabulary is the registry's (R10-W4, ruling 7).

A wallet transaction's type is the registry's closed `wallet_transaction_type`,
LOWERCASE: the ledger spelled its eleven in upper case until R10-W4, outside the
registry's token rule, and the owner ruled the canonical tokens lowercase with no
per-concept exception and no dual acceptance. A credit grant's source spells the
automatic top-up `auto_top_up`, one concept's one spelling (ADR-0006 §2). These
go through the public route, the table's every door, and `wallets/0014` run for
real.
"""
import json

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase

from apps.billing.wallets.models import CreditGrant, Wallet, WalletTransaction
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.vocabulary import (
    GRANT_SOURCE_AUTO_TOP_UP, GRANT_SOURCE_VALUES,
    WALLET_TRANSACTION_TYPE_ADJUSTMENT, WALLET_TRANSACTION_TYPE_DEBIT,
    WALLET_TRANSACTION_TYPE_VALUES)

#: The spellings the ledger stored before R10-W4, as data a migration test
#: plants. Derived rather than listed: upper-casing the registry's value is what
#: the ledger used to do, and a list would be a second copy of the eleven.
UPPERCASE = {value.upper(): value for value in WALLET_TRANSACTION_TYPE_VALUES}
#: The automatic top-up's lots carried the run-together spelling.
OLD_AUTO_TOP_UP = GRANT_SOURCE_AUTO_TOP_UP.replace("top_up", "topup")


class _AWalletTestCase(TestCase):

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Wallets",
                                            products=["metering", "billing"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="k")
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")
        self.wallet = Wallet.objects.create(customer=self.customer,
                                            balance_micros=10_000_000)


class TheLedgerSpeaksLowercaseTest(_AWalletTestCase):

    def test_the_transactions_route_publishes_the_registrys_tokens(self):
        http = Client()
        auth = {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}
        for route, extra in (("credit", {"source": "manual"}),
                             ("debit", {"allow_negative": True})):
            answered = http.post(
                f"/api/v1/billing/{route}", content_type="application/json",
                data=json.dumps({"customer_id": "c1", "amount_micros": 1_000_000,
                                 "reference": "r", "idempotency_key": route,
                                 **extra}), **auth)
            self.assertEqual(answered.status_code, 200, answered.content)

        listed = http.get(
            f"/api/v1/billing/customers/{self.customer.id}/transactions", **auth)

        self.assertEqual(listed.status_code, 200, listed.content)
        types = {row["transaction_type"] for row in listed.json()["data"]}
        self.assertEqual(types, {WALLET_TRANSACTION_TYPE_ADJUSTMENT,
                                 WALLET_TRANSACTION_TYPE_DEBIT})


class TheTableRefusesAnotherSpellingTest(_AWalletTestCase):
    """No dual acceptance: the old spelling is refused, never translated."""

    def _refused(self, constraint, write):
        with self.assertRaisesRegex(IntegrityError, constraint):
            with transaction.atomic():
                write()

    def test_an_uppercase_type_is_refused_through_every_door(self):
        txn = WalletTransaction.objects.create(
            wallet=self.wallet, transaction_type=WALLET_TRANSACTION_TYPE_DEBIT,
            amount_micros=-1, balance_after_micros=9_999_999)
        for upper in sorted(UPPERCASE):
            with self.subTest(spelling=upper):
                self._refused("ck_wallet_transaction_type_known",
                              lambda: WalletTransaction.objects.create(
                                  wallet=self.wallet, transaction_type=upper,
                                  amount_micros=1, balance_after_micros=1))
                self._refused("ck_wallet_transaction_type_known",
                              lambda: WalletTransaction.objects.filter(
                                  pk=txn.pk).update(transaction_type=upper))

                def raw():
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "UPDATE ubb_wallet_transaction SET transaction_type "
                            "= %s WHERE id = %s", [upper, str(txn.pk)])
                self._refused("ck_wallet_transaction_type_known", raw)

    def test_every_registry_type_is_admitted(self):
        for value in sorted(WALLET_TRANSACTION_TYPE_VALUES):
            with self.subTest(value=value):
                WalletTransaction.objects.create(
                    wallet=self.wallet, transaction_type=value,
                    amount_micros=1, balance_after_micros=1)

    def test_the_old_grant_source_spelling_is_refused(self):
        grant = CreditGrant.objects.create(
            tenant=self.tenant, wallet=self.wallet, kind="paid",
            granted_micros=1, remaining_micros=1, currency="usd",
            source=GRANT_SOURCE_AUTO_TOP_UP)
        self._refused("ck_credit_grant_source_known",
                      lambda: CreditGrant.objects.filter(pk=grant.pk).update(
                          source=OLD_AUTO_TOP_UP))
        for value in sorted(GRANT_SOURCE_VALUES):
            CreditGrant.objects.filter(pk=grant.pk).update(source=value)


class TheMigrationMovesEveryStoredRowTest(_AWalletTestCase):
    """`wallets/0014` through the executor and back: every stored upper-case
    type and every run-together grant source moves to the registry's token."""

    BEFORE = ("wallets", "0013_a_wallet_movement_states_its_reason")
    AFTER = ("wallets", "0014_wallet_vocabulary_is_the_registrys")

    def _migrate_to(self, target):
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        MigrationExecutor(connection).migrate([target])

    def tearDown(self):
        self._migrate_to(self.AFTER)

    def _column(self, table, column, pk):
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT {column} FROM {table} WHERE id = %s", [str(pk)])
            return cursor.fetchone()[0]

    def test_the_stored_rows_move_to_the_registrys_tokens_and_back(self):
        rows = {upper: WalletTransaction.objects.create(
            wallet=self.wallet, transaction_type=lower, amount_micros=1,
            balance_after_micros=1) for upper, lower in UPPERCASE.items()}
        grant = CreditGrant.objects.create(
            tenant=self.tenant, wallet=self.wallet, kind="paid",
            granted_micros=1, remaining_micros=1, currency="usd",
            source=GRANT_SOURCE_AUTO_TOP_UP)

        self._migrate_to(self.BEFORE)
        with connection.cursor() as cursor:
            for upper, row in rows.items():
                cursor.execute("UPDATE ubb_wallet_transaction SET "
                               "transaction_type = %s WHERE id = %s",
                               [upper, str(row.pk)])
            cursor.execute("UPDATE ubb_credit_grant SET source = %s "
                           "WHERE id = %s", [OLD_AUTO_TOP_UP, str(grant.pk)])

        self._migrate_to(self.AFTER)
        for upper, row in rows.items():
            self.assertEqual(self._column("ubb_wallet_transaction",
                                          "transaction_type", row.pk),
                             UPPERCASE[upper])
        self.assertEqual(self._column("ubb_credit_grant", "source", grant.pk),
                         GRANT_SOURCE_AUTO_TOP_UP)

        self._migrate_to(self.BEFORE)
        for upper, row in rows.items():
            self.assertEqual(self._column("ubb_wallet_transaction",
                                          "transaction_type", row.pk), upper)
        self.assertEqual(self._column("ubb_credit_grant", "source", grant.pk),
                         OLD_AUTO_TOP_UP)
