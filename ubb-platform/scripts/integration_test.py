#!/usr/bin/env python3
"""
Integration test script for UBB platform Stripe integration.

This script tests the full flow with detailed balance and transaction verification:
1. Create customer with Stripe customer ID
2. Verify initial balance is 0
3. Create top-up checkout session (or fund directly in skip-stripe mode)
4. Verify balance after funding
5. Record usage and verify exact balance deduction
6. Test withdrawal and verify balance
7. Test refund and verify balance restored
8. Verify all transactions are recorded with correct types/amounts
9. Test tenant billing endpoints
10. Test subscriptions endpoints (sync, subscription data, invoices, economics)
11. Test referrals endpoints (program, referrers, attribution, earnings, analytics)

Prerequisites:
- Local server running: python manage.py runserver
- Stripe CLI listening: stripe listen --forward-to localhost:8000/api/v1/webhooks/stripe
- Valid Stripe customer ID on the tenant's connected account

Usage:
    python scripts/integration_test.py --api-key <ubb_api_key> --stripe-customer-id <cus_xxx>

    # Skip Stripe checkout (funds wallet directly via DB):
    python scripts/integration_test.py --api-key <ubb_api_key> --stripe-customer-id <cus_xxx> --skip-stripe-webhook

    # Include subscriptions tests (requires tenant with subscriptions product):
    python scripts/integration_test.py --api-key <ubb_api_key> --stripe-customer-id <cus_xxx> --skip-stripe-webhook --test-subscriptions

    # Include referrals tests:
    python scripts/integration_test.py --api-key <ubb_api_key> --stripe-customer-id <cus_xxx> --skip-stripe-webhook --test-referrals
"""

import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone as dt_timezone
from typing import Optional

import requests


@dataclass
class TestConfig:
    base_url: str
    api_key: str
    stripe_customer_id: str
    stripe_connected_account_id: Optional[str] = None
    db_url: Optional[str] = None
    test_subscriptions: bool = False
    test_referrals: bool = False


@dataclass
class TestState:
    """Track state throughout test run for balance verification."""
    customer_id: Optional[str] = None
    expected_balance: int = 0
    usage_event_ids: list = field(default_factory=list)
    transaction_count: int = 0
    usage_cost_1: int = 1_000_000  # $1.00
    usage_cost_2: int = 500_000    # $0.50 (for idempotency test)
    withdraw_amount: int = 500_000  # $0.50
    top_up_amount: int = 10_000_000  # $10.00
    # Subscriptions state
    stripe_subscription_id: Optional[str] = None
    subscription_invoice_id: Optional[str] = None
    # Referrals state
    referrer_customer_id: Optional[str] = None
    referred_customer_id: Optional[str] = None
    referral_code: Optional[str] = None
    referral_id: Optional[str] = None


