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
from apps.platform.runs.models import Run
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
        assert body["succeeded"] == 2 and body["failed"] == 1
        assert body["results"][0]["ok"] is True
        assert body["results"][1] == {
            "ok": False, "error": "effective_at_too_old",
            "detail": body["results"][1]["detail"]}
        assert body["results"][2]["ok"] is True
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
        assert replay["succeeded"] == 3 and replay["failed"] == 0
        assert [r["event_id"] for r in replay["results"]] == ids
        assert UsageEvent.objects.filter(tenant=t).count() == 3

    def test_duplicate_key_within_one_batch_resolves_to_first(self):
        t, c, http, auth = _setup()
        resp = _post(http, auth, BATCH_URL, {"events": [
            _item(c, 1),
            {"customer_id": str(c.id), "request_id": "r-other",
             "idempotency_key": "k1", "provider_cost_micros": 99},
        ]}).json()
        assert resp["succeeded"] == 2
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
        assert resp.json()["succeeded"] == 100

    def test_unknown_customer_not_found_isolated(self):
        t, c, http, auth = _setup()
        bogus = str(uuid.uuid4())
        resp = _post(http, auth, BATCH_URL, {"events": [
            {"customer_id": bogus, "request_id": "r1", "idempotency_key": "k1",
             "provider_cost_micros": 10},
            _item(c, 2),
        ]}).json()
        assert resp["results"][0] == {"ok": False, "error": "not_found",
                                      "detail": "Customer not found"}
        assert resp["results"][1]["ok"] is True

    def test_unknown_run_not_found(self):
        t, c, http, auth = _setup()
        resp = _post(http, auth, BATCH_URL, {"events": [
            _item(c, 1, run_id=str(uuid.uuid4()))]}).json()
        assert resp["results"][0] == {"ok": False, "error": "not_found",
                                      "detail": "Run not found"}

    def test_mixed_effective_at_errors_isolated(self):
        t, c, http, auth = _setup()
        resp = _post(http, auth, BATCH_URL, {"events": [
            _item(c, 1, effective_at=(timezone.now() + timedelta(minutes=10)).isoformat()),
            _item(c, 2, effective_at="2026-06-01T12:00:00"),  # naive
            _item(c, 3, effective_at=(timezone.now() - timedelta(days=3)).isoformat()),
        ]}).json()
        assert resp["results"][0]["error"] == "effective_at_in_future"
        assert resp["results"][1]["error"] == "effective_at_naive"
        assert resp["results"][2]["ok"] is True
        assert resp["succeeded"] == 1 and resp["failed"] == 2

    def test_validation_error_mapped(self):
        """The generic ValueError branch (e.g. bad tags) maps to validation_error."""
        t, c, http, auth = _setup()
        resp = _post(http, auth, BATCH_URL, {"events": [
            _item(c, 1, tags={"BAD KEY": "x"})]}).json()
        assert resp["results"][0]["error"] == "validation_error"
        assert resp["failed"] == 1

    def test_success_body_mirrors_single_call(self):
        """A batch success item carries the single-call success body + ok."""
        t, c, http, auth = _setup()
        single = _post(http, auth, SINGLE_URL,
                       {"customer_id": str(c.id), "request_id": "s1",
                        "idempotency_key": "ks1", "provider_cost_micros": 10}).json()
        batch = _post(http, auth, BATCH_URL, {"events": [_item(c, 1)]}).json()
        item = dict(batch["results"][0])
        assert item.pop("ok") is True
        # Same keys as the single-call response (values differ only where ids do).
        assert set(single.keys()) == set(item.keys())


