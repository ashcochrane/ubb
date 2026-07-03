"""Wave 2 capstone integration test for Journey 1 (cost attribution).

A REAL live-server test driving the ``ubb`` Python SDK over HTTP against a
running Django server. It proves a tenant can do best-in-class cost attribution
end to end -- with NO raw SQL and NO client-side joins -- using only the SDK:

  - bulk-create dimensional cost cards (one POST for the whole batch),
  - record a fleet of multi-dimension usage events with NO caller-supplied cost,
    so the server computes COGS from the matching dimensional cost card,
  - read a multi-dimension COGS breakdown back (product / service / agent) and
    have every breakdown reconcile to the SAME grand-total provider cost,
  - read a per-day time-series that reconciles to the dimensional breakdown,
  - walk a rate-card's version history and query it point-in-time via ``as_of``,
  - and prove the opt-in strict mode rejects an uncosted metric (no silent $0).

Why live-server (not mocked httpx): mocked unit tests let real wire-level
mismatches ship undetected (a 404 on a renamed route, a response body the SDK
can't deserialize, a query param django-ninja doesn't bind). This exercises the
real URL routing, the real pricing/COGS engine, and the real SDK response
contract end to end.

COGS arithmetic (Rate.compute with unit_quantity=1, fixed_micros=0):
    compute(units) == (units * rate_per_unit_micros + unit_quantity // 2)
                      // unit_quantity + fixed_micros
  - service "alpha" card: rate 2/unit  -> compute(100) == (100*2 + 0)//1 == 200
  - service "beta"  card: rate 5/unit  -> compute(100) == (100*5 + 0)//1 == 500
"""
import datetime as dt

import pytest

from django.utils import timezone

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.metering.usage.models import UsageEvent


@pytest.fixture
def _no_outbox_dispatch():
    """Neutralize the transactional-outbox Celery dispatch for this test.

    record_usage writes an OutboxEvent and fires
    ``transaction.on_commit(lambda: process_single_event.delay(...))``. Under
    live_server there is no Celery worker/broker, so that ``.delay()`` would try
    to publish to the real broker and raise on the commit hook -> the
    /api/v1/metering/usage request returns HTTP 500. Patching the dispatch symbol
    to a no-op removes the broker dependency deterministically; because
    live_server runs in this same process, the patch applies to the server thread
    too. The HTTP response (routing, pricing/COGS, SDK contract) is computed
    synchronously before commit; only the fire-and-forget fan-out is suppressed.
    """
    from unittest.mock import patch

    with patch("apps.platform.events.tasks.process_single_event.delay"):
        yield


# Expected per-event COGS, keyed by the service dimension, from the two cost
# cards below. Asserted exactly so every reconciliation below is precise.
COST_ALPHA = 200   # rate 2/unit * 100 units, unit_quantity=1
COST_BETA = 500    # rate 5/unit * 100 units, unit_quantity=1
# Unattributed event: recorded with an explicit provider_cost_micros (no service tag).
COST_UNATTR = 300


def _force_day(event_id, day):
    """Pin an immutable UsageEvent onto a specific calendar day (UTC noon)."""
    UsageEvent.objects.filter(id=event_id).update(
        effective_at=timezone.make_aware(dt.datetime(2026, 1, day, 12, 0, 0)))