class IntegrationTestRunner:
    def __init__(self, config: TestConfig):
        self.config = config
        self.state = TestState()
        self.results: list[dict] = []

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

    def _log(self, test_name: str, passed: bool, details: str = ""):
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {test_name}")
        if details:
            print(f"       {details}")
        self.results.append({"test": test_name, "passed": passed, "details": details})

    def _get(self, path: str) -> requests.Response:
        return requests.get(f"{self.config.base_url}{path}", headers=self._headers())

    def _post(self, path: str, data: dict) -> requests.Response:
        return requests.post(
            f"{self.config.base_url}{path}",
            headers=self._headers(),
            json=data,
        )

    def _put(self, path: str, data: dict) -> requests.Response:
        return requests.put(
            f"{self.config.base_url}{path}",
            headers=self._headers(),
            json=data,
        )

    def _get_balance(self) -> Optional[int]:
        """Helper to get current balance."""
        resp = self._get(f"/customers/{self.state.customer_id}/balance")
        if resp.status_code == 200:
            return resp.json()["balance_micros"]
        return None

    def _get_transactions(self) -> Optional[list]:
        """Helper to get all transactions."""
        resp = self._get(f"/customers/{self.state.customer_id}/transactions?limit=100")
        if resp.status_code == 200:
            return resp.json()["data"]
        return None

    def _verify_balance(self, test_name: str, expected: int) -> bool:
        """Verify balance matches expected value."""
        actual = self._get_balance()
        passed = actual == expected
        self._log(
            f"{test_name}: balance verification",
            passed,
            f"expected={expected}, actual={actual}"
        )
        return passed

    # =========================================================================
    # TESTS
    # =========================================================================

    def test_health(self) -> bool:
        try:
            resp = requests.get(f"{self.config.base_url}/health")
            passed = resp.status_code == 200 and resp.json().get("status") == "ok"
            self._log("Health check", passed, f"status={resp.status_code}")
            return passed
        except Exception as e:
            self._log("Health check", False, str(e))
            return False

    def test_create_customer(self) -> bool:
        external_id = f"integration_test_{uuid.uuid4().hex[:8]}"
        resp = self._post("/customers", {
            "external_id": external_id,
            "stripe_customer_id": self.config.stripe_customer_id,
            "metadata": {"test": True, "created_by": "integration_test"},
        })

        if resp.status_code == 201:
            body = resp.json()
            self.state.customer_id = body["id"]
            self._log("Create customer", True, f"customer_id={self.state.customer_id}")
            return True
        else:
            self._log("Create customer", False, f"status={resp.status_code}, body={resp.text}")
            return False

    def test_initial_balance_is_zero(self) -> bool:
        balance = self._get_balance()
        passed = balance == 0
        self.state.expected_balance = 0
        self._log("Initial balance is 0", passed, f"balance={balance}")
        return passed

    def test_initial_transactions_empty(self) -> bool:
        txns = self._get_transactions()
        passed = txns is not None and len(txns) == 0
        self._log("Initial transactions empty", passed, f"count={len(txns) if txns else 'N/A'}")
        return passed

    def test_create_topup_checkout(self) -> Optional[str]:
        resp = self._post(f"/customers/{self.state.customer_id}/top-up", {
            "amount_micros": self.state.top_up_amount,
            "success_url": "http://localhost:3000/success",
            "cancel_url": "http://localhost:3000/cancel",
        })

        if resp.status_code == 200:
            body = resp.json()
            checkout_url = body.get("checkout_url", "")
            has_url = checkout_url.startswith("https://checkout.stripe.com")
            self._log("Create top-up checkout", has_url, f"url_prefix_valid={has_url}")
            return checkout_url if has_url else None
        else:
            self._log("Create top-up checkout", False, f"status={resp.status_code}, body={resp.text}")
            return None

    def fund_wallet_directly(self) -> bool:
        """Fund wallet via DB when skipping Stripe."""
        try:
            import psycopg

            db_url = self.config.db_url or os.environ.get(
                "DATABASE_URL", "postgresql://heyotis:heyotis@localhost:5432/ubb"
            )

            with psycopg.connect(db_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, balance_micros FROM ubb_wallet WHERE customer_id = %s",
                        (self.state.customer_id,)
                    )
                    row = cur.fetchone()
                    if not row:
                        self._log("Fund wallet directly", False, "Wallet not found")
                        return False

                    wallet_id, current_balance = row
                    new_balance = current_balance + self.state.top_up_amount

                    cur.execute(
                        "UPDATE ubb_wallet SET balance_micros = %s, updated_at = NOW() WHERE id = %s",
                        (new_balance, wallet_id)
                    )

                    txn_id = str(uuid.uuid4())
                    cur.execute(
                        """
                        INSERT INTO ubb_wallet_transaction
                        (id, created_at, updated_at, wallet_id, transaction_type, amount_micros,
                         balance_after_micros, description, reference_id, idempotency_key)
                        VALUES (%s, NOW(), NOW(), %s, 'TOP_UP', %s, %s, %s, '', %s)
                        """,
                        (txn_id, wallet_id, self.state.top_up_amount, new_balance,
                         "Integration test funding", f"test_fund_{uuid.uuid4().hex[:8]}")
                    )

                    conn.commit()

            self.state.expected_balance = new_balance
            self.state.transaction_count += 1
            self._log(
                "Fund wallet directly",
                True,
                f"amount={self.state.top_up_amount}, new_balance={new_balance}"
            )
            return True

        except ImportError:
            self._log("Fund wallet directly", False, "psycopg not installed. Run: pip install psycopg")
            return False
        except Exception as e:
            self._log("Fund wallet directly", False, str(e))
            return False

    def test_balance_after_topup(self) -> bool:
        return self._verify_balance("After top-up", self.state.expected_balance)

    def test_transaction_after_topup(self) -> bool:
        txns = self._get_transactions()
        if not txns:
            self._log("Transaction after top-up", False, "No transactions found")
            return False

        # Find TOP_UP transaction
        topup_txns = [t for t in txns if t["transaction_type"] == "TOP_UP"]
        if not topup_txns:
            self._log("Transaction after top-up", False, "No TOP_UP transaction found")
            return False

        txn = topup_txns[0]
        amount_correct = txn["amount_micros"] == self.state.top_up_amount
        balance_correct = txn["balance_after_micros"] == self.state.expected_balance

        passed = amount_correct and balance_correct
        self._log(
            "Transaction after top-up",
            passed,
            f"type=TOP_UP, amount={txn['amount_micros']}, balance_after={txn['balance_after_micros']}"
        )
        return passed

    def test_precheck_allowed(self) -> bool:
        resp = self._post("/pre-check", {"customer_id": self.state.customer_id})
        if resp.status_code == 200:
            body = resp.json()
            passed = body["allowed"] is True
            self._log("Pre-check allowed", passed, f"allowed={body['allowed']}, reason={body.get('reason')}")
            return passed
        else:
            self._log("Pre-check allowed", False, f"status={resp.status_code}")
            return False

    def test_record_usage(self) -> bool:
        """Record usage and verify balance deduction."""
        balance_before = self._get_balance()
        idem_key = f"idem_{uuid.uuid4().hex[:8]}"

        resp = self._post("/usage", {
            "customer_id": self.state.customer_id,
            "request_id": f"req_{uuid.uuid4().hex[:8]}",
            "idempotency_key": idem_key,
            "cost_micros": self.state.usage_cost_1,
            "metadata": {"test": "usage_1"},
        })

        if resp.status_code != 200:
            self._log("Record usage", False, f"status={resp.status_code}, body={resp.text}")
            return False

        body = resp.json()
        self.state.usage_event_ids.append(body["event_id"])

        # Verify balance was deducted
        expected_new_balance = balance_before - self.state.usage_cost_1
        actual_new_balance = body["new_balance_micros"]

        passed = actual_new_balance == expected_new_balance
        self.state.expected_balance = actual_new_balance
        self.state.transaction_count += 1

        self._log(
            "Record usage",
            passed,
            f"cost={self.state.usage_cost_1}, balance_before={balance_before}, "
            f"expected_after={expected_new_balance}, actual_after={actual_new_balance}"
        )
        return passed

    def test_usage_transaction_recorded(self) -> bool:
        """Verify USAGE_DEDUCTION transaction was created."""
        txns = self._get_transactions()
        deduction_txns = [t for t in txns if t["transaction_type"] == "USAGE_DEDUCTION"]

        if not deduction_txns:
            self._log("Usage transaction recorded", False, "No USAGE_DEDUCTION found")
            return False

        # Most recent deduction
        txn = deduction_txns[0]
        amount_correct = txn["amount_micros"] == -self.state.usage_cost_1

        self._log(
            "Usage transaction recorded",
            amount_correct,
            f"type=USAGE_DEDUCTION, amount={txn['amount_micros']} (expected -{self.state.usage_cost_1})"
        )
        return amount_correct

    def test_usage_idempotency(self) -> bool:
        """Same idempotency key should not double-charge."""
        balance_before = self._get_balance()
        idem_key = f"idem_dup_{uuid.uuid4().hex[:8]}"

        payload = {
            "customer_id": self.state.customer_id,
            "request_id": f"req_{uuid.uuid4().hex[:8]}",
            "idempotency_key": idem_key,
            "cost_micros": self.state.usage_cost_2,
            "metadata": {},
        }

        # First call
        resp1 = self._post("/usage", payload)
        if resp1.status_code != 200:
            self._log("Usage idempotency", False, f"First call failed: {resp1.status_code}")
            return False

        balance_after_first = resp1.json()["new_balance_micros"]
        self.state.usage_event_ids.append(resp1.json()["event_id"])
        self.state.transaction_count += 1

        # Second call with same idempotency key
        payload["request_id"] = f"req_{uuid.uuid4().hex[:8]}"  # Different request_id
        resp2 = self._post("/usage", payload)
        if resp2.status_code != 200:
            self._log("Usage idempotency", False, f"Second call failed: {resp2.status_code}")
            return False

        balance_after_second = resp2.json()["new_balance_micros"]

        # Balance should only be deducted once
        expected_balance = balance_before - self.state.usage_cost_2
        passed = (
            balance_after_first == expected_balance and
            balance_after_second == expected_balance
        )

        self.state.expected_balance = balance_after_second

        self._log(
            "Usage idempotency",
            passed,
            f"balance_before={balance_before}, after_1st={balance_after_first}, "
            f"after_2nd={balance_after_second}, expected={expected_balance}"
        )
        return passed

    def test_get_usage_history(self) -> bool:
        resp = self._get(f"/customers/{self.state.customer_id}/usage")
        if resp.status_code != 200:
            self._log("Get usage history", False, f"status={resp.status_code}")
            return False

        body = resp.json()
        events = body.get("data", [])

        # Should have 2 usage events (idempotent call doesn't create duplicate)
        passed = len(events) == 2
        self._log(
            "Get usage history",
            passed,
            f"count={len(events)} (expected 2)"
        )
        return passed

    def test_withdraw(self) -> bool:
        """Withdraw and verify balance."""
        balance_before = self._get_balance()
        idem_key = f"wd_{uuid.uuid4().hex[:8]}"

        resp = self._post(f"/customers/{self.state.customer_id}/withdraw", {
            "amount_micros": self.state.withdraw_amount,
            "idempotency_key": idem_key,
            "description": "Integration test withdrawal",
        })

        if resp.status_code != 200:
            self._log("Withdraw", False, f"status={resp.status_code}, body={resp.text}")
            return False

        body = resp.json()
        expected_balance = balance_before - self.state.withdraw_amount
        actual_balance = body["balance_micros"]

        passed = actual_balance == expected_balance
        self.state.expected_balance = actual_balance
        self.state.transaction_count += 1

        self._log(
            "Withdraw",
            passed,
            f"amount={self.state.withdraw_amount}, balance_before={balance_before}, "
            f"expected_after={expected_balance}, actual_after={actual_balance}"
        )
        return passed

    def test_withdraw_transaction_recorded(self) -> bool:
        """Verify WITHDRAWAL transaction was created."""
        txns = self._get_transactions()
        withdraw_txns = [t for t in txns if t["transaction_type"] == "WITHDRAWAL"]

        if not withdraw_txns:
            self._log("Withdraw transaction recorded", False, "No WITHDRAWAL found")
            return False

        txn = withdraw_txns[0]
        amount_correct = txn["amount_micros"] == -self.state.withdraw_amount

        self._log(
            "Withdraw transaction recorded",
            amount_correct,
            f"type=WITHDRAWAL, amount={txn['amount_micros']} (expected -{self.state.withdraw_amount})"
        )
        return amount_correct

    def test_withdraw_idempotency(self) -> bool:
        """Same idempotency key should not double-withdraw."""
        balance_before = self._get_balance()
        idem_key = f"wd_dup_{uuid.uuid4().hex[:8]}"

        payload = {
            "amount_micros": self.state.withdraw_amount,
            "idempotency_key": idem_key,
        }

        resp1 = self._post(f"/customers/{self.state.customer_id}/withdraw", payload)
        if resp1.status_code != 200:
            self._log("Withdraw idempotency", False, f"First call failed: {resp1.status_code}")
            return False

        balance_after_first = resp1.json()["balance_micros"]
        self.state.transaction_count += 1

        resp2 = self._post(f"/customers/{self.state.customer_id}/withdraw", payload)
        if resp2.status_code != 200:
            self._log("Withdraw idempotency", False, f"Second call failed: {resp2.status_code}")
            return False

        balance_after_second = resp2.json()["balance_micros"]

        expected_balance = balance_before - self.state.withdraw_amount
        passed = balance_after_first == expected_balance and balance_after_second == expected_balance

        self.state.expected_balance = balance_after_second

        self._log(
            "Withdraw idempotency",
            passed,
            f"balance_before={balance_before}, after_1st={balance_after_first}, "
            f"after_2nd={balance_after_second}, expected={expected_balance}"
        )
        return passed

    def test_withdraw_insufficient_balance(self) -> bool:
        """Withdraw more than balance should fail."""
        balance = self._get_balance()
        idem_key = f"wd_big_{uuid.uuid4().hex[:8]}"

        resp = self._post(f"/customers/{self.state.customer_id}/withdraw", {
            "amount_micros": balance + 10_000_000,  # More than current balance
            "idempotency_key": idem_key,
        })

        passed = resp.status_code == 400 and "Insufficient balance" in resp.text
        self._log(
            "Withdraw insufficient balance rejected",
            passed,
            f"status={resp.status_code}"
        )
        return passed

    def test_refund(self) -> bool:
        """Refund usage event and verify balance restored."""
        if not self.state.usage_event_ids:
            self._log("Refund", False, "No usage event to refund")
            return False

        balance_before = self._get_balance()
        event_id = self.state.usage_event_ids[0]
        idem_key = f"ref_{uuid.uuid4().hex[:8]}"

        resp = self._post(f"/customers/{self.state.customer_id}/refund", {
            "usage_event_id": event_id,
            "reason": "Integration test refund",
            "idempotency_key": idem_key,
        })

        if resp.status_code != 200:
            self._log("Refund", False, f"status={resp.status_code}, body={resp.text}")
            return False

        body = resp.json()
        # Refund should restore the usage_cost_1 amount
        expected_balance = balance_before + self.state.usage_cost_1
        actual_balance = body["balance_micros"]

        passed = actual_balance == expected_balance
        self.state.expected_balance = actual_balance
        self.state.transaction_count += 1

        self._log(
            "Refund",
            passed,
            f"refund_id={body['refund_id']}, balance_before={balance_before}, "
            f"expected_after={expected_balance}, actual_after={actual_balance}"
        )
        return passed

    def test_refund_transaction_recorded(self) -> bool:
        """Verify REFUND transaction was created."""
        txns = self._get_transactions()
        refund_txns = [t for t in txns if t["transaction_type"] == "REFUND"]

        if not refund_txns:
            self._log("Refund transaction recorded", False, "No REFUND found")
            return False

        txn = refund_txns[0]
        amount_correct = txn["amount_micros"] == self.state.usage_cost_1

        self._log(
            "Refund transaction recorded",
            amount_correct,
            f"type=REFUND, amount={txn['amount_micros']} (expected +{self.state.usage_cost_1})"
        )
        return amount_correct

    def test_double_refund_fails(self) -> bool:
        """Same event cannot be refunded twice."""
        if not self.state.usage_event_ids:
            self._log("Double refund fails", False, "No usage event")
            return False

        event_id = self.state.usage_event_ids[0]  # Already refunded
        idem_key = f"ref_dup_{uuid.uuid4().hex[:8]}"

        resp = self._post(f"/customers/{self.state.customer_id}/refund", {
            "usage_event_id": event_id,
            "reason": "Should fail",
            "idempotency_key": idem_key,
        })

        passed = resp.status_code == 409
        self._log(
            "Double refund rejected with 409",
            passed,
            f"status={resp.status_code}"
        )
        return passed

    def test_final_balance_correct(self) -> bool:
        """Verify final balance matches expected."""
        return self._verify_balance("Final balance", self.state.expected_balance)

    def test_transaction_count(self) -> bool:
        """Verify total transaction count."""
        txns = self._get_transactions()
        actual_count = len(txns) if txns else 0

        passed = actual_count == self.state.transaction_count
        self._log(
            "Transaction count",
            passed,
            f"expected={self.state.transaction_count}, actual={actual_count}"
        )
        return passed

    def test_transaction_types_present(self) -> bool:
        """Verify all expected transaction types are present."""
        txns = self._get_transactions()
        types = set(t["transaction_type"] for t in txns)

        expected_types = {"TOP_UP", "USAGE_DEDUCTION", "WITHDRAWAL", "REFUND"}
        missing = expected_types - types

        passed = len(missing) == 0
        self._log(
            "All transaction types present",
            passed,
            f"found={types}, missing={missing}"
        )
        return passed

    def test_configure_auto_topup(self) -> bool:
        resp = self._put(f"/customers/{self.state.customer_id}/auto-top-up", {
            "is_enabled": True,
            "trigger_threshold_micros": 1_000_000,
            "top_up_amount_micros": 10_000_000,
        })
        passed = resp.status_code == 200
        self._log("Configure auto top-up", passed, f"status={resp.status_code}")
        return passed

    def test_tenant_billing_periods(self) -> bool:
        resp = self._get("/tenant/billing-periods")
        if resp.status_code == 200:
            body = resp.json()
            self._log("Get tenant billing periods", True, f"count={len(body.get('data', []))}")
            return True
        else:
            self._log("Get tenant billing periods", False, f"status={resp.status_code}")
            return False

    def test_tenant_invoices(self) -> bool:
        resp = self._get("/tenant/invoices")
        if resp.status_code == 200:
            body = resp.json()
            self._log("Get tenant invoices", True, f"count={len(body.get('data', []))}")
            return True
        else:
            self._log("Get tenant invoices", False, f"status={resp.status_code}")
            return False

    def test_usage_analytics(self) -> bool:
        resp = self._get("/tenant/analytics/usage")
        if resp.status_code == 200:
            body = resp.json()
            self._log(
                "Get usage analytics",
                True,
                f"total_events={body.get('total_events', 0)}, "
                f"total_billed={body.get('total_billed_cost_micros', 0)}"
            )
            return True
        else:
            self._log("Get usage analytics", False, f"status={resp.status_code}")
            return False

    def test_revenue_analytics(self) -> bool:
        resp = self._get("/tenant/analytics/revenue")
        if resp.status_code == 200:
            body = resp.json()
            self._log(
                "Get revenue analytics",
                True,
                f"total_billed={body.get('total_billed_cost_micros', 0)}, "
                f"markup={body.get('total_markup_micros', 0)}"
            )
            return True
        else:
            self._log("Get revenue analytics", False, f"status={resp.status_code}")
            return False

    # =========================================================================
    # SUBSCRIPTIONS HELPERS
    # =========================================================================

    def _subs_get(self, path: str) -> requests.Response:
        """GET against subscriptions API (/api/v1/subscriptions/...)."""
        base = self.config.base_url  # e.g. http://localhost:8000/api/v1
        subs_url = base.rsplit("/api/v1", 1)[0] + "/api/v1/subscriptions"
        return requests.get(f"{subs_url}{path}", headers=self._headers())

    def _subs_post(self, path: str, data: dict = None) -> requests.Response:
        """POST against subscriptions API."""
        base = self.config.base_url
        subs_url = base.rsplit("/api/v1", 1)[0] + "/api/v1/subscriptions"
        return requests.post(
            f"{subs_url}{path}",
            headers=self._headers(),
            json=data or {},
        )

    def seed_subscription_via_db(self) -> bool:
        """Seed a StripeSubscription + SubscriptionInvoice directly in the DB.

        This mirrors what Stripe webhooks would create, allowing us to test
        the read-only API endpoints without a live Stripe connection.
        """
        try:
            import psycopg

            db_url = self.config.db_url or os.environ.get(
                "DATABASE_URL", "postgresql://heyotis:heyotis@localhost:5432/ubb"
            )

            with psycopg.connect(db_url) as conn:
                with conn.cursor() as cur:
                    sub_id = str(uuid.uuid4())
                    stripe_sub_id = f"sub_test_{uuid.uuid4().hex[:12]}"

                    # Look up tenant_id from the customer
                    cur.execute(
                        "SELECT tenant_id FROM ubb_customer WHERE id = %s",
                        (self.state.customer_id,)
                    )
                    row = cur.fetchone()
                    if not row:
                        self._log("Seed subscription", False, "Customer not found in DB")
                        return False
                    tenant_id = row[0]

                    # Ensure tenant has "subscriptions" in products
                    cur.execute(
                        "SELECT products FROM ubb_tenant WHERE id = %s",
                        (tenant_id,)
                    )
                    raw = cur.fetchone()[0]
                    if isinstance(raw, str):
                        products = json.loads(raw) if raw else []
                    elif isinstance(raw, list):
                        products = raw
                    else:
                        products = []
                    if "subscriptions" not in products:
                        products.append("subscriptions")
                        cur.execute(
                            "UPDATE ubb_tenant SET products = %s::jsonb, updated_at = NOW() WHERE id = %s",
                            (json.dumps(products), tenant_id),
                        )

                    period_start = date.today().replace(day=1).isoformat() + " 00:00:00"
                    if date.today().month == 12:
                        period_end = date.today().replace(year=date.today().year + 1, month=1, day=1).isoformat() + " 00:00:00"
                    else:
                        period_end = date.today().replace(month=date.today().month + 1, day=1).isoformat() + " 00:00:00"

                    # Create StripeSubscription
                    cur.execute(
                        """INSERT INTO ubb_stripe_subscription
                           (id, created_at, updated_at, tenant_id, customer_id,
                            stripe_subscription_id, stripe_product_name, status,
                            amount_micros, currency, "interval", current_period_start,
                            current_period_end, last_synced_at)
                           VALUES (%s, NOW(), NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())""",
                        (sub_id, tenant_id, self.state.customer_id,
                         stripe_sub_id, "Pro Plan", "active",
                         490_000_000, "usd", "month",
                         period_start, period_end),
                    )
                    self.state.stripe_subscription_id = stripe_sub_id

                    # Create SubscriptionInvoice
                    inv_id = str(uuid.uuid4())
                    stripe_inv_id = f"in_test_{uuid.uuid4().hex[:12]}"
                    cur.execute(
                        """INSERT INTO ubb_subscription_invoice
                           (id, created_at, updated_at, tenant_id, customer_id,
                            stripe_subscription_id, stripe_invoice_id, amount_paid_micros,
                            currency, period_start, period_end, paid_at)
                           VALUES (%s, NOW(), NOW(), %s, %s, %s, %s, %s, %s, %s, %s, NOW())""",
                        (inv_id, tenant_id, self.state.customer_id,
                         sub_id, stripe_inv_id, 490_000_000,
                         "usd", period_start, period_end),
                    )
                    self.state.subscription_invoice_id = stripe_inv_id

                    # Create CustomerCostAccumulator for economics
                    acc_id = str(uuid.uuid4())
                    period_start_date = date.today().replace(day=1).isoformat()
                    if date.today().month == 12:
                        period_end_date = date.today().replace(year=date.today().year + 1, month=1, day=1).isoformat()
                    else:
                        period_end_date = date.today().replace(month=date.today().month + 1, day=1).isoformat()
                    cur.execute(
                        """INSERT INTO ubb_customer_cost_accumulator
                           (id, created_at, updated_at, tenant_id, customer_id,
                            period_start, period_end, total_cost_micros, event_count)
                           VALUES (%s, NOW(), NOW(), %s, %s, %s, %s, %s, %s)""",
                        (acc_id, tenant_id, self.state.customer_id,
                         period_start_date, period_end_date, 50_000_000, 10),
                    )

                    conn.commit()

            self._log(
                "Seed subscription via DB",
                True,
                f"sub={stripe_sub_id}, invoice={stripe_inv_id}, cost_acc=50M micros"
            )
            return True

        except ImportError:
            self._log("Seed subscription via DB", False, "psycopg not installed. Run: pip install psycopg")
            return False
        except Exception as e:
            self._log("Seed subscription via DB", False, str(e))
            return False

    # =========================================================================
    # SUBSCRIPTIONS TESTS
    # =========================================================================

    def test_subs_get_subscription(self) -> bool:
        """Get subscription for customer."""
        resp = self._subs_get(f"/customers/{self.state.customer_id}/subscription")
        if resp.status_code != 200:
            self._log(
                "Subscriptions: get subscription", False,
                f"status={resp.status_code}, body={resp.text}"
            )
            return False

        body = resp.json()
        checks = [
            body.get("status") == "active",
            body.get("stripe_product_name") == "Pro Plan",
            body.get("amount_micros") == 490_000_000,
            body.get("currency") == "usd",
            body.get("interval") == "month",
        ]
        passed = all(checks)
        self._log(
            "Subscriptions: get subscription", passed,
            f"product={body.get('stripe_product_name')}, status={body.get('status')}, "
            f"amount={body.get('amount_micros')}"
        )
        return passed

    def test_subs_get_subscription_not_found(self) -> bool:
        """Non-existent customer returns 404."""
        fake_id = str(uuid.uuid4())
        resp = self._subs_get(f"/customers/{fake_id}/subscription")
        passed = resp.status_code == 404
        self._log(
            "Subscriptions: subscription 404 for unknown customer", passed,
            f"status={resp.status_code}"
        )
        return passed

    def test_subs_get_invoices(self) -> bool:
        """Get invoices for customer."""
        resp = self._subs_get(f"/customers/{self.state.customer_id}/invoices")
        if resp.status_code != 200:
            self._log(
                "Subscriptions: get invoices", False,
                f"status={resp.status_code}, body={resp.text}"
            )
            return False

        body = resp.json()
        data = body.get("data", [])
        passed = (
            len(data) >= 1
            and data[0].get("amount_paid_micros") == 490_000_000
            and body.get("has_more") is False
        )
        self._log(
            "Subscriptions: get invoices", passed,
            f"count={len(data)}, has_more={body.get('has_more')}"
        )
        return passed

    def test_subs_get_invoices_pagination(self) -> bool:
        """Invoices endpoint respects limit parameter."""
        resp = self._subs_get(f"/customers/{self.state.customer_id}/invoices?limit=1")
        if resp.status_code != 200:
            self._log(
                "Subscriptions: invoices pagination", False,
                f"status={resp.status_code}"
            )
            return False

        body = resp.json()
        passed = len(body.get("data", [])) <= 1
        self._log(
            "Subscriptions: invoices pagination", passed,
            f"count={len(body.get('data', []))}, limit=1"
        )
        return passed

    def test_subs_economics_summary(self) -> bool:
        """Get economics summary for current period."""
        today = date.today()
        period_start = today.replace(day=1).isoformat()
        if today.month == 12:
            period_end = today.replace(year=today.year + 1, month=1, day=1).isoformat()
        else:
            period_end = today.replace(month=today.month + 1, day=1).isoformat()

        resp = self._subs_get(
            f"/economics/summary?period_start={period_start}&period_end={period_end}"
        )
        if resp.status_code != 200:
            self._log(
                "Subscriptions: economics summary", False,
                f"status={resp.status_code}, body={resp.text}"
            )
            return False

        body = resp.json()
        passed = (
            body.get("total_customers", 0) >= 1
            and body.get("total_revenue_micros", 0) > 0
            and "total_cost_micros" in body
            and "total_margin_micros" in body
            and "avg_margin_percentage" in body
        )
        self._log(
            "Subscriptions: economics summary", passed,
            f"customers={body.get('total_customers')}, "
            f"revenue={body.get('total_revenue_micros')}, "
            f"cost={body.get('total_cost_micros')}, "
            f"margin={body.get('avg_margin_percentage')}%"
        )
        return passed

    def test_subs_economics_list(self) -> bool:
        """Get per-customer economics list."""
        today = date.today()
        period_start = today.replace(day=1).isoformat()
        if today.month == 12:
            period_end = today.replace(year=today.year + 1, month=1, day=1).isoformat()
        else:
            period_end = today.replace(month=today.month + 1, day=1).isoformat()

        resp = self._subs_get(
            f"/economics?period_start={period_start}&period_end={period_end}"
        )
        if resp.status_code != 200:
            self._log(
                "Subscriptions: economics list", False,
                f"status={resp.status_code}, body={resp.text}"
            )
            return False

        body = resp.json()
        customers = body.get("customers", [])
        summary = body.get("summary", {})

        # Find our customer in the list
        our_customer = next(
            (c for c in customers if c["customer_id"] == self.state.customer_id),
            None,
        )

        passed = (
            our_customer is not None
            and our_customer.get("plan") == "Pro Plan"
            and our_customer.get("subscription_revenue_micros") > 0
            and summary.get("total_revenue_micros", 0) > 0
        )
        self._log(
            "Subscriptions: economics list", passed,
            f"total_customers={len(customers)}, "
            f"our_revenue={our_customer.get('subscription_revenue_micros') if our_customer else 'N/A'}, "
            f"our_cost={our_customer.get('usage_cost_micros') if our_customer else 'N/A'}"
        )
        return passed

    def test_subs_customer_economics(self) -> bool:
        """Get economics for a specific customer."""
        today = date.today()
        period_start = today.replace(day=1).isoformat()
        if today.month == 12:
            period_end = today.replace(year=today.year + 1, month=1, day=1).isoformat()
        else:
            period_end = today.replace(month=today.month + 1, day=1).isoformat()

        resp = self._subs_get(
            f"/economics/{self.state.customer_id}"
            f"?period_start={period_start}&period_end={period_end}"
        )
        if resp.status_code != 200:
            self._log(
                "Subscriptions: customer economics", False,
                f"status={resp.status_code}, body={resp.text}"
            )
            return False

        body = resp.json()
        revenue = body.get("subscription_revenue_micros", 0)
        cost = body.get("usage_cost_micros", 0)
        margin = body.get("gross_margin_micros", 0)

        # Revenue should be 490M (from the seeded invoice)
        # Cost should be 50M (from the seeded accumulator)
        # Margin should be revenue - cost
        passed = (
            revenue == 490_000_000
            and cost == 50_000_000
            and margin == 440_000_000
            and body.get("plan") == "Pro Plan"
            and body.get("margin_percentage", 0) > 0
        )
        self._log(
            "Subscriptions: customer economics", passed,
            f"revenue={revenue}, cost={cost}, margin={margin}, "
            f"margin_pct={body.get('margin_percentage')}%"
        )
        return passed

    def test_subs_economics_default_period(self) -> bool:
        """Economics endpoints default to current period when params omitted."""
        resp = self._subs_get("/economics/summary")
        if resp.status_code != 200:
            self._log(
                "Subscriptions: economics default period", False,
                f"status={resp.status_code}"
            )
            return False

        body = resp.json()
        period = body.get("period", {})
        today = date.today()
        expected_start = today.replace(day=1).isoformat()

        passed = period.get("start") == expected_start
        self._log(
            "Subscriptions: economics default period", passed,
            f"period_start={period.get('start')} (expected {expected_start})"
        )
        return passed

    def test_subs_sync(self) -> bool:
        """Trigger subscription sync (may sync 0 if no Stripe connection)."""
        resp = self._subs_post("/sync")
        if resp.status_code != 200:
            self._log(
                "Subscriptions: trigger sync", False,
                f"status={resp.status_code}, body={resp.text}"
            )
            return False

        body = resp.json()
        passed = (
            "synced" in body
            and "skipped" in body
            and "errors" in body
        )
        self._log(
            "Subscriptions: trigger sync", passed,
            f"synced={body.get('synced')}, skipped={body.get('skipped')}, "
            f"errors={body.get('errors')}"
        )
        return passed

    # =========================================================================
    # REFERRALS HELPERS
    # =========================================================================

    def _ref_get(self, path: str) -> requests.Response:
        """GET against referrals API (/api/v1/referrals/...)."""
        base = self.config.base_url  # e.g. http://localhost:8000/api/v1
        ref_url = base.rsplit("/api/v1", 1)[0] + "/api/v1/referrals"
        return requests.get(f"{ref_url}{path}", headers=self._headers())

    def _ref_post(self, path: str, data: dict = None) -> requests.Response:
        """POST against referrals API."""
        base = self.config.base_url
        ref_url = base.rsplit("/api/v1", 1)[0] + "/api/v1/referrals"
        return requests.post(
            f"{ref_url}{path}",
            headers=self._headers(),
            json=data or {},
        )

    def _ref_patch(self, path: str, data: dict = None) -> requests.Response:
        """PATCH against referrals API."""
        base = self.config.base_url
        ref_url = base.rsplit("/api/v1", 1)[0] + "/api/v1/referrals"
        return requests.patch(
            f"{ref_url}{path}",
            headers=self._headers(),
            json=data or {},
        )

    def _ref_delete(self, path: str) -> requests.Response:
        """DELETE against referrals API."""
        base = self.config.base_url
        ref_url = base.rsplit("/api/v1", 1)[0] + "/api/v1/referrals"
        return requests.delete(f"{ref_url}{path}", headers=self._headers())

    def seed_referrals_via_db(self) -> bool:
        """Ensure the tenant has 'referrals' in products and create a second
        customer to act as the referred user."""
        try:
            import psycopg

            db_url = self.config.db_url or os.environ.get(
                "DATABASE_URL", "postgresql://heyotis:heyotis@localhost:5432/ubb"
            )

            with psycopg.connect(db_url) as conn:
                with conn.cursor() as cur:
                    # Look up tenant_id
                    cur.execute(
                        "SELECT tenant_id FROM ubb_customer WHERE id = %s",
                        (self.state.customer_id,)
                    )
                    row = cur.fetchone()
                    if not row:
                        self._log("Seed referrals", False, "Customer not found in DB")
                        return False
                    tenant_id = row[0]

                    # Ensure tenant has "referrals" in products
                    cur.execute(
                        "SELECT products FROM ubb_tenant WHERE id = %s",
                        (tenant_id,)
                    )
                    raw = cur.fetchone()[0]
                    if isinstance(raw, str):
                        products = json.loads(raw) if raw else []
                    elif isinstance(raw, list):
                        products = raw
                    else:
                        products = []
                    if "referrals" not in products:
                        products.append("referrals")
                        cur.execute(
                            "UPDATE ubb_tenant SET products = %s::jsonb, updated_at = NOW() WHERE id = %s",
                            (json.dumps(products), tenant_id),
                        )

                    # Create a second customer to be the "referred" user
                    referred_id = str(uuid.uuid4())
                    referred_ext = f"referred_{uuid.uuid4().hex[:8]}"
                    cur.execute(
                        """INSERT INTO ubb_customer
                           (id, created_at, updated_at, tenant_id, external_id,
                            stripe_customer_id, metadata, is_active, is_suspended)
                           VALUES (%s, NOW(), NOW(), %s, %s, %s, '{}'::jsonb, true, false)""",
                        (referred_id, tenant_id, referred_ext, "cus_ref_test"),
                    )
                    self.state.referred_customer_id = referred_id

                    # Create a wallet for the referred customer
                    wallet_id = str(uuid.uuid4())
                    cur.execute(
                        """INSERT INTO ubb_wallet
                           (id, created_at, updated_at, customer_id, balance_micros)
                           VALUES (%s, NOW(), NOW(), %s, 0)""",
                        (wallet_id, referred_id),
                    )

                    conn.commit()

            self.state.referrer_customer_id = self.state.customer_id
            self._log(
                "Seed referrals via DB", True,
                f"referred_customer={referred_id}, tenant products updated"
            )
            return True

        except ImportError:
            self._log("Seed referrals via DB", False, "psycopg not installed. Run: pip install psycopg")
            return False
        except Exception as e:
            self._log("Seed referrals via DB", False, str(e))
            return False

    # =========================================================================
    # REFERRALS TESTS
    # =========================================================================

    def test_ref_create_program(self) -> bool:
        """Create a referral program."""
        resp = self._ref_post("/program", {
            "reward_type": "revenue_share",
            "reward_value": 0.10,
            "attribution_window_days": 30,
            "reward_window_days": 365,
        })
        if resp.status_code != 200:
            self._log("Referrals: create program", False,
                      f"status={resp.status_code}, body={resp.text}")
            return False

        body = resp.json()
        passed = (
            body.get("reward_type") == "revenue_share"
            and body.get("status") == "active"
        )
        self._log("Referrals: create program", passed,
                  f"type={body.get('reward_type')}, status={body.get('status')}")
        return passed

    def test_ref_get_program(self) -> bool:
        """Get the active referral program."""
        resp = self._ref_get("/program")
        if resp.status_code != 200:
            self._log("Referrals: get program", False,
                      f"status={resp.status_code}")
            return False

        body = resp.json()
        passed = body.get("status") == "active"
        self._log("Referrals: get program", passed,
                  f"type={body.get('reward_type')}, status={body.get('status')}")
        return passed

    def test_ref_update_program(self) -> bool:
        """Update program reward value."""
        resp = self._ref_patch("/program", {"reward_value": 0.15})
        if resp.status_code != 200:
            self._log("Referrals: update program", False,
                      f"status={resp.status_code}, body={resp.text}")
            return False

        body = resp.json()
        passed = abs(body.get("reward_value", 0) - 0.15) < 0.001
        self._log("Referrals: update program", passed,
                  f"reward_value={body.get('reward_value')}")

        # Reset back to 0.10 for subsequent tests
        self._ref_patch("/program", {"reward_value": 0.10})
        return passed

    def test_ref_register_referrer(self) -> bool:
        """Register the primary customer as a referrer."""
        resp = self._ref_post("/referrers", {
            "customer_id": self.state.referrer_customer_id,
        })
        if resp.status_code != 200:
            self._log("Referrals: register referrer", False,
                      f"status={resp.status_code}, body={resp.text}")
            return False

        body = resp.json()
        self.state.referral_code = body.get("referral_code")
        passed = (
            body.get("referral_code", "").startswith("REF-")
            and body.get("is_active") is True
        )
        self._log("Referrals: register referrer", passed,
                  f"code={body.get('referral_code')}, active={body.get('is_active')}")
        return passed

    def test_ref_get_referrer(self) -> bool:
        """Get referrer by customer ID."""
        resp = self._ref_get(f"/referrers/{self.state.referrer_customer_id}")
        if resp.status_code != 200:
            self._log("Referrals: get referrer", False,
                      f"status={resp.status_code}")
            return False

        body = resp.json()
        passed = body.get("customer_id") == self.state.referrer_customer_id
        self._log("Referrals: get referrer", passed,
                  f"customer_id={body.get('customer_id')}")
        return passed

    def test_ref_list_referrers(self) -> bool:
        """List referrers."""
        resp = self._ref_get("/referrers")
        if resp.status_code != 200:
            self._log("Referrals: list referrers", False,
                      f"status={resp.status_code}")
            return False

        body = resp.json()
        passed = len(body.get("data", [])) >= 1
        self._log("Referrals: list referrers", passed,
                  f"count={len(body.get('data', []))}")
        return passed

    def test_ref_attribute(self) -> bool:
        """Attribute referred customer using referral code."""
        resp = self._ref_post("/attribute", {
            "customer_id": self.state.referred_customer_id,
            "code": self.state.referral_code,
        })
        if resp.status_code != 200:
            self._log("Referrals: attribute customer", False,
                      f"status={resp.status_code}, body={resp.text}")
            return False

        body = resp.json()
        self.state.referral_id = body.get("referral_id")
        passed = (
            body.get("status") == "active"
            and body.get("referred_customer_id") == self.state.referred_customer_id
        )
        self._log("Referrals: attribute customer", passed,
                  f"referral_id={body.get('referral_id')}, status={body.get('status')}")
        return passed

    def test_ref_duplicate_attribution_409(self) -> bool:
        """Duplicate attribution returns 409."""
        resp = self._ref_post("/attribute", {
            "customer_id": self.state.referred_customer_id,
            "code": self.state.referral_code,
        })
        passed = resp.status_code == 409
        self._log("Referrals: duplicate attribution 409", passed,
                  f"status={resp.status_code}")
        return passed

    def test_ref_get_earnings(self) -> bool:
        """Get referrer earnings (should be 0 since no usage from referred customer)."""
        resp = self._ref_get(f"/referrers/{self.state.referrer_customer_id}/earnings")
        if resp.status_code != 200:
            self._log("Referrals: get earnings", False,
                      f"status={resp.status_code}")
            return False

        body = resp.json()
        passed = (
            body.get("total_referrals") >= 1
            and body.get("active_referrals") >= 1
            and body.get("total_earned_micros") == 0  # No usage yet
        )
        self._log("Referrals: get earnings", passed,
                  f"referrals={body.get('total_referrals')}, "
                  f"earned={body.get('total_earned_micros')}")
        return passed

    def test_ref_get_referrals(self) -> bool:
        """Get referrer's referral list."""
        resp = self._ref_get(f"/referrers/{self.state.referrer_customer_id}/referrals")
        if resp.status_code != 200:
            self._log("Referrals: get referrals list", False,
                      f"status={resp.status_code}")
            return False

        body = resp.json()
        data = body.get("data", [])
        passed = (
            len(data) >= 1
            and data[0].get("status") == "active"
        )
        self._log("Referrals: get referrals list", passed,
                  f"count={len(data)}")
        return passed

    def test_ref_get_ledger(self) -> bool:
        """Get referral ledger (empty initially)."""
        resp = self._ref_get(f"/referrals/{self.state.referral_id}/ledger")
        if resp.status_code != 200:
            self._log("Referrals: get ledger", False,
                      f"status={resp.status_code}")
            return False

        body = resp.json()
        passed = isinstance(body.get("data"), list)
        self._log("Referrals: get ledger", passed,
                  f"entries={len(body.get('data', []))}")
        return passed

    def test_ref_analytics_summary(self) -> bool:
        """Get referral analytics summary."""
        resp = self._ref_get("/analytics/summary")
        if resp.status_code != 200:
            self._log("Referrals: analytics summary", False,
                      f"status={resp.status_code}")
            return False

        body = resp.json()
        passed = (
            body.get("total_referrers") >= 1
            and body.get("total_referrals") >= 1
        )
        self._log("Referrals: analytics summary", passed,
                  f"referrers={body.get('total_referrers')}, "
                  f"referrals={body.get('total_referrals')}")
        return passed

    def test_ref_analytics_earnings(self) -> bool:
        """Get referral earnings analytics."""
        resp = self._ref_get("/analytics/earnings")
        if resp.status_code != 200:
            self._log("Referrals: analytics earnings", False,
                      f"status={resp.status_code}")
            return False

        body = resp.json()
        passed = isinstance(body.get("referrers"), list)
        self._log("Referrals: analytics earnings", passed,
                  f"referrers_count={len(body.get('referrers', []))}")
        return passed

    # =========================================================================
    # RUN ALL
    # =========================================================================

    def run_all(self, skip_stripe_webhook: bool = False) -> bool:
        print("=" * 70)
        print("UBB Integration Test Suite (Detailed)")
        print("=" * 70)
        print(f"Base URL:            {self.config.base_url}")
        print(f"Stripe Customer ID:  {self.config.stripe_customer_id}")
        print(f"Skip Stripe Webhook: {skip_stripe_webhook}")
        print(f"Test Subscriptions:  {self.config.test_subscriptions}")
        print(f"Test Referrals:      {self.config.test_referrals}")
        print("=" * 70)
        print()

        # ---- Setup ----
        print("--- Setup ---")
        if not self.test_health():
            print("\n[FATAL] Server not reachable. Aborting.")
            return False

        if not self.test_create_customer():
            print("\n[FATAL] Could not create customer. Aborting.")
            return False

        # ---- Initial State ----
        print("\n--- Initial State ---")
        self.test_initial_balance_is_zero()
        self.test_initial_transactions_empty()

        # ---- Top-Up Flow ----
        print("\n--- Top-Up Flow ---")
        checkout_url = self.test_create_topup_checkout()

        if skip_stripe_webhook:
            print("\n[INFO] Skipping Stripe webhook, funding wallet directly...")
            if not self.fund_wallet_directly():
                print("\n[WARN] Could not fund wallet directly. Withdrawal tests may fail.")
            else:
                self.test_balance_after_topup()
                self.test_transaction_after_topup()
        elif checkout_url:
            print("\n" + "=" * 70)
            print("MANUAL STEP REQUIRED")
            print("=" * 70)
            print(f"\nOpen this URL in your browser and complete payment:")
            print(f"\n  {checkout_url}\n")
            print("Use test card: 4242 4242 4242 4242")
            print("Any future expiry, any CVC")
            print("\nPress Enter after completing payment...")
            input()

            print("Waiting for webhook to process...")
            time.sleep(3)

            self.state.expected_balance = self.state.top_up_amount
            self.state.transaction_count += 1
            self.test_balance_after_topup()
            self.test_transaction_after_topup()

        # ---- Pre-Check ----
        print("\n--- Pre-Check ---")
        self.test_precheck_allowed()

        # ---- Usage Recording ----
        print("\n--- Usage Recording ---")
        self.test_record_usage()
        self.test_usage_transaction_recorded()
        self.test_usage_idempotency()
        self.test_get_usage_history()

        # ---- Withdrawals ----
        print("\n--- Withdrawals ---")
        self.test_withdraw()
        self.test_withdraw_transaction_recorded()
        self.test_withdraw_idempotency()
        self.test_withdraw_insufficient_balance()

        # ---- Refunds ----
        print("\n--- Refunds ---")
        self.test_refund()
        self.test_refund_transaction_recorded()
        self.test_double_refund_fails()

        # ---- Final Verification ----
        print("\n--- Final Verification ---")
        self.test_final_balance_correct()
        self.test_transaction_count()
        self.test_transaction_types_present()

        # ---- Auto Top-Up ----
        print("\n--- Auto Top-Up Config ---")
        self.test_configure_auto_topup()

        # ---- Tenant Billing ----
        print("\n--- Tenant Billing ---")
        self.test_tenant_billing_periods()
        self.test_tenant_invoices()
        self.test_usage_analytics()
        self.test_revenue_analytics()

        # ---- Subscriptions ----
        if self.config.test_subscriptions:
            print("\n--- Subscriptions: Setup ---")
            if not self.seed_subscription_via_db():
                print("\n[WARN] Could not seed subscription data. Skipping subscriptions tests.")
            else:
                print("\n--- Subscriptions: Subscription Data ---")
                self.test_subs_get_subscription()
                self.test_subs_get_subscription_not_found()

                print("\n--- Subscriptions: Invoices ---")
                self.test_subs_get_invoices()
                self.test_subs_get_invoices_pagination()

                print("\n--- Subscriptions: Unit Economics ---")
                self.test_subs_customer_economics()
                self.test_subs_economics_summary()
                self.test_subs_economics_list()
                self.test_subs_economics_default_period()

                print("\n--- Subscriptions: Sync ---")
                self.test_subs_sync()
        else:
            print("\n--- Subscriptions ---")
            print("[SKIP] Use --test-subscriptions to run subscriptions tests")

        # ---- Referrals ----
        if self.config.test_referrals:
            print("\n--- Referrals: Setup ---")
            if not self.seed_referrals_via_db():
                print("\n[WARN] Could not seed referrals data. Skipping referrals tests.")
            else:
                print("\n--- Referrals: Program Management ---")
                self.test_ref_create_program()
                self.test_ref_get_program()
                self.test_ref_update_program()

                print("\n--- Referrals: Referrer Management ---")
                self.test_ref_register_referrer()
                self.test_ref_get_referrer()
                self.test_ref_list_referrers()

                print("\n--- Referrals: Attribution ---")
                self.test_ref_attribute()
                self.test_ref_duplicate_attribution_409()

                print("\n--- Referrals: Rewards ---")
                self.test_ref_get_earnings()
                self.test_ref_get_referrals()
                self.test_ref_get_ledger()

                print("\n--- Referrals: Analytics ---")
                self.test_ref_analytics_summary()
                self.test_ref_analytics_earnings()
        else:
            print("\n--- Referrals ---")
            print("[SKIP] Use --test-referrals to run referrals tests")

        # ---- Summary ----
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        passed = sum(1 for r in self.results if r["passed"])
        failed = sum(1 for r in self.results if not r["passed"])
        total = len(self.results)

        print(f"Passed: {passed}/{total}")
        print(f"Failed: {failed}/{total}")

        if failed > 0:
            print("\n--- Failed Tests ---")
            for r in self.results:
                if not r["passed"]:
                    print(f"  [FAIL] {r['test']}")
                    print(f"         {r['details']}")

        print("\n--- Balance Ledger ---")
        print(f"  Initial:    0 micros")
        print(f"  + Top-up:   +{self.state.top_up_amount} micros")
        print(f"  - Usage 1:  -{self.state.usage_cost_1} micros")
        print(f"  - Usage 2:  -{self.state.usage_cost_2} micros")
        print(f"  - Withdraw: -{self.state.withdraw_amount} micros")
        print(f"  - Withdraw: -{self.state.withdraw_amount} micros (idempotency test)")
        print(f"  + Refund:   +{self.state.usage_cost_1} micros")
        print(f"  = Expected: {self.state.expected_balance} micros")
        print(f"  = Actual:   {self._get_balance()} micros")

        return failed == 0


