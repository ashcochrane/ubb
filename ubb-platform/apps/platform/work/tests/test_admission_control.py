"""Admission control lives in the kernel and answers for every tenant
(#462, slice 6 §1, §6; #154 §3.4; #141 §4.5; TD claim 8).

`work/admission.py` is the one mechanism of the family: a bound on how fast
NEW top-level work may enter, per seat, in a fixed window of one minute —
and the customer's standing beside it, because a suspended or closed
customer is a kernel fact a tenant that does not bill through UBB is still
owed. Until this ticket the bound ran INSIDE billing's money-shaped verdict,
which the composition layer asks only where the tenant has a wallet — so a
tenant without one had no bound and no standing check at the start (§6, the
bank's missed finding).

What this module proves at the service seam: exactly the bound is admitted
in one window and the next start is refused with the retry information;
contained work consumes none of it; the window is keyed per seat; a refused
start does not count; a tenant declaring no bound never touches the store;
the store being unavailable admits (the posture the old throttle had); the
standing refusals name the registry's words for the seat AND for the
business funding a pooled seat; and the rate answers before the standing —
the one observable reordering §6 states and accepts. The routes' cases,
including that a replay, a usage report and a close consume nothing, are
`api/v1/tests/test_admission_control_runs_for_every_start.py`.

⚠ THE WINDOW IS REAL: the counter lives on the Django cache (Redis, DB 15
under the suite) exactly as the old throttle's did, keyed on the customer's
id, so no case here clears the store — a fresh customer is a fresh window.
"""
import ast
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.platform.customers.models import (
    ACCOUNT_TYPE_BUSINESS, ACCOUNT_TYPE_SEAT, CUSTOMER_STATUS_CLOSED,
    CUSTOMER_STATUS_SUSPENDED, Customer)
from apps.platform.tenants.models import Tenant
from apps.platform.work import admission, services
from apps.platform.work.admission import AdmissionRefused
from core.vocabulary import (
    AFFORDABILITY_REASON_ACCOUNT_CLOSED,
    AFFORDABILITY_REASON_CUSTOMER_STOPPED,
    AFFORDABILITY_REASON_PARENT_TASK_NOT_ACTIVE,
    AFFORDABILITY_REASON_RATE_LIMIT_EXCEEDED,
    AFFORDABILITY_REASON_SUBTASK_DEPTH_EXCEEDED)

#: Small enough that a case reaches it in a handful of calls, and not one —
#: one would make "the bound" and "the first start" the same number.
THE_BOUND = 3


class AdmissionTestBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="T", max_task_starts_per_minute=THE_BOUND)
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1")

    def admit(self, customer=None, *, contained=False):
        return admission.admit(self.tenant, customer or self.customer,
                               contained=contained)

    def refusal(self, customer=None, *, contained=False):
        with self.assertRaises(AdmissionRefused) as caught:
            self.admit(customer, contained=contained)
        return caught.exception

    def counted(self, customer=None):
        starts_key, _ = admission.window_keys((customer or self.customer).id)
        return cache.get(starts_key, 0)


