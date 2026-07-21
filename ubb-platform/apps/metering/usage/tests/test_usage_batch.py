"""F4.2 POST /usage/batch: independent per-item commits, per-item error
mapping byte-equivalent to sequential singles, whole-batch replay safety."""
import json
import uuid
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.metering.usage.models import UsageEvent
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tasks.models import Task
from apps.platform.tenants.models import Tenant, TenantApiKey

BATCH_URL = "/api/v1/metering/usage/batch"
SINGLE_URL = "/api/v1/metering/usage"


def _setup(**tenant_kwargs):
    t = Tenant.objects.create(name="T", products=["metering", "billing"],
                              **tenant_kwargs)
    _, raw_key = TenantApiKey.create_key(t, label="test")
    c = Customer.objects.create(tenant=t, external_id="cust1")
    http = Client()
    auth = {"HTTP_AUTHORIZATION": f"Bearer {raw_key}"}
    return t, c, http, auth


def _post(http, auth, url, body):
    return http.post(url, data=json.dumps(body),
                     content_type="application/json", **auth)


def _item(c, n, **extra):
    return {"customer_id": str(c.id), "request_id": f"r{n}",
            "idempotency_key": f"k{n}", "provider_cost_micros": 10, **extra}


@pytest.mark.django_db
class TestBatchBasics:
    def test_middle_item_invalid_others_commit(self):
        t, c, http, auth = _setup()
        too_old = (timezone.now() - timedelta(days=40)).isoformat()
        resp = _post(http, auth, BATCH_URL, {"events": [
            _item(c, 1), _item(c, 2, effective_at=too_old), _item(c, 3)]})
        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] == 2 and body["rejected"] == 1
        assert body["results"][0]["accepted"] is True
        assert body["results"][1] == {
            "accepted": False, "code": "effective_at_too_old",
            "detail": body["results"][1]["detail"],
            "stop": False, "stop_reason": None, "stop_scope": None}
        assert body["results"][2]["accepted"] is True
        # Items 1 + 3 are durably committed: event rows AND outbox rows exist.
        assert UsageEvent.objects.filter(tenant=t).count() == 2
        assert OutboxEvent.objects.filter(
            event_type="usage.recorded", tenant_id=t.id).count() == 2

    def test_whole_batch_replay_returns_original_ids_zero_new_rows(self):
        t, c, http, auth = _setup()
        events = {"events": [_item(c, 1), _item(c, 2), _item(c, 3)]}
        first = _post(http, auth, BATCH_URL, events).json()
        ids = [r["event_id"] for r in first["results"]]
        assert UsageEvent.objects.filter(tenant=t).count() == 3
        replay = _post(http, auth, BATCH_URL, events).json()
        assert replay["accepted"] == 3 and replay["rejected"] == 0
        assert [r["event_id"] for r in replay["results"]] == ids
        assert UsageEvent.objects.filter(tenant=t).count() == 3

    def test_duplicate_key_within_one_batch_resolves_to_first(self):
        t, c, http, auth = _setup()
        resp = _post(http, auth, BATCH_URL, {"events": [
            _item(c, 1),
            {"customer_id": str(c.id), "request_id": "r-other",
             "idempotency_key": "k1", "provider_cost_micros": 99},
        ]}).json()
        assert resp["accepted"] == 2
        assert resp["results"][1]["event_id"] == resp["results"][0]["event_id"]
        assert UsageEvent.objects.filter(tenant=t).count() == 1

    def test_zero_items_422(self):
        t, c, http, auth = _setup()
        resp = _post(http, auth, BATCH_URL, {"events": []})
        assert resp.status_code == 422

    def test_over_100_items_422(self):
        t, c, http, auth = _setup()
        resp = _post(http, auth, BATCH_URL,
                     {"events": [_item(c, n) for n in range(101)]})
        assert resp.status_code == 422
        assert UsageEvent.objects.count() == 0

    def test_exactly_100_items_accepted(self):
        t, c, http, auth = _setup()
        resp = _post(http, auth, BATCH_URL,
                     {"events": [_item(c, n) for n in range(100)]})
        assert resp.status_code == 200
        assert resp.json()["accepted"] == 100

    def test_unknown_customer_not_found_isolated(self):
        t, c, http, auth = _setup()
        bogus = str(uuid.uuid4())
        resp = _post(http, auth, BATCH_URL, {"events": [
            {"customer_id": bogus, "request_id": "r1", "idempotency_key": "k1",
             "provider_cost_micros": 10},
            _item(c, 2),
        ]}).json()
        assert resp["results"][0] == {
            "accepted": False, "code": "not_found",
            "detail": "Customer not found",
            "stop": False, "stop_reason": None, "stop_scope": None}
        assert resp["results"][1]["accepted"] is True

    def test_unknown_task_not_found(self):
        t, c, http, auth = _setup()
        resp = _post(http, auth, BATCH_URL, {"events": [
            _item(c, 1, task_id=str(uuid.uuid4()))]}).json()
        assert resp["results"][0] == {
            "accepted": False, "code": "not_found",
            "detail": "Task not found",
            "stop": False, "stop_reason": None, "stop_scope": None}

    def test_mixed_effective_at_errors_isolated(self):
        t, c, http, auth = _setup()
        resp = _post(http, auth, BATCH_URL, {"events": [
            _item(c, 1, effective_at=(timezone.now() + timedelta(minutes=10)).isoformat()),
            _item(c, 2, effective_at="2026-06-01T12:00:00"),  # naive
            _item(c, 3, effective_at=(timezone.now() - timedelta(days=3)).isoformat()),
        ]}).json()
        assert resp["results"][0]["code"] == "effective_at_in_future"
        assert resp["results"][1]["code"] == "effective_at_naive"
        assert resp["results"][2]["accepted"] is True
        assert resp["accepted"] == 1 and resp["rejected"] == 2

    def test_validation_error_mapped(self):
        """The generic ValueError branch (e.g. bad tags) maps to validation_error."""
        t, c, http, auth = _setup()
        resp = _post(http, auth, BATCH_URL, {"events": [
            _item(c, 1, tags={"BAD KEY": "x"})]}).json()
        assert resp["results"][0]["code"] == "validation_error"
        assert resp["rejected"] == 1

    def test_success_body_mirrors_single_call(self):
        """A batch success item carries the single-call success body + accepted."""
        t, c, http, auth = _setup()
        single = _post(http, auth, SINGLE_URL,
                       {"customer_id": str(c.id), "request_id": "s1",
                        "idempotency_key": "ks1", "provider_cost_micros": 10}).json()
        batch = _post(http, auth, BATCH_URL, {"events": [_item(c, 1)]}).json()
        item = dict(batch["results"][0])
        assert item.pop("accepted") is True
        # Same keys as the single-call response (values differ only where ids do).
        assert set(single.keys()) == set(item.keys())


