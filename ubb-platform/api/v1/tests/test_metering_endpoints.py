import json
from unittest.mock import patch

from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.platform.tasks.services import TaskService
from apps.billing.wallets.models import Wallet
from apps.metering.pricing.models import TenantMarkup
from apps.metering.pricing.services import markup_cache
from apps.metering.pricing.services.markup_cache import MarkupCache


class MeteringProductGatingTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant_metering_only = Tenant.objects.create(
            name="Metering Only", products=["metering"]
        )
        self.key_obj_met, self.raw_key_met = TenantApiKey.create_key(
            self.tenant_metering_only, label="test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant_metering_only, external_id="cust_met1"
        )
        wallet = Wallet.objects.create(customer=self.customer)
        wallet.balance_micros = 10_000_000
        wallet.save(update_fields=["balance_micros"])

    def test_metering_only_tenant_gets_403_on_billing_balance(self):
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/balance",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_met}",
        )
        self.assertEqual(response.status_code, 403)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_tenant_with_metering_can_record_usage(self, mock_process):
        response = self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps({
                "customer_id": str(self.customer.id),
                "request_id": "req_met_1",
                "idempotency_key": "idem_met_1",
                "provider_cost_micros": 1_500_000,
                "metadata": {"model": "gpt-4"},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_met}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body["new_balance_micros"])
        self.assertIn("event_id", body)

    def test_metering_only_tenant_gets_403_on_billing_transactions(self):
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/transactions",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_met}",
        )
        self.assertEqual(response.status_code, 403)

    def test_tenant_with_metering_can_get_usage_history(self):
        response = self.http_client.get(
            f"/api/v1/metering/customers/{self.customer.id}/usage",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_met}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("data", body)
        self.assertIn("has_more", body)


class PricingMarkupsCRUDTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        # Module-level L1 + contextvar are in-process state: reset per test,
        # mirroring apps/metering/pricing/tests/test_markup_cache.py.
        markup_cache._l1.clear()
        markup_cache._ctx_versions.set({})

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def test_get_tenant_markup_no_markup_returns_zeros(self):
        resp = self.http_client.get("/api/v1/metering/pricing/markup", **self._auth())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["markup_percentage_micros"], 0)
        self.assertEqual(body["fixed_uplift_micros"], 0)

    def test_put_tenant_markup_upserts(self):
        # Create
        resp = self.http_client.put(
            "/api/v1/metering/pricing/markup",
            data=json.dumps({"markup_percentage_micros": 20000000, "fixed_uplift_micros": 0}),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["markup_percentage_micros"], 20000000)

        # GET returns set values
        resp = self.http_client.get("/api/v1/metering/pricing/markup", **self._auth())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["markup_percentage_micros"], 20000000)

        # PUT again with different values updates in place — still exactly one row
        resp = self.http_client.put(
            "/api/v1/metering/pricing/markup",
            data=json.dumps({"markup_percentage_micros": 30000000, "fixed_uplift_micros": 500}),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["markup_percentage_micros"], 30000000)
        self.assertEqual(TenantMarkup.objects.filter(tenant=self.tenant, customer__isnull=True).count(), 1)

    def test_put_and_get_customer_markup_override(self):
        resp = self.http_client.put(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/markup",
            data=json.dumps({"markup_percentage_micros": 50000000, "fixed_uplift_micros": 0}),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)

        resp = self.http_client.get(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/markup",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["markup_percentage_micros"], 50000000)

    def test_get_customer_markup_falls_back_to_tenant_default(self):
        # Set only tenant default, no customer override
        TenantMarkup.objects.create(
            tenant=self.tenant, customer=None, markup_percentage_micros=15000000, fixed_uplift_micros=0
        )
        resp = self.http_client.get(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/markup",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["markup_percentage_micros"], 15000000)

    def test_customer_markup_zero_shadows_tenant_default(self):
        # Documents WHY delete exists: a 0/0 override is NOT the same as
        # inheriting — it shadows the tenant default and pins the customer at cost.
        TenantMarkup.objects.create(
            tenant=self.tenant, customer=None,
            markup_percentage_micros=15000000, fixed_uplift_micros=0)
        self.http_client.put(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/markup",
            data=json.dumps({"markup_percentage_micros": 0, "fixed_uplift_micros": 0}),
            content_type="application/json", **self._auth())
        resp = self.http_client.get(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/markup",
            **self._auth())
        self.assertEqual(resp.json()["markup_percentage_micros"], 0)

    def test_delete_customer_markup_reverts_to_tenant_default(self):
        TenantMarkup.objects.create(
            tenant=self.tenant, customer=None,
            markup_percentage_micros=15000000, fixed_uplift_micros=0)
        TenantMarkup.objects.create(
            tenant=self.tenant, customer=self.customer,
            markup_percentage_micros=50000000, fixed_uplift_micros=0)
        resp = self.http_client.delete(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/markup",
            **self._auth())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "deleted")
        # Now resolves to the tenant default (15%), NOT to zero.
        resp = self.http_client.get(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/markup",
            **self._auth())
        self.assertEqual(resp.json()["markup_percentage_micros"], 15000000)

    def test_delete_customer_markup_idempotent_when_no_override(self):
        resp = self.http_client.delete(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/markup",
            **self._auth())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "no_override")

    def test_delete_customer_markup_unknown_customer_404(self):
        resp = self.http_client.delete(
            "/api/v1/metering/pricing/customers/00000000-0000-0000-0000-000000000000/markup",
            **self._auth())
        self.assertEqual(resp.status_code, 404)

    def test_delete_customer_markup_bumps_l1_cache_immediately(self):
        """Regression: deleting a customer override that is LOWER than the
        tenant default must not leave MarkupCache's L1 serving the stale,
        lower markup for the TTL window — that under-estimates cost and
        therefore under-holds (money leak). The endpoint must delete via the
        model layer (TenantMarkup.delete()) so the version bump added in
        8272e5a actually fires; a queryset .filter(...).delete() bypasses it."""
        TenantMarkup.objects.create(
            tenant=self.tenant, customer=None,
            markup_percentage_micros=50_000_000, fixed_uplift_micros=0)  # tenant default 50%
        TenantMarkup.objects.create(
            tenant=self.tenant, customer=self.customer,
            markup_percentage_micros=10_000_000, fixed_uplift_micros=0)  # customer discount 10%

        # Pre-populate L1 with the override, as the estimation hot path would.
        MarkupCache.begin_request(self.tenant.id)
        cached = MarkupCache.resolve(self.tenant, self.customer)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.markup_percentage_micros, 10_000_000)

        resp = self.http_client.delete(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/markup",
            **self._auth())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "deleted")

        # A new request pins whatever version is current in Redis. If delete()
        # bumped it, the stale L1 entry misses on version and resolve() falls
        # through to a live ORM resolve — landing on the tenant default, not
        # the deleted (lower) override.
        MarkupCache.begin_request(self.tenant.id)
        resolved = MarkupCache.resolve(self.tenant, self.customer)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.markup_percentage_micros, 50_000_000)


class UsageEventDetailEndpointTest(TestCase):
    """GET /usage/{event_id} returns the full pricing receipt (provenance)."""

    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="Rcpt", products=["metering"])
        _, self.key = TenantApiKey.create_key(self.tenant, label="r")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.key}"}

    def _event(self, tenant=None, customer=None):
        from apps.metering.usage.models import UsageEvent
        t = tenant or self.tenant
        c = customer or self.customer
        return UsageEvent.objects.create(
            tenant=t, customer=c,
            request_id=f"req-{c.external_id}", idempotency_key=f"idem-{c.external_id}",
            provider_cost_micros=300_000, billed_cost_micros=450_000,
            event_type="chat", provider="openai", units=35_000, currency="usd",
            pricing_provenance={
                "engine_version": "2.1.0",
                "metrics": [{"metric": "input_tokens", "price_card_id": "abc",
                             "units": 35_000, "micros": 450_000}]})

    def test_get_event_returns_full_receipt(self):
        ev = self._event()
        resp = self.http.get(f"/api/v1/metering/usage/{ev.id}", **self._auth())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["id"], str(ev.id))
        self.assertEqual(body["billed_cost_micros"], 450_000)
        self.assertEqual(body["pricing_provenance"]["engine_version"], "2.1.0")
        self.assertEqual(
            body["pricing_provenance"]["metrics"][0]["price_card_id"], "abc")

    def test_get_unknown_event_returns_404(self):
        resp = self.http.get(
            "/api/v1/metering/usage/00000000-0000-0000-0000-000000000000",
            **self._auth())
        self.assertEqual(resp.status_code, 404)

    def test_get_event_of_other_tenant_returns_404(self):
        other = Tenant.objects.create(name="Other", products=["metering"])
        other_cust = Customer.objects.create(tenant=other, external_id="oc")
        ev = self._event(tenant=other, customer=other_cust)
        resp = self.http.get(f"/api/v1/metering/usage/{ev.id}", **self._auth())
        self.assertEqual(resp.status_code, 404)


class MeteringTaskEndpointTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Task Tenant",
            products=["metering"],
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_task_met"
        )

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _task(self, tenant=None, customer=None, balance=20_000_000,
              limit=None, floor=None):
        # One-rule (#37): the tenant-level run-era knobs are gone — limits are
        # passed explicitly at task creation (as billing pre-check does).
        return TaskService.create_task(
            tenant or self.tenant, customer or self.customer,
            balance_snapshot_micros=balance,
            provider_cost_limit_micros=limit,
            floor_snapshot_micros=floor,
            billing_owner_id=(customer or self.customer).id,
        )

    def _record(self, **extra):
        data = {
            "customer_id": str(self.customer.id),
            "request_id": "req_1",
            "idempotency_key": "idem_1",
            "provider_cost_micros": 1_000_000,
        }
        data.update(extra)
        return self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps(data),
            content_type="application/json",
            **self._auth(),
        )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_with_task_id_success(self, mock_process):
        task = self._task()
        resp = self._record(task_id=str(task.id))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["task_id"], str(task.id))
        self.assertEqual(body["task_total_billed_cost_micros"], 1_000_000)
        self.assertEqual(body["task_total_provider_cost_micros"], 1_000_000)
        self.assertFalse(body["stop"])
        self.assertNotIn("hard_stop", body)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_tipping_event_returns_200_and_kills_task(self, mock_process):
        """One-rule (#37): the 429 hard-stop is retired — the tipping event
        answers 200, LANDS, and the stop verdict rides the body while the
        server kills the task."""
        from apps.metering.usage.models import UsageEvent
        from apps.platform.events.models import OutboxEvent

        task = self._task(limit=10_000_000, floor=-5_000_000)
        # First event under limit
        resp = self._record(
            task_id=str(task.id),
            request_id="req_hs1",
            idempotency_key="idem_hs1",
            provider_cost_micros=9_000_000,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["stop"])

        # Second event pushes the PROVIDER total past the 10M ceiling — still
        # 200. The kill executes on the recording transaction's on_commit
        # (#112), which the test transaction never reaches on its own.
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._record(
                task_id=str(task.id),
                request_id="req_hs2",
                idempotency_key="idem_hs2",
                provider_cost_micros=2_000_000,
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["stop"])
        self.assertEqual(body["stop_reason"], "task_limit")
        self.assertEqual(body["stop_scope"], "task")
        self.assertEqual(body["task_total_provider_cost_micros"], 11_000_000)

        # The tipping event landed; the task is killed; the signal fired once.
        self.assertEqual(UsageEvent.objects.filter(tenant=self.tenant).count(), 2)
        task.refresh_from_db()
        self.assertEqual(task.status, "killed")
        self.assertEqual(task.metadata.get("kill_reason"), "task_limit")
        self.assertEqual(task.total_provider_cost_micros, 11_000_000)
        self.assertEqual(OutboxEvent.objects.filter(
            event_type="task.limit_exceeded").count(), 1)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_killed_task_returns_200_task_not_active(self, mock_process):
        """One-rule (#37): the 409 run_not_active is retired — an event for a
        killed task answers 200, lands, bills, and counts; the body carries
        the task_not_active verdict."""
        from apps.metering.usage.models import UsageEvent

        task = self._task()
        TaskService.kill_task(task.id)

        resp = self._record(task_id=str(task.id))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["stop"])
        self.assertEqual(body["stop_reason"], "task_not_active")
        self.assertEqual(body["stop_scope"], "task")

        # Landed and counted into both totals.
        self.assertEqual(UsageEvent.objects.filter(tenant=self.tenant).count(), 1)
        task.refresh_from_db()
        self.assertEqual(task.status, "killed")
        self.assertEqual(task.total_billed_cost_micros, 1_000_000)
        self.assertEqual(task.total_provider_cost_micros, 1_000_000)
        self.assertEqual(task.event_count, 1)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_close_task_success(self, mock_process):
        task = self._task()
        # Record some usage first
        self._record(task_id=str(task.id))

        resp = self.http_client.post(
            f"/api/v1/metering/tasks/{task.id}/close",
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["task_id"], str(task.id))
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["total_billed_cost_micros"], 1_000_000)
        self.assertEqual(body["total_provider_cost_micros"], 1_000_000)
        self.assertEqual(body["event_count"], 1)

    def test_close_task_not_found_returns_404(self):
        import uuid
        resp = self.http_client.post(
            f"/api/v1/metering/tasks/{uuid.uuid4()}/close",
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 404)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_cross_tenant_task_id_is_404_and_not_mutated(self, mock_process):
        other_tenant = Tenant.objects.create(name="Victim", products=["metering"])
        other_customer = Customer.objects.create(tenant=other_tenant, external_id="victim_c")
        victim_task = self._task(tenant=other_tenant, customer=other_customer)
        resp = self._record(task_id=str(victim_task.id), request_id="req_idor1", idempotency_key="idem_idor1")
        self.assertEqual(resp.status_code, 404)
        victim_task.refresh_from_db()
        self.assertEqual(victim_task.total_billed_cost_micros, 0)
        self.assertEqual(victim_task.total_provider_cost_micros, 0)
        self.assertEqual(victim_task.event_count, 0)
        self.assertEqual(victim_task.status, "active")

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_cross_customer_same_tenant_task_id_is_404(self, mock_process):
        cust_b = Customer.objects.create(tenant=self.tenant, external_id="cust_b")
        task_b = self._task(customer=cust_b)
        resp = self._record(task_id=str(task_b.id), request_id="req_idor2", idempotency_key="idem_idor2")
        self.assertEqual(resp.status_code, 404)
        task_b.refresh_from_db()
        self.assertEqual(task_b.total_billed_cost_micros, 0)
        self.assertEqual(task_b.total_provider_cost_micros, 0)
        self.assertEqual(task_b.event_count, 0)
        self.assertEqual(task_b.status, "active")