class TheBoundTest(AdmissionTestBase):
    def test_exactly_the_bound_is_admitted_and_the_next_start_is_refused(self):
        before = timezone.now()
        for _ in range(THE_BOUND):
            self.admit()
        refused = self.refusal()
        self.assertEqual(refused.reason, AFFORDABILITY_REASON_RATE_LIMIT_EXCEEDED)
        window = refused.window
        self.assertEqual(window.limit, THE_BOUND)
        self.assertEqual(window.remaining, 0)
        # The retry information: the window ends one window's length after
        # the first start — so after `before`, and no later than one length
        # after now — and the seconds to wait are whole and at least one: a
        # `Retry-After` of zero tells a caller to try again now.
        self.assertGreater(window.ends_at, before)
        self.assertLessEqual(
            window.ends_at,
            timezone.now() + timedelta(seconds=admission.WINDOW_SECONDS))
        self.assertIsInstance(window.retry_after_seconds, int)
        self.assertGreaterEqual(window.retry_after_seconds, 1)
        self.assertLessEqual(window.retry_after_seconds, admission.WINDOW_SECONDS)

    def test_an_admitted_start_reports_what_is_left(self):
        left = [self.admit().remaining for _ in range(THE_BOUND)]
        self.assertEqual(left, [THE_BOUND - 1, THE_BOUND - 2, 0])

    def test_a_refused_start_does_not_count(self):
        """As the old throttle: the count is of starts the bound admitted,
        so a caller hammering a full window is not pushed further into it."""
        for _ in range(THE_BOUND):
            self.admit()
        self.refusal()
        self.refusal()
        self.assertEqual(self.counted(), THE_BOUND)

    def test_contained_work_consumes_none_of_the_allowance(self):
        """Contained work started inside admitted work is that work
        completing, not new work entering (#154 §3.4): at a full window it
        is admitted, and it moves nothing."""
        for _ in range(THE_BOUND):
            self.admit()
        self.assertIsNone(self.admit(contained=True))
        self.assertEqual(self.counted(), THE_BOUND)
        # And the next top-level start is still refused — the contained one
        # neither consumed nor reset anything.
        self.refusal()

    def test_the_window_is_keyed_per_seat(self):
        another = Customer.objects.create(tenant=self.tenant, external_id="c2")
        for _ in range(THE_BOUND):
            self.admit()
        self.refusal()
        self.assertEqual(self.admit(another).remaining, THE_BOUND - 1)
        self.assertEqual(self.counted(another), 1)

    def test_the_window_lives_in_the_store_and_a_fresh_one_admits_again(self):
        """Backing off past the window is the store forgetting the keys; a
        case cannot wait a minute, so it forgets them the way expiry would."""
        for _ in range(THE_BOUND):
            self.admit()
        self.refusal()
        cache.delete_many(admission.window_keys(self.customer.id))
        self.assertEqual(self.admit().remaining, THE_BOUND - 1)

    def test_a_tenant_declaring_no_bound_is_never_refused_and_never_touches_the_store(self):
        self.tenant.max_task_starts_per_minute = None
        self.tenant.save(update_fields=["max_task_starts_per_minute"])
        with patch.object(admission, "cache") as store:
            for _ in range(THE_BOUND + 2):
                self.assertIsNone(self.admit())
        store.get.assert_not_called()
        store.incr.assert_not_called()
        store.set.assert_not_called()
        store.add.assert_not_called()

    def test_the_store_being_unavailable_admits_the_start(self):
        """Fail open, as the old throttle did: a Redis outage must not stop
        work entering — the money is still guarded by the durable checks
        that follow. Loudly, though: the degraded path logs."""
        with patch.object(admission, "cache") as store:
            store.get.side_effect = ConnectionError("the store is away")
            with self.assertLogs("apps.platform.work.admission", level="WARNING") as logged:
                self.assertIsNone(self.admit())
        self.assertTrue(any("admission_store_unavailable" in line
                            for line in logged.output), logged.output)


