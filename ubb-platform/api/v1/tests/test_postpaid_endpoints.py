import json
from django.test import TestCase, Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer


class PostpaidEndpointsTest(TestCase):
    def setUp(self):
        from apps.platform.grouping_fields.services import DimensionService
        self.http = Client()
        self.tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
        # The invoice-line grouping is an axis this tenant declared (#503), so
        # the two the config tests below send have to exist.
        for key, slot in (("product_id", "grouping_field_1"),
                          ("model", "grouping_field_2")):
            DimensionService.declare(self.tenant, key=key, slot=slot,
                                     scope="event")
        _, self.key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.key}"}

    def test_list_customer_usage_invoices_empty(self):
        r = self.http.get(f"/api/v1/billing/customers/{self.customer.id}/usage-invoices", **self._auth())
        assert r.status_code == 200
        assert r.json() == {"data": [], "next_cursor": None, "has_more": False}

    def test_usage_invoice_listed_after_create(self):
        import datetime
        from apps.billing.invoicing.models import CustomerUsageInvoice
        CustomerUsageInvoice.objects.create(tenant=self.tenant, customer=self.customer,
            period_start=datetime.date(2026, 6, 1), period_end=datetime.date(2026, 7, 1),
            total_billed_micros=1_000_000, currency="usd", status="pushed")
        r = self.http.get(f"/api/v1/billing/customers/{self.customer.id}/usage-invoices", **self._auth())
        assert r.status_code == 200
        b = r.json()
        rows = b["data"]
        assert b["has_more"] is False
        assert len(rows) == 1 and rows[0]["total_billed_micros"] == 1_000_000 and rows[0]["status"] == "pushed"

    def test_tenant_usage_invoices(self):
        r = self.http.get("/api/v1/billing/tenant/usage-invoices?period=2026-06", **self._auth())
        assert r.status_code == 200
        body = r.json()
        assert set(body) == {"data", "next_cursor", "has_more"}

    def test_tenant_usage_invoices_bad_period_is_a_400_problem(self):
        r = self.http.get("/api/v1/billing/tenant/usage-invoices?period=junk", **self._auth())
        assert r.status_code == 400
        assert r["Content-Type"] == "application/problem+json"
        assert r.json()["code"] == "bad_request"

    def test_postpaid_config_get_put(self):
        r = self.http.get("/api/v1/billing/postpaid-config", **self._auth())
        assert r.status_code == 200 and r.json()["usage_line_item_group_by"] == ""
        assert r.json()["consolidate_with_subscription"] is False
        r = self.http.put("/api/v1/billing/postpaid-config",
                          data=json.dumps({"usage_line_item_group_by": "field:product_id"}),
                          content_type="application/json", **self._auth())
        assert r.status_code == 200
        r = self.http.get("/api/v1/billing/postpaid-config", **self._auth())
        assert r.json()["usage_line_item_group_by"] == "field:product_id"

    def test_postpaid_config_consolidation_flag_roundtrip(self):
        r = self.http.put("/api/v1/billing/postpaid-config",
                          data=json.dumps({"usage_line_item_group_by": "field:product_id",
                                           "consolidate_with_subscription": True}),
                          content_type="application/json", **self._auth())
        assert r.status_code == 200 and r.json()["consolidate_with_subscription"] is True
        # F5.5: a group_by-only PUT (flag omitted) must NOT flip the opt-in off.
        r = self.http.put("/api/v1/billing/postpaid-config",
                          data=json.dumps({"usage_line_item_group_by": "field:model"}),
                          content_type="application/json", **self._auth())
        assert r.status_code == 200
        body = r.json()
        assert body["usage_line_item_group_by"] == "field:model"
        assert body["consolidate_with_subscription"] is True
        # An explicit false switches it off.
        r = self.http.put("/api/v1/billing/postpaid-config",
                          data=json.dumps({"usage_line_item_group_by": "field:model",
                                           "consolidate_with_subscription": False}),
                          content_type="application/json", **self._auth())
        assert r.json()["consolidate_with_subscription"] is False


