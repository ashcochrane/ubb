"""Admission control runs for every start, through the routes (#462, slice 6
§1, §6; #154 §3.4; #141 §4.5; TD claim 8).

THE CLAIM, IN THE SPEC'S WORDS: the throttle refuses a NEW TOP-LEVEL start
over the window with the retry information and the scope key; a replay, a
contained start, a usage report and a close consume none of it; a tenant
without a wallet regime is throttled and its suspended customer is refused;
the affordability read never increments the window (that last one is
`gating/tests/test_risk_service.py`'s, at the verdict it is about).

THE TWO POSTURES ARE THE SAME CASES RUN TWICE, and that is the point. The
per-minute bound and the standing check ran inside billing's money-shaped
verdict until #462, and the composition layer asks that verdict only where
the tenant has a wallet — so a tenant that does not bill through UBB had
neither (§6, the bank's missed finding). Every case in the mixin below runs
once for that tenant and once for a prepaid one, and the two must answer
alike: the bound is the kernel's now, asked for every start.

WHY THIS MODULE IS THE COMPOSITION LAYER'S. The claim spans the start, the
close, the recording route and the money verdict — routes in three products'
mounts — and no product's test may drive the others (ADR-001, and the
boundary `apps/billing/gating/tests/test_patrol_pins.py` names).

⚠ THE SUSPENDED CUSTOMER'S REFUSAL IS THE KERNEL'S FOR BOTH POSTURES, AND
THE WORD NAMES THE LINE WHERE THERE IS ONE TO NAME. A suspension is the
durable form of the customer-wide stop, and the kernel refuses it in the
registry's word for a stop in force — `customer_stopped` — because it does
not know, and must not ask billing, which line opened it. For a tenant with
a wallet the composition layer lets the money verdict name the line on that
refusal (the pool's word where the pool alone holds, else the wallet's —
#459's cases hold both through this route), so the two postures answer with
different words for one refusal made at one point: `STANDING_WORD_FOR_A_
SUSPENSION` below is each posture's, and the reordering case is what pins
that the refusal itself comes before the money.

⚠ THE WINDOW IS REAL — the counter lives on the Django cache under the
customer's id, as the old throttle's did — so every case works on its own
fresh customer and none clears the store.
"""
import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from api.v1.tests._helpers import SOLD_PER_EVENT, a_tenant_selling_whole_work
from apps.platform.customers.models import (
    CUSTOMER_STATUS_CLOSED, CUSTOMER_STATUS_SUSPENDED)
from apps.platform.event_types.tests._helpers import (
    DECLARED, declares_a_caller_supplied_cost)
from apps.platform.work import admission
from apps.platform.work.models import Task
from core.vocabulary import (
    AFFORDABILITY_REASON_ACCOUNT_CLOSED,
    AFFORDABILITY_REASON_CUSTOMER_STOPPED,
    AFFORDABILITY_REASON_INSUFFICIENT_FUNDS,
    TASK_OUTCOME_DELIVERED)

#: Two: enough that "the window is full" and "the first start" are
#: different moments, small enough that a case fills it in two calls.
THE_BOUND = 2

#: Where the outbox doorbell rings; patched so executed on-commit callbacks
#: never reach Celery (the release module's arrangement).
DOORBELL = "apps.platform.events.tasks.process_single_event"


