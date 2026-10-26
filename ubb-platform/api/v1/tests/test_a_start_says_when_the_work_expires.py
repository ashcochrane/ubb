"""A start says when UBB will expire the work it registered (#540 comment
`5831553075`, #179 §2.4).

The SDK's `TaskOutcomeRequired` — a work block that ended without declaring how
the work ended — is required to carry the unit's expiry, so a caller that
leaves work open learns how long it stays counted as active. It could not:
the registration published no expiry, so the SDK carried what the wire did.

A unit is expired on two windows, and neither is one instant a start can name
on its own (`apps/platform/work/tasks.py`):

  * its **Absolute deadline**, measured from registration whatever the work
    does — an instant, published as `absolute_deadline_at`, and never null
    because the deadline cannot be switched off at any rung;
  * its **Silence window**, measured from the last usage report — a duration,
    published as `silence_window_seconds`, null where the resolved answer is
    that the unit has none.

Both are the ladder `expiry_windows` resolves — the declared kind of work, then
the workspace default, then UBB's backstop — and each is REQUIRED (#569's rule
for a new response fact), the second NULLABLE.

⚠ **WHAT THE START PUBLISHES IS THE POLICY AS IT STOOD THEN — A SNAPSHOT, AND
NOT A PROMISE.** The start resolves the ladder once and records the two
windows on the unit; its response, and every replay of it, answers from that
record (ADR-0019: a replay answers from what it said). The sweepers do not
read the record: they resolve the ladder each time they run, because that is
the ladder's own rule — a changed window reaches work already running. So a
published `absolute_deadline_at` is the deadline the policy set at the start,
and the unit can be expired earlier, or later, once the policy changes. The
last class below drives exactly that case end to end.
"""
import json
import uuid
from datetime import datetime, timedelta

from django.test import Client, TestCase
from django.utils import timezone

from api.v1.tests._helpers import a_tenant
from apps.platform.customers.models import Customer
from apps.platform.work import reasons
from apps.platform.work.models import Task, TaskType
from apps.platform.work.queries import (
    ABSOLUTE_DEADLINE_BACKSTOP_SECONDS, SILENCE_WINDOW_BACKSTOP_SECONDS)
from apps.platform.work.tasks import reap_stale_tasks
from core.vocabulary import (
    TASK_STATUS_EXPIRED, TASK_TYPE_KIND_SUBTASK, TASK_TYPE_KIND_TASK)