def main():
    parser = argparse.ArgumentParser(description="UBB Integration Test Suite")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("UBB_BASE_URL", "http://localhost:8000/api/v1"),
        help="Base URL for API",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("UBB_API_KEY"),
        help="UBB API key",
    )
    parser.add_argument(
        "--stripe-customer-id",
        default=os.environ.get("STRIPE_CUSTOMER_ID"),
        help="Stripe customer ID on connected account",
    )
    parser.add_argument(
        "--stripe-connected-account",
        default=os.environ.get("STRIPE_CONNECTED_ACCOUNT_ID"),
        help="Stripe connected account ID (optional)",
    )
    parser.add_argument(
        "--db-url",
        default=os.environ.get("DATABASE_URL"),
        help="Database URL for direct DB access (optional)",
    )
    parser.add_argument(
        "--skip-stripe-webhook",
        action="store_true",
        help="Skip Stripe checkout, fund wallet directly via DB",
    )
    parser.add_argument(
        "--test-subscriptions",
        action="store_true",
        help="Include subscriptions product tests (requires tenant with subscriptions product)",
    )
    parser.add_argument(
        "--test-referrals",
        action="store_true",
        help="Include referrals product tests (seeds program + attribution via API)",
    )

    args = parser.parse_args()

    if not args.api_key:
        print("Error: --api-key or UBB_API_KEY required")
        sys.exit(1)

    if not args.stripe_customer_id:
        print("Error: --stripe-customer-id or STRIPE_CUSTOMER_ID required")
        sys.exit(1)

    config = TestConfig(
        base_url=args.base_url,
        api_key=args.api_key,
        stripe_customer_id=args.stripe_customer_id,
        stripe_connected_account_id=args.stripe_connected_account,
        db_url=args.db_url,
        test_subscriptions=args.test_subscriptions,
        test_referrals=args.test_referrals,
    )

    runner = IntegrationTestRunner(config)
    success = runner.run_all(skip_stripe_webhook=args.skip_stripe_webhook)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