@pytest.mark.django_db(transaction=True)
def test_journey1_best_in_class_cost_attribution_via_sdk(live_server, _no_outbox_dispatch):
    from ubb.metering import MeteringClient
    from ubb.exceptions import UBBAPIError

    tenant = Tenant.objects.create(name="J1cap", products=["metering"])
    _, raw_key = TenantApiKey.create_key(tenant)
    c1 = Customer.objects.create(tenant=tenant, external_id="c1")
    Customer.objects.create(tenant=tenant, external_id="c2")  # C2: isolation/noise

    client = MeteringClient(api_key=raw_key, base_url=live_server.url)
    try:
        # ---- 2. bulk-create TWO dimensional cost cards for metric "tokens" ----
        # They differ ONLY by the {"service": ...} dimension. The pricing engine
        # matches a card's dimensions against the event's tags.
        batch = client.bulk_create_rate_cards([
            {"card_type": "cost", "metric_name": "tokens",
             "dimensions": {"service": "alpha"},
             "pricing_model": "per_unit", "rate_per_unit_micros": 2, "unit_quantity": 1},
            {"card_type": "cost", "metric_name": "tokens",
             "dimensions": {"service": "beta"},
             "pricing_model": "per_unit", "rate_per_unit_micros": 5, "unit_quantity": 1},
        ])
        assert batch["count"] == 2
        assert len(batch["created"]) == 2

        # ---- 3. record 8 events for C1: 2 products x 2 services x 2 agents,
        # spread across 3 days; ONE event carries a mis-typed agent tag. ----
        # Each tuple: (product, service, agent, day). Expected cost derives purely
        # from `service`. The matrix is balanced so each dimension reconciles.
        matrix = [
            ("p1", "alpha", "ag1",     1),   # 200
            ("p1", "beta",  "ag2",     1),   # 500
            ("p2", "alpha", "ag2",     2),   # 200
            ("p2", "beta",  "ag1",     2),   # 500
            ("p1", "alpha", "ag1",     3),   # 200
            ("p1", "beta",  "ag2",     3),   # 500
            ("p2", "alpha", "ag_typo", 1),   # 200  <- the typo'd agent
            ("p2", "beta",  "ag1",     2),   # 500
        ]
        expected_cost = {"alpha": COST_ALPHA, "beta": COST_BETA}
        for i, (product, service, agent, day) in enumerate(matrix):
            res = client.record_usage(
                customer_id=str(c1.id), request_id=f"r{i}", idempotency_key=f"i{i}",
                product_id=product, usage_metrics={"tokens": 100},
                tags={"service": service, "agent": agent})
            # Server computed COGS from the matching dimensional cost card.
            assert res.provider_cost_micros == expected_cost[service], (i, service)
            assert res.uncosted_metrics == []   # tokens HAS a matching card
            assert res.service_id == service
            assert res.agent_id == agent
            _force_day(res.event_id, day)

        # ---- 3b. One extra event for C1 with NO service tag -> service_id="" ----
        # This event MUST appear as "(unattributed)" in the service_id breakdown
        # so that the breakdown reconciles to the new grand total.
        unattr_res = client.record_usage(
            customer_id=str(c1.id), request_id="r_unattr", idempotency_key="i_unattr",
            provider_cost_micros=COST_UNATTR,
            # Deliberately no service/agent/product tags so all three dimension
            # fields are empty strings on the stored event.
        )
        assert unattr_res.provider_cost_micros == COST_UNATTR
        assert unattr_res.service_id == ""
        _force_day(unattr_res.event_id, 1)  # pin to day 1 alongside other day-1 events

        # Expected grand-total provider cost (COGS) across all 9 events (8 matrix + 1 unattr).
        grand_total = sum(expected_cost[svc] for _, svc, _, _ in
                          [(p, s, a, d) for (p, s, a, d) in matrix]) + COST_UNATTR
        assert grand_total == 4 * COST_ALPHA + 4 * COST_BETA + COST_UNATTR == 3100

        # Per-dimension expected provider-cost totals (matrix events + unattributed event).
        # The unattributed event contributes to the "(unattributed)" bucket in each dimension.
        exp_by_product, exp_by_service, exp_by_agent = {}, {}, {}
        for product, service, agent, _ in matrix:
            cost = expected_cost[service]
            exp_by_product[product] = exp_by_product.get(product, 0) + cost
            exp_by_service[service] = exp_by_service.get(service, 0) + cost
            exp_by_agent[agent] = exp_by_agent.get(agent, 0) + cost
        # The extra unattributed event has no service/agent/product tags.
        exp_by_service["(unattributed)"] = COST_UNATTR
        exp_by_product["(unattributed)"] = COST_UNATTR
        exp_by_agent["(unattributed)"] = COST_UNATTR

        # ---- 4. multi-dimension COGS breakdown via the SDK (no client joins) ----
        rep = client.usage_analytics(
            customer_id=str(c1.id),
            dimensions=["product_id", "service_id", "agent_id"])
        breakdowns = rep["breakdowns"]
        assert set(breakdowns) == {"product_id", "service_id", "agent_id"}

        def _as_map(rows):
            return {r["dimension"]: r["total_provider_cost_micros"] for r in rows}

        by_product = _as_map(breakdowns["product_id"])
        by_service = _as_map(breakdowns["service_id"])
        by_agent = _as_map(breakdowns["agent_id"])

        # (a) per-service totals reflect alpha=2/unit (200 each) vs beta=5/unit (500 each),
        #     PLUS an "(unattributed)" row for the event with no service tag.
        assert by_service == exp_by_service == {
            "alpha": 800, "beta": 2000, "(unattributed)": COST_UNATTR}
        # (b) every breakdown sums to the SAME grand-total provider cost (including unattributed).
        assert sum(by_product.values()) == grand_total
        assert sum(by_service.values()) == grand_total
        assert sum(by_agent.values()) == grand_total
        assert by_product == exp_by_product
        assert by_agent == exp_by_agent
        # (c) the typo'd agent is its OWN row -- not merged into a real agent, not dropped.
        assert "ag_typo" in by_agent
        assert by_agent["ag_typo"] == COST_ALPHA   # event 7 was service "alpha"
        assert rep["total_provider_cost_micros"] == grand_total

        # ---- 5. time-series per-day per-service reconciles to the step-4 breakdown ----
        ts = client.usage_timeseries(
            customer_id=str(c1.id), granularity="day", group_by="service_id")
        series = ts["series"]
        # 3 distinct day-buckets (days 1, 2, 3).
        buckets = {row["bucket"] for row in series}
        assert len(buckets) == 3, buckets
        # Sum provider cost per service across all buckets -> must equal step-4 totals.
        ts_by_service = {}
        for row in series:
            svc = row["dimension"]
            ts_by_service[svc] = ts_by_service.get(svc, 0) + (row["provider_cost_micros"] or 0)
        # Timeseries totals per service must match the step-4 dimensional breakdown
        # (alpha, beta, AND the "(unattributed)" bucket from the no-service-tag event).
        assert ts_by_service == by_service == {
            "alpha": 800, "beta": 2000, "(unattributed)": COST_UNATTR}

        # ---- 6. rate-card version history + point-in-time as_of ----
        alpha_card_id = batch["created"][0]   # the {"service":"alpha"} cost card
        # Capture a timestamp strictly BEFORE the update (old rate is active then).
        before_update = timezone.now()

        updated = client.update_rate_card(alpha_card_id, rate_per_unit_micros=99)
        lineage_id = updated.lineage_id

        history = client.get_rate_card_history(lineage_id)
        assert len(history) == 2                       # original + new version
        assert history[0].rate_per_unit_micros == 99   # newest first
        assert history[1].rate_per_unit_micros == 2    # the original alpha rate
        # Non-overlapping validity: old version closed, new version open.
        assert history[1].valid_to is not None
        assert history[0].valid_to is None
        assert history[1].valid_to <= history[0].valid_from  # windows don't overlap

        # as_of BEFORE the update -> the OLD rate (2) is the active version then.
        as_of_iso = before_update.isoformat()
        at_before = {c.lineage_id: c for c in client.list_rate_cards(as_of=as_of_iso)}
        assert at_before[lineage_id].rate_per_unit_micros == 2
        # And the current active list shows the NEW rate (99).
        now_active = {c.lineage_id: c for c in client.list_rate_cards(card_type="cost")}
        assert now_active[lineage_id].rate_per_unit_micros == 99

        # ---- 7. opt-in strict mode: an uncosted metric is REJECTED (no silent $0) ----
        tenant.require_cost_card_coverage = True
        tenant.save()
        with pytest.raises(UBBAPIError) as exc:
            client.record_usage(
                customer_id=str(c1.id), request_id="r_strict",
                idempotency_key="i_strict", usage_metrics={"unmatched_metric": 5},
                tags={"service": "alpha"})
        assert exc.value.status_code == 422
    finally:
        client.close()