class StartExpiryTestBase(TestCase):

    def setUp(self):
        self.tenant, self.raw_key = a_tenant("Expiry")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1")
        self.http_client = Client()

    def _kind(self, key, *, kind=TASK_TYPE_KIND_TASK, **windows):
        return TaskType.objects.create(tenant=self.tenant, key=key, kind=kind,
                                       uncapped=True, **windows)

    def _start(self, **body):
        body.setdefault("customer_id", str(self.customer.id))
        body.setdefault("idempotency_key", f"attempt-{uuid.uuid4()}")
        response = self.http_client.post(
            "/api/v1/tasks", data=json.dumps(body),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def assertDeadlineAfter(self, body, seconds):
        self.assertEqual(
            datetime.fromisoformat(body["absolute_deadline_at"]),
            datetime.fromisoformat(body["created_at"])
            + timedelta(seconds=seconds))


class AStartPublishesItsExpiryTest(StartExpiryTestBase):

    def test_undeclared_work_answers_with_ubbs_backstops(self):
        body = self._start()

        self.assertDeadlineAfter(body, ABSOLUTE_DEADLINE_BACKSTOP_SECONDS)
        self.assertEqual(body["silence_window_seconds"],
                         SILENCE_WINDOW_BACKSTOP_SECONDS)

    def test_a_declared_kind_of_work_answers_with_its_own_windows(self):
        self._kind("transcode", silence_window_seconds=1200,
                   absolute_deadline_seconds=7200)

        body = self._start(task_type="transcode")

        self.assertDeadlineAfter(body, 7200)
        self.assertEqual(body["silence_window_seconds"], 1200)

    def test_a_kind_that_declares_no_silence_window_says_none(self):
        """`0` declared at a rung is the answer *no window*, and the published
        figure says null rather than a window of zero seconds — a unit that
        any silence at all would expire."""
        self._kind("overnight", silence_window_seconds=0,
                   absolute_deadline_seconds=86_400)

        body = self._start(task_type="overnight")

        self.assertIn("silence_window_seconds", body)
        self.assertIsNone(body["silence_window_seconds"])
        self.assertDeadlineAfter(body, 86_400)

    def test_the_workspace_default_answers_where_the_kind_says_nothing(self):
        self.tenant.task_stale_seconds = 300
        self.tenant.task_absolute_deadline_seconds = 3600
        self.tenant.save(update_fields=["task_stale_seconds",
                                        "task_absolute_deadline_seconds"])
        self._kind("transcode")

        body = self._start(task_type="transcode")

        self.assertDeadlineAfter(body, 3600)
        self.assertEqual(body["silence_window_seconds"], 300)

    def test_contained_work_answers_with_its_own_altitudes_declaration(self):
        """One word may name a kind of work at either altitude, and the two
        are different declarations with different windows."""
        self._kind("step", silence_window_seconds=1200,
                   absolute_deadline_seconds=7200)
        self._kind("step", kind=TASK_TYPE_KIND_SUBTASK,
                   silence_window_seconds=60, absolute_deadline_seconds=600)
        parent = self._start(task_type="step")

        body = self._start(task_type="step", parent_task_id=parent["task_id"])

        self.assertDeadlineAfter(body, 600)
        self.assertEqual(body["silence_window_seconds"], 60)

    def test_a_replay_answers_the_same_expiry(self):
        self._kind("transcode", silence_window_seconds=1200,
                   absolute_deadline_seconds=7200)
        first = self._start(task_type="transcode", idempotency_key="k-1")

        again = self._start(task_type="transcode", idempotency_key="k-1")

        self.assertTrue(again["replayed"])
        self.assertEqual(again["absolute_deadline_at"],
                         first["absolute_deadline_at"])
        self.assertEqual(again["silence_window_seconds"],
                         first["silence_window_seconds"])


class AReplayRepeatsTheStartWhileTheSweeperFollowsThePolicyTest(
        StartExpiryTestBase):
    """The decisive case for the snapshot, through the public routes: a start,
    a changed declaration, a replay of the same start, and the sweeper."""

    def _declare(self, **windows):
        response = self.http_client.put(
            "/api/v1/task-types", content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
            data={"task_types": [{"key": "transcode",
                                  "kind": TASK_TYPE_KIND_TASK,
                                  "uncapped": True, **windows}]})
        self.assertEqual(response.status_code, 200, response.content)

    def test_the_replay_answers_the_original_and_the_sweeper_the_live_policy(self):
        self.tenant.enforcement_mode = "enforcing"
        self.tenant.save(update_fields=["enforcement_mode"])
        self._declare(silence_window_seconds=1200, absolute_deadline_seconds=7200)

        # 1. The start, and the two values it published.
        first = self._start(task_type="transcode", idempotency_key="k-1")
        self.assertDeadlineAfter(first, 7200)
        self.assertEqual(first["silence_window_seconds"], 1200)

        # 2. The declaration changes: a far shorter deadline, no silence window.
        self._declare(silence_window_seconds=0, absolute_deadline_seconds=600)

        # 3. A replay of the same start answers what the start said...
        again = self._start(task_type="transcode", idempotency_key="k-1")
        self.assertTrue(again["replayed"])
        self.assertEqual(again["absolute_deadline_at"],
                         first["absolute_deadline_at"])
        self.assertEqual(again["silence_window_seconds"],
                         first["silence_window_seconds"])
        # ...while a NEW start of the same kind answers the changed policy, so
        # the replay's answer is the record's and not a ladder that held still.
        fresh = self._start(task_type="transcode")
        self.assertDeadlineAfter(fresh, 600)
        self.assertIsNone(fresh["silence_window_seconds"])

        # 4. The sweeper enforces the live policy on the running unit: twenty
        # minutes in, it is past the new ten-minute deadline and well inside
        # the two hours the start published.
        Task.objects.filter(id=first["task_id"]).update(
            created_at=timezone.now() - timedelta(minutes=20))

        self.assertEqual(reap_stale_tasks(), 1)

        read = self.http_client.get(
            f"/api/v1/tasks/{first['task_id']}",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}").json()
        self.assertEqual(read["status"], TASK_STATUS_EXPIRED)
        self.assertEqual(read["reason_code"], reasons.ABSOLUTE_DEADLINE)
        self.assertLess(timezone.now(),
                        datetime.fromisoformat(first["absolute_deadline_at"])
                        - timedelta(minutes=20))