class TheStandingTest(AdmissionTestBase):
    def test_a_closed_customer_is_refused_by_name(self):
        self.customer.status = CUSTOMER_STATUS_CLOSED
        self.customer.save(update_fields=["status"])
        refused = self.refusal()
        self.assertEqual(refused.reason, AFFORDABILITY_REASON_ACCOUNT_CLOSED)
        self.assertIsNone(refused.window)

    def test_a_suspended_customer_is_refused_as_stopped(self):
        """A suspension is the durable form of the customer-wide stop, and
        the kernel says so in the registry's word for a stop in force —
        it does not know, and must not ask billing, which line opened it."""
        self.customer.status = CUSTOMER_STATUS_SUSPENDED
        self.customer.save(update_fields=["status"])
        refused = self.refusal()
        self.assertEqual(refused.reason, AFFORDABILITY_REASON_CUSTOMER_STOPPED)
        self.assertIsNone(refused.window)

    def test_a_suspended_customers_contained_start_is_refused_too(self):
        """Only the RATE is scoped to top-level starts; standing is asked of
        every start, as the money verdict always asked it."""
        self.customer.status = CUSTOMER_STATUS_SUSPENDED
        self.customer.save(update_fields=["status"])
        refused = self.refusal(contained=True)
        self.assertEqual(refused.reason, AFFORDABILITY_REASON_CUSTOMER_STOPPED)

    def test_a_pooled_seat_under_a_suspended_business_is_refused(self):
        business = Customer.objects.create(
            tenant=self.tenant, external_id="biz",
            account_type=ACCOUNT_TYPE_BUSINESS, billing_topology="pooled",
            status=CUSTOMER_STATUS_SUSPENDED)
        seat = Customer.objects.create(
            tenant=self.tenant, external_id="s1",
            account_type=ACCOUNT_TYPE_SEAT, parent=business)
        refused = self.refusal(seat)
        self.assertEqual(refused.reason, AFFORDABILITY_REASON_CUSTOMER_STOPPED)
        self.assertIn("business", str(refused))

    def test_an_allocated_seat_is_judged_on_its_own_standing(self):
        """The business is consulted only where it funds the seat — the same
        rule the money verdict's owner resolution follows."""
        business = Customer.objects.create(
            tenant=self.tenant, external_id="biz",
            account_type=ACCOUNT_TYPE_BUSINESS, billing_topology="allocated",
            status=CUSTOMER_STATUS_SUSPENDED)
        seat = Customer.objects.create(
            tenant=self.tenant, external_id="s1",
            account_type=ACCOUNT_TYPE_SEAT, parent=business)
        self.assertEqual(self.admit(seat).remaining, THE_BOUND - 1)

    def test_the_rate_answers_before_the_standing(self):
        """The one observable reordering, stated and accepted (§6): a
        customer both stopped and over the rate is told about the rate
        first — the answer that changes on its own within a minute — and a
        caller that backs off then meets the stop. Its consequence, that a
        start refused for standing has still entered the window, is what
        the first refusal here shows."""
        self.tenant.max_task_starts_per_minute = 1
        self.tenant.save(update_fields=["max_task_starts_per_minute"])
        self.customer.status = CUSTOMER_STATUS_SUSPENDED
        self.customer.save(update_fields=["status"])
        first = self.refusal()
        self.assertEqual(first.reason, AFFORDABILITY_REASON_CUSTOMER_STOPPED)
        self.assertEqual(self.counted(), 1)
        second = self.refusal()
        self.assertEqual(second.reason, AFFORDABILITY_REASON_RATE_LIMIT_EXCEEDED)
        cache.delete_many(admission.window_keys(self.customer.id))
        backed_off = self.refusal()
        self.assertEqual(backed_off.reason, AFFORDABILITY_REASON_CUSTOMER_STOPPED)


class TheWordsAreTheRegistrysTest(TestCase):
    """The four refusal values the kernel produces are BOUND from
    `core.vocabulary`, read off the assignments rather than compared by
    value — an equal literal would satisfy a value comparison while being
    exactly the second spelling ADR-0006 §2 forbids."""

    def names_imported_from_the_vocabulary(self, module):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        return {alias.name for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
                and node.module == "core.vocabulary"
                for alias in node.names}

    def test_the_admission_module_binds_its_three_words_from_the_vocabulary(self):
        imported = self.names_imported_from_the_vocabulary(admission)
        self.assertTrue({"AFFORDABILITY_REASON_RATE_LIMIT_EXCEEDED",
                         "AFFORDABILITY_REASON_ACCOUNT_CLOSED",
                         "AFFORDABILITY_REASON_CUSTOMER_STOPPED"} <= imported,
                        imported)

    def test_the_start_shape_refusals_are_bound_from_the_vocabulary(self):
        imported = self.names_imported_from_the_vocabulary(services)
        self.assertTrue({"AFFORDABILITY_REASON_PARENT_TASK_NOT_ACTIVE",
                         "AFFORDABILITY_REASON_SUBTASK_DEPTH_EXCEEDED"} <= imported,
                        imported)
        self.assertEqual(services.PARENT_NOT_ACTIVE,
                         AFFORDABILITY_REASON_PARENT_TASK_NOT_ACTIVE)
        self.assertEqual(services.SUBTASK_DEPTH_EXCEEDED,
                         AFFORDABILITY_REASON_SUBTASK_DEPTH_EXCEEDED)