@pytest.mark.django_db
class TestBatchOneRuleParity:
    """One-rule (#37): items that once came back as hard_stop / run_not_active
    rejections now return accepted=True with the stop-verdict fields — the
    batch CONTINUES, and every item lands, bills, and counts."""

    def _task(self, t, c, limit=1_000):
        return Task.objects.create(tenant=t, customer=c, status="active",
                                   balance_snapshot_micros=10_000_000,
                                   provider_cost_limit_micros=limit,
                                   billing_owner_id=c.id)

    def _items(self, c, task, n0=1):
        return [
            {"customer_id": str(c.id), "request_id": f"r{n0}",
             "idempotency_key": f"k{n0}", "provider_cost_micros": 600,
             "task_id": str(task.id)},
            {"customer_id": str(c.id), "request_id": f"r{n0+1}",
             "idempotency_key": f"k{n0+1}", "provider_cost_micros": 600,
             "task_id": str(task.id)},  # 1200 > 1000 → task_limit crossing
            {"customer_id": str(c.id), "request_id": f"r{n0+2}",
             "idempotency_key": f"k{n0+2}", "provider_cost_micros": 100,
             "task_id": str(task.id)},  # task now killed → task_not_active
        ]

    def test_tipping_item_kills_task_and_batch_continues(self):
        t, c, http, auth = _setup()
        task = self._task(t, c)
        resp = _post(http, auth, BATCH_URL, {"events": self._items(c, task)}).json()
        r1, r2, r3 = resp["results"]
        assert r1["accepted"] is True
        assert r1["stop"] is False
        # The tipping item answers accepted=True with the stop verdict riding it.
        assert r2["accepted"] is True
        assert r2["stop"] is True
        assert r2["stop_reason"] == "task_limit"
        assert r2["stop_scope"] == "task"
        assert r2["task_total_provider_cost_micros"] == 1_200
        # A later item on the killed task still LANDS, with task_not_active.
        assert r3["accepted"] is True
        assert r3["stop"] is True
        assert r3["stop_reason"] == "task_not_active"
        assert r3["stop_scope"] == "task"
        assert resp["accepted"] == 3 and resp["rejected"] == 0

        # Every item landed and counted into BOTH totals.
        assert UsageEvent.objects.filter(tenant=t).count() == 3
        task.refresh_from_db()
        assert task.status == "killed"
        assert task.metadata.get("kill_reason") == "task_limit"
        assert task.total_provider_cost_micros == 1_300
        assert task.total_billed_cost_micros == 1_300
        assert task.event_count == 3

    def test_kill_failure_does_not_500_batch(self):
        """A kill_task crash is contained by kill_and_announce (it swallows
        and logs task.kill_failed) — the batch still answers 200 with
        accepted=True items and every event lands. The failed kill leaves the
        task ACTIVE, so later items keep re-reporting the task_limit crossing
        (the next event's verdict retries the kill)."""
        from unittest import mock
        t, c, http, auth = _setup()
        task = self._task(t, c)
        with mock.patch("apps.platform.tasks.services.TaskService.kill_task",
                        side_effect=RuntimeError("kill boom")) as kill:
            resp = _post(http, auth, BATCH_URL, {"events": self._items(c, task)})
        assert resp.status_code == 200  # never a 500
        body = resp.json()
        r1, r2, r3 = body["results"]
        assert r1["accepted"] is True and r1["stop"] is False
        assert r2["accepted"] is True
        assert r2["stop_reason"] == "task_limit"
        assert kill.called
        # The task was never killed -> item 3 still lands; its provider total
        # (1300) remains past the limit, so the crossing verdict repeats.
        assert r3["accepted"] is True
        assert r3["stop_reason"] == "task_limit"
        task.refresh_from_db()
        assert task.status == "active"
        assert task.event_count == 3
        assert body["accepted"] == 3 and body["rejected"] == 0

    def test_byte_equivalent_to_sequential_singles(self):
        """The batch per-item bodies equal the single endpoint's bodies for the
        identical scenario (modulo the 'accepted' marker and the task/event
        ids)."""
        t, c, http, auth = _setup()
        c2 = Customer.objects.create(tenant=t, external_id="cust2")
        task_b = self._task(t, c)
        task_s = self._task(t, c2)

        batch = _post(http, auth, BATCH_URL,
                      {"events": self._items(c, task_b)}).json()
        single_bodies = []
        for item in self._items(c2, task_s, n0=10):
            single_bodies.append(_post(http, auth, SINGLE_URL, item).json())

        def normalize(d):
            d = {k: v for k, v in d.items() if k not in ("accepted",)}
            if d.get("task_id"):
                d["task_id"] = "TASK"
            if d.get("event_id"):
                d["event_id"] = "EVT"
            if d.get("stop_context"):
                # Same volatile-field masking as above: ids and trip times
                # naturally differ between the two runs; limit/scope/
                # episode_seq/arrived_after must still match byte-for-byte.
                d["stop_context"] = [
                    {**ctx,
                     "task_id": "TASK" if ctx.get("task_id") else None,
                     "subtask_id": "SUB" if ctx.get("subtask_id") else None,
                     "tripped_at": "T" if ctx.get("tripped_at") else None}
                    for ctx in d["stop_context"]]
            return d

        for batch_item, single_body in zip(batch["results"], single_bodies):
            assert normalize(batch_item) == normalize(single_body)