class InvoiceLineGroupingIsChosenFromTheDiscoveryContractTest(TestCase):
    """What a tenant may configure, and what UBB tells them at the moment they do.

    #503, slice 7 §11. The value is one axis of the SAME vocabulary every chart
    uses, reached through metering's `queries.py` read contract — so the refusal
    is the one every other surface gives, and the warning is the one the
    discovery contract said only this surface could give.
    """

    def setUp(self):
        from apps.platform.grouping_fields.services import DimensionService
        self.http = Client()
        self.tenant = Tenant.objects.create(
            name="T", products=["metering", "billing"])
        DimensionService.declare(self.tenant, key="region",
                                 slot="grouping_field_1", scope="event",
                                 max_cardinality=2)
        _, self.key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.key}"}

    def _put(self, axis):
        return self.http.put(
            "/api/v1/billing/postpaid-config",
            data=json.dumps({"usage_line_item_group_by": axis}),
            content_type="application/json", **self._auth())

    def _a_posting(self, key, region):
        from apps.metering.usage.models import Posting
        return Posting.objects.create(
            tenant=self.tenant, customer=self.customer, idempotency_key=key,
            billed_cost_micros=1_000, grouping_field_1=region)

    def _last_audit_metadata(self):
        from apps.platform.audit.models import AuditRecord
        return (AuditRecord.objects.filter(tenant_id=self.tenant.id,
                                           action="postpaid_config.set")
                .order_by("-created_at").first().metadata)

    def test_a_word_with_no_kind_is_refused(self):
        """The free-text hatch, closed at the door a tenant writes through."""
        r = self._put("region")
        assert r.status_code == 422
        assert r.json()["code"] == "validation_error"
        assert "grouping kind" in r.json()["detail"]

    def test_an_axis_this_tenant_never_declared_is_refused(self):
        r = self._put("field:not_declared")
        assert r.status_code == 422
        assert "declared" in r.json()["detail"]

    def test_an_axis_that_cannot_label_money_is_refused(self):
        """The measurement-concept rollup groups records BENEATH an event, and
        UBB holds money per posting — so it is not offered on this surface, and
        the discovery contract is what says so rather than a list kept here."""
        r = self._put("rollup:measurement_concept")
        assert r.status_code == 422
        assert "invoice_lines" in r.json()["detail"]

    def test_a_declared_axis_is_accepted_and_stored(self):
        """THE OTHER DIRECTION — without it, a route that refused everything
        would pass all three tests above."""
        r = self._put("field:region")
        assert r.status_code == 200
        assert r.json()["usage_line_item_group_by"] == "field:region"

    def test_an_axis_inside_its_declared_maximum_warns_about_nothing(self):
        self._a_posting("i1", "emea")
        self._a_posting("i2", "apac")

        assert self._put("field:region").status_code == 200
        assert "invoice_line_cardinality_warning" not in self._last_audit_metadata()

    def test_an_axis_past_its_declared_maximum_warns_AT_configuration_time(self):
        """The whole point of the timing: the tenant hears it while choosing,
        not when a 5,000-line invoice has already reached their customer.

        It is a WARNING — the write succeeds — because the declared maximum is
        a keyspace bound the tenant set on their own axis, not an invariant UBB
        may decline to bill against.
        """
        for index, region in enumerate(("emea", "apac", "amer")):
            self._a_posting(f"i{index}", region)

        response = self._put("field:region")

        assert response.status_code == 200
        assert response.json()["usage_line_item_group_by"] == "field:region"
        warning = self._last_audit_metadata()["invoice_line_cardinality_warning"]
        assert "more than 2 distinct values" in warning

    def test_the_warning_is_not_deferred_to_the_invoice(self):
        """The claim the test above cannot make on its own: the same tenant, the
        same axis, and NO postings yet — so nothing warns. The warning tracks
        what the axis has recorded rather than firing on the choice itself,
        which is what makes its arrival informative."""
        assert self._put("field:region").status_code == 200
        assert self._last_audit_metadata() == {
            "usage_line_item_group_by": "field:region",
            "consolidate_with_subscription": False,
        }