@pytest.mark.django_db
class TestBatchHardStopEquivalence:
    def _run(self, t, c, limit=1_000):
        return Run.objects.create(tenant=t, customer=c, status="active",
                                  balance_snapshot_micros=10_000_000,
                                  cost_limit_micros=limit)

    def _items(self, c, run, n0=1):
        return [
            {"customer_id": str(c.id), "request_id": f"r{n0}",
             "idempotency_key": f"k{n0}", "billed_cost_micros": 600,
             "run_id": str(run.id)},
            {"customer_id": str(c.id), "request_id": f"r{n0+1}",
             "idempotency_key": f"k{n0+1}", "billed_cost_micros": 600,
             "run_id": str(run.id)},  # 1200 > 1000 → hard stop
            {"customer_id": str(c.id), "request_id": f"r{n0+2}",
             "idempotency_key": f"k{n0+2}", "billed_cost_micros": 100,
             "run_id": str(run.id)},  # run now killed → run_not_active
        ]

    def test_hard_stop_kills_run_then_continues(self):
        t, c, http, auth = _setup()
        run = self._run(t, c)
        resp = _post(http, auth, BATCH_URL, {"events": self._items(c, run)}).json()
        r1, r2, r3 = resp["results"]
        assert r1["ok"] is True
        assert r2 == {"ok": False, "error": "hard_stop_exceeded",
                      "reason": "cost_limit_exceeded", "run_id": str(run.id),
                      "total_cost_micros": 1_200, "hard_stop": True}
        assert r3 == {"ok": False, "error": "run_not_active",
                      "run_id": str(run.id), "status": "killed"}
        run.refresh_from_db()
        assert run.status == "killed"
        assert run.total_cost_micros == 600  # only item 1 accumulated
        assert resp["succeeded"] == 1 and resp["failed"] == 2

    def test_kill_run_failure_does_not_500_batch(self):
        """F4.2 review Fix 5: a kill_run crash is contained — the item still
        reports hard_stop_exceeded and LATER items are processed. NOTE: the
        failed kill leaves the run ACTIVE, so the later item SUCCEEDS instead
        of run_not_active — the run.kill_failed log is the operator signal."""
        from unittest import mock
        t, c, http, auth = _setup()
        run = self._run(t, c)
        with mock.patch("apps.platform.runs.services.RunService.kill_run",
                        side_effect=RuntimeError("kill boom")) as kill:
            resp = _post(http, auth, BATCH_URL, {"events": self._items(c, run)})
        assert resp.status_code == 200  # never a 500
        body = resp.json()
        r1, r2, r3 = body["results"]
        assert r1["ok"] is True
        assert r2 == {"ok": False, "error": "hard_stop_exceeded",
                      "reason": "cost_limit_exceeded", "run_id": str(run.id),
                      "total_cost_micros": 1_200, "hard_stop": True}
        kill.assert_called_once()
        # The run was never killed -> item 3 (100 micros, 600+100 <= 1000)
        # is PROCESSED and succeeds.
        assert r3["ok"] is True
        run.refresh_from_db()
        assert run.status == "active"
        assert body["succeeded"] == 2 and body["failed"] == 1

    def test_byte_equivalent_to_sequential_singles(self):
        """The batch per-item bodies equal the single endpoint's bodies for the
        identical scenario (modulo the 'ok' marker and the run/customer ids)."""
        t, c, http, auth = _setup()
        c2 = Customer.objects.create(tenant=t, external_id="cust2")
        run_b = self._run(t, c)
        run_s = self._run(t, c2)

        batch = _post(http, auth, BATCH_URL,
                      {"events": self._items(c, run_b)}).json()
        single_bodies = []
        for item in self._items(c2, run_s, n0=10):
            single_bodies.append(_post(http, auth, SINGLE_URL, item).json())

        def normalize(d):
            d = {k: v for k, v in d.items() if k not in ("ok",)}
            if d.get("run_id"):
                d["run_id"] = "RUN"
            if d.get("event_id"):
                d["event_id"] = "EVT"
            return d

        for batch_item, single_body in zip(batch["results"], single_bodies):
            assert normalize(batch_item) == normalize(single_body)
