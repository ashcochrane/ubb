"""A wallet movement states its reason, under its own name (#479).

A manual credit or debit carries why the money moved — the registry's closed
`movement_reason`. It was `reason_code` until #479, which is the stop cause's
public name: a different concept (why work was stopped), published on the stop
surfaces, and ADR-0006 §2 does not let two concepts share one. These tests go
through the two routes, and the column's set through every door that skips
them.
"""
import json

from django.db import IntegrityError, connection, transaction
from django.test import Client, TestCase

from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.platform.audit.models import AuditRecord
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.vocabulary import MOVEMENT_REASON_VALUES, REASON_CODE_KNOWN_VALUES

ROUTES = {"credit": {"source": "manual"}, "debit": {"allow_negative": True}}


class _WalletRoutesTestCase(TestCase):
    """A billing tenant, one customer's wallet, and the two routes."""

    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="Wallets",
                                            products=["metering", "billing"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="k")
        customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        Wallet.objects.create(customer=customer, balance_micros=10_000_000)
        self.keys = iter(range(1000))

    def _move(self, route, **fields):
        body = {"customer_id": "c1", "amount_micros": 1_000_000,
                "reference": "adj", "idempotency_key": f"k-{next(self.keys)}",
                **ROUTES[route], **fields}
        return self.http.post(f"/api/v1/billing/{route}", data=json.dumps(body),
                              content_type="application/json",
                              HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")


class AMovementStatesItsReasonTest(_WalletRoutesTestCase):

    def test_every_reason_is_stored_on_the_ledger_and_in_the_audit(self):
        for route in ROUTES:
            for reason in sorted(MOVEMENT_REASON_VALUES):
                with self.subTest(route=route, reason=reason):
                    answered = self._move(route, movement_reason=reason,
                                          actor="ops@acme.co")

                    self.assertEqual(answered.status_code, 200, answered.content)
                    txn = WalletTransaction.objects.get(
                        id=answered.json()["transaction_id"])
                    self.assertEqual((txn.movement_reason, txn.actor),
                                     (reason, "ops@acme.co"))
                    audit = AuditRecord.objects.get(
                        action=f"wallet.{route}ed",
                        metadata__transaction_id=answered.json()["transaction_id"])
                    self.assertEqual(audit.metadata["movement_reason"], reason)
                    self.assertNotIn("reason_code", audit.metadata)

    def test_no_reason_records_none(self):
        for route in ROUTES:
            for sent in ({}, {"movement_reason": None}):
                with self.subTest(route=route, sent=sent):
                    answered = self._move(route, **sent)

                    self.assertEqual(answered.status_code, 200, answered.content)
                    txn = WalletTransaction.objects.get(
                        id=answered.json()["transaction_id"])
                    self.assertEqual(txn.movement_reason, "")

    def test_a_value_outside_the_set_is_refused_and_moves_nothing(self):
        # A stop cause is the sharpest wrong value: the field's old name was
        # the stop's, and its values are not movement reasons.
        for route in ROUTES:
            for wrong in ("bogus", "", sorted(REASON_CODE_KNOWN_VALUES)[0]):
                with self.subTest(route=route, wrong=wrong):
                    before = WalletTransaction.objects.count()

                    answered = self._move(route, movement_reason=wrong)

                    self.assertEqual(answered.status_code, 422, answered.content)
                    self.assertEqual(answered.json()["code"], "validation_error")
                    self.assertEqual(WalletTransaction.objects.count(), before)


class TheRetiredFieldIsRefusedNotDroppedTest(_WalletRoutesTestCase):
    """A raw-HTTP caller still sending `reason_code` is refused through the
    normal validation path — never answered 200 with the reason lost, and
    never read as an alias. Both routes, with and without the new field."""

    def test_the_retired_field_is_refused_by_name_and_moves_nothing(self):
        for route in ROUTES:
            for sent in ({"reason_code": "goodwill"},
                         {"reason_code": "goodwill", "movement_reason": "goodwill"},
                         {"reason_code": None}):
                with self.subTest(route=route, sent=sent):
                    before = WalletTransaction.objects.count()

                    answered = self._move(route, **sent)

                    self.assertEqual(answered.status_code, 422, answered.content)
                    body = answered.json()
                    self.assertEqual(body["code"], "validation_error")
                    self.assertIn("movement_reason", json.dumps(body["errors"]))
                    self.assertEqual(WalletTransaction.objects.count(), before)


class TheLedgerHoldsTheSetTest(TestCase):
    """The route refuses by hand; the column's `CHECK` is what a write that
    skips the route meets."""

    def setUp(self):
        tenant = Tenant.objects.create(name="Wallets", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        wallet = Wallet.objects.create(customer=customer, balance_micros=0)
        self.txn = WalletTransaction.objects.create(
            wallet=wallet, transaction_type="ADJUSTMENT", amount_micros=1,
            balance_after_micros=1, movement_reason="goodwill")

    def test_an_unknown_reason_is_refused_through_every_door(self):
        doors = {
            "save()": lambda: _saved_with(self.txn, "bogus"),
            "QuerySet.update()": lambda: WalletTransaction.objects.filter(
                pk=self.txn.pk).update(movement_reason="bogus"),
            "raw SQL": lambda: connection.cursor().execute(
                "UPDATE ubb_wallet_transaction SET movement_reason = %s "
                "WHERE id = %s", ["bogus", str(self.txn.pk)]),
        }
        for door, write in doors.items():
            with self.subTest(door=door):
                with self.assertRaisesRegex(
                        IntegrityError, "ck_wallet_transaction_movement_reason_known"):
                    with transaction.atomic():
                        write()
                self.txn.refresh_from_db()
                self.assertEqual(self.txn.movement_reason, "goodwill")

    def test_every_reason_and_none_are_admitted(self):
        """The control: the same door, every legal value."""
        for reason in sorted(MOVEMENT_REASON_VALUES) + [""]:
            with self.subTest(reason=reason):
                WalletTransaction.objects.filter(pk=self.txn.pk).update(
                    movement_reason=reason)
                self.txn.refresh_from_db()
                self.assertEqual(self.txn.movement_reason, reason)


def _saved_with(txn, reason):
    txn.movement_reason = reason
    txn.save()
