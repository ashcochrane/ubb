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

Prerequisites:
- Local server running: python manage.py runserver
- Stripe CLI listening: stripe listen --forward-to localhost:8000/api/v1/webhooks/stripe
- Valid Stripe customer ID on the tenant's connected account

Usage:
    python scripts/integration_test.py --api-key <ubb_api_key> --stripe-customer-id <cus_xxx>

    # Skip Stripe checkout (funds wallet directly via DB):
    python scripts/integration_test.py --api-key <ubb_api_key> --stripe-customer-id <cus_xxx> --skip-stripe-webhook
"""

import argparse
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import requests


@dataclass
class TestConfig:
    base_url: str
    api_key: str
    stripe_customer_id: str
    stripe_connected_account_id: Optional[str] = None
    db_url: Optional[str] = None


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
    # RUN ALL
    # =========================================================================

    def run_all(self, skip_stripe_webhook: bool = False) -> bool:
        print("=" * 70)
        print("UBB Integration Test Suite (Detailed)")
        print("=" * 70)
        print(f"Base URL:            {self.config.base_url}")
        print(f"Stripe Customer ID:  {self.config.stripe_customer_id}")
        print(f"Skip Stripe Webhook: {skip_stripe_webhook}")
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
    )

    runner = IntegrationTestRunner(config)
    success = runner.run_all(skip_stripe_webhook=args.skip_stripe_webhook)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
