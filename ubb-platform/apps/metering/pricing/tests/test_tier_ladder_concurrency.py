"""Fix 2: Threaded concurrency test for lock_and_advance.

Two threads call record_usage with DIFFERENT idempotency keys against the SAME
graduated lineage simultaneously.  The SELECT FOR UPDATE row-lock inside
lock_and_advance must serialise them, so their provenance prior_units are
exactly {0, N} — never {0, 0} (no double-zero collision).

Uses TransactionTestCase (NOT @pytest.mark.django_db) so setup data is
committed before worker threads start and workers can see each other's
transactions through real Postgres row locking — the same harness as
apps/billing/tests/test_concurrency_races.py.

process_single_event.delay is patched at class level to prevent Celery broker
connections from worker threads (on_commit fires after the transaction commits
inside the worker thread's connection, which has no broker reachability in test).

Run 3 times for stability.
"""
import threading
from unittest import mock

from django.db import connection
from django.test import TransactionTestCase

from apps.metering.pricing.models import PricingPeriodCounter, Rate
from apps.metering.pricing.tests._helpers import rate_in_default_book
from apps.metering.usage.models import UsageEvent
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant

TIERS = [
    {"up_to": 100, "rate_per_unit_micros": 10, "unit_quantity": 1},
    {"up_to": None, "rate_per_unit_micros": 5, "unit_quantity": 1},
]
N = 60  # units per event; two events → total 120


def _setup():
    tenant = Tenant.objects.create(name="RACE_TIER", products=["metering", "billing"])
    customer = Customer.objects.create(tenant=tenant, external_id="race_c1")
    card = rate_in_default_book(
        tenant, card_type="price", metric_name="tok",
        pricing_model="graduated", tiers=TIERS,
    )
    return tenant, customer, card


class ConcurrentTierLadderRace(TransactionTestCase):
    """Two concurrent record_usage calls against the same graduated lineage
    must serialise via SELECT FOR UPDATE so prior_units are {0, N} not {0, 0}.

    The test runs 3 times for stability.
    """

    def _run_once(self, tenant, customer, card, run_index):
        barrier = threading.Barrier(2)
        results = {}
        errors = []

        def worker(idx):
            try:
                barrier.wait()
                result = UsageService.record_usage(
                    tenant, customer,
                    request_id=f"r{run_index}_{idx}",
                    idempotency_key=f"k{run_index}_{idx}",
                    usage_metrics={"tok": N},
                )
                results[idx] = result
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))
            finally:
                connection.close()

        # Patch process_single_event.delay before threads start — mock is
        # module-level so both threads inherit it without needing per-thread setup.
        with mock.patch(
            "apps.platform.events.tasks.process_single_event.delay"
        ):
            threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(errors, [], f"workers raised unexpected exceptions: {errors}")

        # Both events recorded.
        self.assertEqual(len(results), 2)

        # Retrieve provenance prior_units for each event.
        priors = set()
        for res in results.values():
            event = UsageEvent.objects.get(id=res["event_id"])
            price_entries = [
                m for m in (event.pricing_provenance or {}).get("metrics", [])
                if m.get("card_type") == "price"
            ]
            self.assertEqual(len(price_entries), 1,
                             "expected exactly one price provenance entry")
            breakdown = price_entries[0]["tier_breakdown"]
            priors.add(breakdown["prior_units"])

        # The row lock must serialise: one event saw prior=0, the other saw prior=N.
        self.assertEqual(priors, {0, N},
                         f"expected prior_units {{0, {N}}}, got {priors} — "
                         "ladder was not serialised (double-zero race)")

        # Counter advanced by 2N total.
        counter = PricingPeriodCounter.objects.get(lineage_id=card.lineage_id)
        self.assertEqual(counter.units_total, 2 * N,
                         f"expected units_total={2*N}, got {counter.units_total}")

        # Σ billed == compute_cumulative(2N): telescoping invariant.
        total_billed = sum(
            res["billed_cost_micros"] for res in results.values()
        )
        expected_billed = card.compute_cumulative(2 * N)
        self.assertEqual(total_billed, expected_billed,
                         f"expected Σbilled={expected_billed}, got {total_billed}")

    def test_concurrent_record_usage_ladder_serialised_3x(self):
        """Run 3 times for stability."""
        for run_index in range(3):
            # Each run uses a fresh tenant/customer/card so events don't bleed.
            tenant, customer, card = _setup()
            self._run_once(tenant, customer, card, run_index)