class AdmissionRouteCases:
    """The cases, run under each posture by the two classes at the foot."""

    PRODUCTS = ("metering",)
    BILLING_MODE = None
    BALANCE_MICROS = None
    #: The word a suspended customer's start is refused in under this
    #: posture: the kernel's, where no line can be named.
    STANDING_WORD_FOR_A_SUSPENSION = AFFORDABILITY_REASON_CUSTOMER_STOPPED

    def setUp(self):
        self.client = Client()
        self.fixture = a_tenant_selling_whole_work(
            products=self.PRODUCTS, billing_mode=self.BILLING_MODE,
            balance_micros=self.BALANCE_MICROS)
        self.tenant = self.fixture.tenant
        self.customer = self.fixture.customer
        self.tenant.max_task_starts_per_minute = THE_BOUND
        self.tenant.save(update_fields=["max_task_starts_per_minute"])
        declares_a_caller_supplied_cost(self.tenant, DECLARED)

    def _auth(self):
        return self.fixture.auth()

    def _start(self, **body):
        body.setdefault("task_type", SOLD_PER_EVENT)
        return self.client.post(
            "/api/v1/tasks", data=json.dumps(self.fixture.start_body(**body)),
            content_type="application/json", **self._auth())

    def _admitted(self, **body):
        response = self._start(**body)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _fill_the_window(self):
        return [self._admitted() for _ in range(THE_BOUND)]

    def _refused_by_the_rate(self, **body):
        response = self._start(**body)
        self.assertEqual(response.status_code, 429, response.content)
        self.assertEqual(response.json()["code"], "rate_limit_exceeded")
        return response

    def _refused_for_standing(self, reason, **body):
        response = self._start(**body)
        self.assertEqual(response.status_code, 409, response.content)
        body = response.json()
        self.assertEqual(body["code"], "task_start_refused")
        self.assertEqual(body["reason"], reason)
        return body

    def _report_usage(self, **extra):
        data = {"customer_id": str(self.customer.id),
                "idempotency_key": f"idem-{uuid.uuid4()}",
                "event_type": DECLARED, "provider_cost_micros": 1_000}
        data.update(extra)
        with patch(DOORBELL), self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                "/api/v1/metering/usage", data=json.dumps(data),
                content_type="application/json", **self._auth())

    def _close(self, task_id):
        return self.client.post(
            f"/api/v1/tasks/{task_id}/close",
            data=json.dumps({"outcome": TASK_OUTCOME_DELIVERED}),
            content_type="application/json", **self._auth())

    def counted(self):
        starts_key, _ = admission.window_keys(self.customer.id)
        return cache.get(starts_key, 0)

    def _suspend(self):
        self.customer.status = CUSTOMER_STATUS_SUSPENDED
        self.customer.save(update_fields=["status"])

    # --- the rate, and what does not consume it --------------------------

    def test_a_new_top_level_start_over_the_window_is_a_429_with_the_retry_information(self):
        before = timezone.now()
        self._fill_the_window()
        response = self._refused_by_the_rate()
        body = response.json()
        # `Retry-After` is the header the dialect promises on every 429,
        # whole seconds, at least one and at most the window.
        self.assertTrue(response.has_header("Retry-After"))
        self.assertTrue(1 <= int(response["Retry-After"]) <= admission.WINDOW_SECONDS)
        self.assertEqual(body["limit"], THE_BOUND)
        self.assertEqual(body["remaining"], 0)
        reset = datetime.fromisoformat(body["window_reset_at"])
        self.assertIsNotNone(reset.tzinfo)
        self.assertGreater(reset, before)
        self.assertLessEqual(
            reset, timezone.now() + timedelta(seconds=admission.WINDOW_SECONDS))
        # The scope key, pinned and exposed: per seat, never per tenant or
        # per billing owner, and never varying between endpoints.
        self.assertEqual(body["scope"], admission.SCOPE)
        # A refused start created nothing.
        self.assertEqual(Task.objects.filter(customer=self.customer).count(),
                         THE_BOUND)

    def test_a_replay_consumes_none_of_the_allowance(self):
        the_claim = f"attempt-{uuid.uuid4()}"
        first = self._admitted(idempotency_key=the_claim)
        for _ in range(THE_BOUND - 1):
            self._admitted()
        self._refused_by_the_rate()
        replayed = self._admitted(idempotency_key=the_claim)
        self.assertTrue(replayed["replayed"])
        self.assertEqual(replayed["task_id"], first["task_id"])
        self.assertEqual(self.counted(), THE_BOUND)
        self._refused_by_the_rate()

    def test_a_contained_start_consumes_none_of_the_allowance(self):
        first, *_ = self._fill_the_window()
        self._refused_by_the_rate()
        contained = self._admitted(parent_task_id=first["task_id"])
        self.assertEqual(contained["parent_task_id"], first["task_id"])
        self.assertEqual(self.counted(), THE_BOUND)
        self._refused_by_the_rate()

    def test_a_usage_report_is_always_accepted(self):
        """The one rule (#150 §1.3): a usage report is evidence of work that
        already happened, and admission control cannot refuse it — so a
        full window neither refuses nor counts one."""
        self._fill_the_window()
        self._refused_by_the_rate()
        response = self._report_usage()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.counted(), THE_BOUND)
        self._refused_by_the_rate()

    def test_a_close_is_never_subject_to_it(self):
        """The close half of Pin 7 (§22): work entering is bounded, work
        ending never is."""
        first, *_ = self._fill_the_window()
        self._refused_by_the_rate()
        response = self._close(first["task_id"])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.counted(), THE_BOUND)
        self._refused_by_the_rate()

    # --- the standing -----------------------------------------------------

    def test_its_suspended_customer_is_refused_at_the_start(self):
        self._suspend()
        body = self._refused_for_standing(self.STANDING_WORD_FOR_A_SUSPENSION)
        self.assertIsNone(body["balance_micros"])
        self.assertEqual(Task.objects.filter(customer=self.customer).count(), 0)

    def test_its_closed_customer_is_refused_at_the_start(self):
        self.customer.status = CUSTOMER_STATUS_CLOSED
        self.customer.save(update_fields=["status"])
        self._refused_for_standing(AFFORDABILITY_REASON_ACCOUNT_CLOSED)

    def test_a_customer_both_stopped_and_over_the_rate_is_told_about_the_rate_first(self):
        """The one observable reordering, asserted (§6): the rate answers
        before the standing, and a caller that backs off then meets the
        stop. Backing off past the window is the store forgetting the
        seat's keys; a case cannot wait a minute, so it forgets them the
        way expiry would."""
        self._suspend()
        for _ in range(THE_BOUND):
            self._refused_for_standing(self.STANDING_WORD_FOR_A_SUSPENSION)
        self._refused_by_the_rate()
        cache.delete_many(admission.window_keys(self.customer.id))
        self._refused_for_standing(self.STANDING_WORD_FOR_A_SUSPENSION)


