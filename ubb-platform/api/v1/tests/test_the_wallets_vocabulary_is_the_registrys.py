"""The wallet's own vocabulary is the registry's (R10-W4, ruling 7).

A wallet transaction's type is the registry's closed `wallet_transaction_type`,
LOWERCASE: the ledger spelled its eleven in upper case until R10-W4, outside the
registry's token rule, and the owner ruled the canonical tokens lowercase with no
per-concept exception and no dual acceptance. A credit grant's source spells the
automatic top-up `auto_top_up`, one concept's one spelling (ADR-0006 §2). These
go through the public route and the table's every door, where
`ck_wallet_transaction_type_known` and `ck_credit_grant_source_known` refuse
the old spellings.

Before the cutover (#190) a case here also ran `wallets/0014` through the
executor and back, moving every stored upper-case type and every run-together
grant source to the registry's token; that data step left with the squashed
chain.
"""
import json

from django.db import IntegrityError, connection, transaction
from django.test import Client, TestCase

from api.v1.tests._helpers import a_tenant
from apps.billing.wallets.models import CreditGrant, Wallet, WalletTransaction
from apps.platform.customers.models import Customer
from core.vocabulary import (
    GRANT_SOURCE_AUTO_TOP_UP, GRANT_SOURCE_VALUES,
    WALLET_TRANSACTION_TYPE_ADJUSTMENT, WALLET_TRANSACTION_TYPE_DEBIT,
    WALLET_TRANSACTION_TYPE_VALUES)

#: The spellings the ledger stored before R10-W4, as the refusals below send
#: them. Derived rather than listed: upper-casing the registry's value is what
#: the ledger used to do, and a list would be a second copy of the eleven.
UPPERCASE = {value.upper(): value for value in WALLET_TRANSACTION_TYPE_VALUES}
#: The automatic top-up's lots carried the run-together spelling.
OLD_AUTO_TOP_UP = GRANT_SOURCE_AUTO_TOP_UP.replace("top_up", "topup")


class _AWalletTestCase(TestCase):

    def setUp(self):
        self.tenant, self.raw_key = a_tenant(
            "Wallets", products=("metering", "billing"))
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