class MeteringUsageAnalyticsEndpointTest(TestCase):
    def setUp(self):
        from apps.metering.usage.services.usage_service import UsageService

        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Analytics Tenant", products=["metering"],
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c_analytics"
        )
        wallet = Wallet.objects.create(customer=self.customer)
        wallet.balance_micros = 100_000_000
        wallet.save()
        for i in range(3):
            UsageService.record_usage(
                tenant=self.tenant,
                customer=self.customer,
                request_id=f"req_analytics_{i}",
                idempotency_key=f"idem_analytics_{i}",
                provider_cost_micros=1_000_000,
            )

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def test_usage_analytics(self):
        response = self.http_client.get(
            "/api/v1/metering/analytics/usage",
            **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_events"], 3)
        self.assertEqual(body["total_billed_cost_micros"], 3_000_000)

    def test_usage_analytics_dimensions(self):
        from apps.metering.usage.services.usage_service import UsageService
        from apps.metering.pricing.models import TenantMarkup
        # a tenant-default markup so billed > provider (margin is non-zero)
        TenantMarkup.objects.create(tenant=self.tenant, customer=None, markup_percentage_micros=20_000_000)  # 20%
        other = Customer.objects.create(tenant=self.tenant, external_id="c_other")
        UsageService.record_usage(
            tenant=self.tenant, customer=other,
            request_id="req_dim_1", idempotency_key="idem_dim_1",
            provider_cost_micros=2_000_000, tags={"model": "gpt-4"}, product_id="chat",
        )
        response = self.http_client.get(
            "/api/v1/metering/analytics/usage?tag_key=model", **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("usage_markup_margin_micros", body)
        self.assertEqual(
            body["usage_markup_margin_micros"],
            body["total_billed_cost_micros"] - body["total_provider_cost_micros"],
        )
        self.assertTrue(body["by_customer"])      # non-empty
        self.assertTrue(body["by_product"])       # non-empty (the product_id="chat" event)
        self.assertTrue(body["by_tag"])           # non-empty (tag_key=model)
        product_ids = {row["product_id"] for row in body["by_product"]}
        self.assertIn("chat", product_ids)
        tag_values = {row["tag_value"] for row in body["by_tag"]}
        self.assertIn("gpt-4", tag_values)

    def test_metering_only_tenant_gets_403_on_billing_balance(self):
        """Metering-only tenant cannot access billing endpoints."""
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/balance",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    def test_usage_analytics_multi_dimension_breakdown(self):
        from apps.platform.customers.models import Customer
        from apps.metering.usage.models import UsageEvent
        c = Customer.objects.create(tenant=self.tenant, external_id="acme_multi")
        UsageEvent.objects.create(
            tenant=self.tenant, customer=c, request_id="r_md1", idempotency_key="i_md1",
            provider_cost_micros=300_000, billed_cost_micros=500_000, product_id="search",
            service_id="svcA", agent_id="ag1", tags={"region": "us"},
        )
        resp = self.http_client.get(
            f"/api/v1/metering/analytics/usage?customer_id={c.id}"
            "&dimensions=product_id&dimensions=service_id&dimensions=tag:region",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(resp.status_code, 200)
        b = resp.json()["breakdowns"]
        self.assertTrue(
            any(r["dimension"] == "search" and r["total_provider_cost_micros"] == 300_000
                for r in b["product_id"]),
            f"product_id rows: {b.get('product_id')}",
        )
        self.assertTrue(
            any(r["dimension"] == "svcA" and r["total_provider_cost_micros"] == 300_000
                for r in b["service_id"]),
            f"service_id rows: {b.get('service_id')}",
        )
        self.assertTrue(
            any(r["dimension"] == "us" and r["total_provider_cost_micros"] == 300_000
                for r in b["tag:region"]),
            f"tag:region rows: {b.get('tag:region')}",
        )

    def test_usage_analytics_rejects_unknown_dimension(self):
        resp = self.http_client.get(
            "/api/v1/metering/analytics/usage?dimensions=ssn",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(resp.status_code, 422)

    def test_usage_analytics_breakdowns_include_provider_cost(self):
        from apps.metering.usage.models import UsageEvent
        c = Customer.objects.create(tenant=self.tenant, external_id="acme")
        UsageEvent.objects.create(
            tenant=self.tenant, customer=c, request_id="r1", idempotency_key="i1",
            provider_cost_micros=300_000, billed_cost_micros=500_000, product_id="search",
        )
        resp = self.http_client.get(
            f"/api/v1/metering/analytics/usage?customer_id={c.id}",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(
            any(r["customer__external_id"] == "acme" and r["total_provider_cost_micros"] == 300_000
                for r in body["by_customer"]),
            f"by_customer rows: {body['by_customer']}",
        )
        self.assertTrue(
            any(r["product_id"] == "search" and r["total_provider_cost_micros"] == 300_000
                for r in body["by_product"]),
            f"by_product rows: {body['by_product']}",
        )


class RateCardValidationTest(TestCase):
    """Book-centric surface: a BOOK create validates card_type; adding a rate
    validates the pricing_model/tier shape; a publish soft-versions history."""

    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(name="Rate Tenant", products=["metering"])
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")

    def _post(self, path, body):
        return self.client.post(path, data=json.dumps(body),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def _cost_book(self):
        r = self._post("/api/v1/metering/pricing/rate-cards",
                       {"card_type": "cost", "key": "openai", "provider_key": "openai"})
        assert r.status_code == 200, r.content
        return r.json()["id"]

    def test_create_book_rejects_invalid_card_type(self):
        resp = self._post("/api/v1/metering/pricing/rate-cards",
                          {"card_type": "costs", "key": "x"})
        assert resp.status_code == 422

    def test_add_rate_rejects_invalid_pricing_model(self):
        # graduated was deleted end to end (ADR-0003) — not a valid model -> 422.
        book_id = self._cost_book()
        resp = self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}/rates",
                          {"metric_name": "input_tokens", "pricing_model": "graduated"})
        assert resp.status_code == 422

    def test_record_usage_surfaces_uncosted_metrics(self):
        # A metric with NO matching cost card -> the response lists it as uncosted.
        c = Customer.objects.create(tenant=self.tenant, external_id="acme2")
        resp = self.client.post("/api/v1/metering/usage",
            data=json.dumps({"customer_id": str(c.id), "request_id": "r9", "idempotency_key": "i9",
                  "usage_metrics": {"unknown_metric": 100}}),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        assert resp.status_code == 200
        assert "unknown_metric" in resp.json().get("uncosted_metrics", [])

    def test_publish_keeps_lineage_and_versions_history(self):
        # create a cost book + a rate (rate 2)
        book_id = self._cost_book()
        r1 = self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}/rates",
            {"metric_name": "tokens", "pricing_model": "per_unit",
             "rate_per_unit_micros": 2, "unit_quantity": 1})
        assert r1.status_code == 200, r1.content
        rate1 = r1.json(); rid = rate1["id"]; lineage = rate1["lineage_id"]
        # reprice the rate via publish -> new version supersedes the old
        pub = self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}/publish",
            {"changes": [{"metric_name": "tokens", "rate_per_unit_micros": 9}]})
        assert pub.status_code == 200, pub.content
        assert pub.json()["version"] == 2
        # history: both versions, newest first
        h = self.client.get(
            f"/api/v1/metering/pricing/rate-cards/{book_id}/rates?include_history=true",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}").json()["data"]
        assert len(h) == 2
        assert h[0]["rate_per_unit_micros"] == 9 and h[1]["rate_per_unit_micros"] == 2
        assert h[0]["lineage_id"] == lineage and h[1]["lineage_id"] == lineage  # same lineage
        assert h[0]["id"] != rid  # new version row
        # old version has valid_to set; new version valid_to is null
        assert h[1]["valid_to"] is not None and h[0]["valid_to"] is None


class RateCardBatchCreateTest(TestCase):
    """Adding multiple rates under one book (the batch endpoint is gone)."""

    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(name="Batch Rate Tenant", products=["metering"])
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")

    def _post(self, path, body):
        return self.client.post(path, data=json.dumps(body),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def _cost_book(self):
        r = self._post("/api/v1/metering/pricing/rate-cards",
                       {"card_type": "cost", "key": "openai", "provider_key": "openai"})
        assert r.status_code == 200, r.content
        return r.json()["id"]

    def test_add_many_rates_under_a_book(self):
        from apps.metering.pricing.models import Rate
        book_id = self._cost_book()
        r1 = self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}/rates",
            {"metric_name": "tokens", "pricing_model": "per_unit",
             "rate_per_unit_micros": 2, "unit_quantity": 1})
        r2 = self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}/rates",
            {"metric_name": "images", "pricing_model": "flat", "fixed_micros": 500})
        assert r1.status_code == 200 and r2.status_code == 200
        assert Rate.objects.filter(tenant=self.tenant, rate_card_id=book_id).count() == 2

    def test_invalid_rate_creates_nothing(self):
        from apps.metering.pricing.models import Rate
        book_id = self._cost_book()
        before = Rate.objects.filter(tenant=self.tenant).count()
        resp = self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}/rates",
            {"metric_name": "bad", "pricing_model": "package"})  # retired model (ADR-0003)
        assert resp.status_code == 422
        assert Rate.objects.filter(tenant=self.tenant).count() == before  # zero created


class UsageTimeseriesEndpointTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(name="Timeseries Tenant", products=["metering"])
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")

    def test_usage_timeseries_daily_buckets(self):
        import datetime
        from django.utils import timezone
        from apps.platform.customers.models import Customer
        from apps.metering.usage.models import UsageEvent
        c = Customer.objects.create(tenant=self.tenant, external_id="acme")
        for i, day in enumerate([1, 2, 3]):
            e = UsageEvent.objects.create(tenant=self.tenant, customer=c, request_id=f"r{i}",
                idempotency_key=f"i{i}", provider_cost_micros=100_000, billed_cost_micros=150_000)
            UsageEvent.objects.filter(id=e.id).update(
                effective_at=timezone.make_aware(timezone.datetime(2026, 6, day, 12, 0)))
        resp = self.client.get(
            "/api/v1/metering/analytics/usage/timeseries?customer_id=%s&granularity=day&start_date=2026-06-01&end_date=2026-07-01" % c.id,
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        assert resp.status_code == 200
        series = resp.json()["series"]
        assert len(series) == 3
        assert sum(b["provider_cost_micros"] for b in series) == 300_000

    def test_usage_timeseries_invalid_granularity_422(self):
        resp = self.client.get("/api/v1/metering/analytics/usage/timeseries?granularity=year",
                               HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        assert resp.status_code == 422


class DimensionBreakdownReconciliationTest(TestCase):
    """Breakdowns using dimensions=[...] must reconcile to the grand total.

    An event with an empty service_id must NOT be silently excluded; it must
    appear as a '(unattributed)' row so that the sum of the breakdown equals
    the top-line total_provider_cost_micros.
    """

    def setUp(self):
        from apps.metering.usage.models import UsageEvent

        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Reconcile Tenant", products=["metering"]
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c_reconcile"
        )
        # Event 1: has a service tag -> service_id = "svcA"
        UsageEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            request_id="r_rec_1", idempotency_key="i_rec_1",
            provider_cost_micros=100_000, billed_cost_micros=100_000,
            service_id="svcA",
        )
        # Event 2: NO service tag -> service_id is empty string (the default)
        UsageEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            request_id="r_rec_2", idempotency_key="i_rec_2",
            provider_cost_micros=100_000, billed_cost_micros=100_000,
            service_id="",
        )

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def test_empty_service_id_bucketed_as_unattributed(self):
        """The breakdown must contain an '(unattributed)' row for the empty service_id
        event, and the row totals must sum to the overall total_provider_cost_micros."""
        resp = self.http_client.get(
            f"/api/v1/metering/analytics/usage"
            f"?customer_id={self.customer.id}&dimensions=service_id",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        # Grand total is both events combined: 200_000
        grand_total = body["total_provider_cost_micros"]
        self.assertEqual(grand_total, 200_000)

        breakdown = body["breakdowns"]["service_id"]
        dim_map = {row["dimension"]: row["total_provider_cost_micros"] for row in breakdown}

        # The named-service event must still appear
        self.assertIn("svcA", dim_map)
        self.assertEqual(dim_map["svcA"], 100_000)

        # The empty-service event must appear as "(unattributed)"
        self.assertIn("(unattributed)", dim_map, f"breakdown rows: {breakdown}")
        self.assertEqual(dim_map["(unattributed)"], 100_000)

        # The breakdown must reconcile to the grand total
        breakdown_sum = sum(dim_map.values())
        self.assertEqual(
            breakdown_sum, grand_total,
            f"breakdown sum {breakdown_sum} != grand total {grand_total}; rows: {breakdown}",
        )


class RecordUsageCurrencyTest(TestCase):
    """CUR-1 choke point: record_usage rejects any currency that is not the
    tenant's default_currency (case-insensitive); stored normalized lowercase."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="CurTenant", products=["metering"], default_currency="usd")
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="cur")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="cur_c1")

    def _post(self, body):
        return self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps(body),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )

    def _body(self, idem, **extra):
        return {
            "customer_id": str(self.customer.id),
            "request_id": f"req_{idem}",
            "idempotency_key": idem,
            "provider_cost_micros": 1_000_000,
            **extra,
        }

    def test_mismatched_currency_returns_422(self):
        resp = self._post(self._body("cur_mismatch", currency="eur"))
        self.assertEqual(resp.status_code, 422, resp.content)
        self.assertIn("currency mismatch", resp.json()["detail"])
        from apps.metering.usage.models import UsageEvent
        self.assertEqual(UsageEvent.objects.filter(tenant=self.tenant).count(), 0)

    def test_matching_currency_accepted(self):
        resp = self._post(self._body("cur_match", currency="usd"))
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_currency_compare_is_case_insensitive_and_stored_lowercase(self):
        resp = self._post(self._body("cur_case", currency="USD"))
        self.assertEqual(resp.status_code, 200, resp.content)
        from apps.metering.usage.models import UsageEvent
        event = UsageEvent.objects.get(id=resp.json()["event_id"])
        self.assertEqual(event.currency, "usd")

    def test_omitted_currency_defaults_to_tenant_currency(self):
        eur_tenant = Tenant.objects.create(
            name="EurTenant", products=["metering"], default_currency="eur")
        _, eur_key = TenantApiKey.create_key(eur_tenant, label="cur-eur")
        eur_customer = Customer.objects.create(tenant=eur_tenant, external_id="cur_eur1")
        resp = self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps({
                "customer_id": str(eur_customer.id),
                "request_id": "req_eur",
                "idempotency_key": "idem_eur",
                "provider_cost_micros": 1_000_000,
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {eur_key}",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        from apps.metering.usage.models import UsageEvent
        event = UsageEvent.objects.get(id=resp.json()["event_id"])
        self.assertEqual(event.currency, "eur")

    def test_batch_item_currency_mismatch_is_per_item_validation_error(self):
        resp = self.http_client.post(
            "/api/v1/metering/usage/batch",
            data=json.dumps({"events": [
                self._body("cur_batch_ok"),
                self._body("cur_batch_bad", currency="eur"),
            ]}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["accepted"], 1)
        self.assertEqual(body["rejected"], 1)
        self.assertTrue(body["results"][0]["accepted"])
        self.assertEqual(body["results"][1]["code"], "validation_error")
        self.assertIn("currency mismatch", body["results"][1]["detail"])