class ATenantThatDoesNotBillThroughUbbTest(AdmissionRouteCases, TestCase):
    """The posture owed by name: no wallet regime, no money-shaped verdict
    — and, until #462, no bound and no standing check at the start."""


class ATenantWithAWalletRegimeTest(AdmissionRouteCases, TestCase):
    """The same refusals at the same point for a tenant the money verdict
    also runs for. A suspension here is refused in the line's word — the
    wallet's, since no pool holds this customer — which is #459's answer
    kept; the reordering case is what pins that the rate still answers
    before it."""

    PRODUCTS = ("metering", "billing")
    BILLING_MODE = "prepaid"
    BALANCE_MICROS = 100_000_000
    STANDING_WORD_FOR_A_SUSPENSION = AFFORDABILITY_REASON_INSUFFICIENT_FUNDS


class ATenantDeclaringNoBoundTest(TestCase):
    """The default posture: NULL is no bound, so the bound is the tenant's
    declaration and a tenant that never made one is throttled by nothing —
    exactly as a tenant with no risk row was."""

    def setUp(self):
        self.client = Client()
        self.fixture = a_tenant_selling_whole_work()
        self.assertIsNone(self.fixture.tenant.max_task_starts_per_minute)

    def test_every_start_is_admitted_and_the_store_is_untouched(self):
        for _ in range(THE_BOUND + 2):
            response = self.client.post(
                "/api/v1/tasks",
                data=json.dumps(self.fixture.start_body(task_type=SOLD_PER_EVENT)),
                content_type="application/json", **self.fixture.auth())
            self.assertEqual(response.status_code, 200, response.content)
        starts_key, ends_key = admission.window_keys(self.fixture.customer.id)
        self.assertIsNone(cache.get(starts_key))
        self.assertIsNone(cache.get(ends_key))
