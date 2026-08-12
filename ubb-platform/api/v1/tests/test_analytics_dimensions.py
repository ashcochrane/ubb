"""Task 15: analytics on declared grouping fields, filter by task.

Grouping now speaks the tenant's own vocabulary (registry-resolved), not a
hardcoded column allowlist. Bounded grouping fields can be grouped by; unbounded
correlation identifiers (task_id) can only be filtered (design D9).

**THE WIRE-KEY PINS AT THE BOTTOM LIVE HERE FOR A REASON.** They belong to the
two analytics rollups that return an open dict, and one of them is reached by a
request parameter whose word is retired under slice 7's ledger entry. A new test
module naming that parameter would push a recorded extent wider, which the sweep
refuses — the same constraint `test_grouping_values_on_the_contract.py` records
for the same reason. This module already carries the word, so the pins cost the
ledger nothing by sitting beside the behaviour they describe.
"""
from datetime import datetime, timezone

import pytest
from django.test import Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.metering.usage.models import Posting
from apps.platform.grouping_fields.models import GroupingField
from apps.platform.work.models import Task


@pytest.mark.django_db
class TestAnalyticsDimensions:
    def setup_method(self):
        # products=[...] is REQUIRED — routes are gated by _product_check.
        # /margin/* needs "subscriptions" as well as "metering".
        self.tenant = Tenant.objects.create(
            # No "subscriptions": plan-as-kernel (#129) retired it from
            # VALID_PRODUCTS, and margin_endpoints is gated on "metering".
            name="T", products=["metering", "billing"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.client = Client()

    def _get(self, path):
        return self.client.get(path, HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def _seed(self):
        GroupingField.objects.create(tenant=self.tenant, key="region", slot="grouping_field_1",
                                    scope="task")
        parent = Task.objects.create(tenant=self.tenant, customer=self.customer,
                                     balance_snapshot_micros=0,
                                     task_type="invoice_batch")
        sub = Task.objects.create(tenant=self.tenant, customer=self.customer,
                                  parent=parent,
                                  balance_snapshot_micros=0, subtask_type="ocr")
        for i, (task, dim1, cost) in enumerate([
                (parent, "eu-west-1", 1_000), (sub, "eu-west-1", 2_000),
                (sub, "us-east-1", 4_000)]):
            Posting.objects.create(
                tenant=self.tenant, customer=self.customer, request_id=f"r{i}",
                idempotency_key=f"k{i}", provider="aws_textract",
                event_type="ocr_page", task_id=task.id,
                task_type="invoice_batch",
                subtask_type=task.subtask_type, grouping_field_1=dim1,
                provider_cost_micros=cost, billed_cost_micros=cost * 2)
        return parent, sub

    def test_group_by_declared_key_name(self):
        self._seed()
        r = self._get("/api/v1/metering/analytics/usage?dimensions=region")
        assert r.status_code == 200
        rows = {x["grouping_field_value"]: x["total_provider_cost_micros"]
                for x in r.json()["breakdowns"]["region"]}
        assert rows == {"eu-west-1": 3_000, "us-east-1": 4_000}

    def test_group_by_reserved_subtask_type(self):
        self._seed()
        r = self._get("/api/v1/metering/analytics/usage?dimensions=subtask_type")
        rows = {x["grouping_field_value"]: x["total_provider_cost_micros"]
                for x in r.json()["breakdowns"]["subtask_type"]}
        assert rows == {"ocr": 6_000, "(unattributed)": 1_000}

    def test_undeclared_key_is_422(self):
        self._seed()
        r = self._get("/api/v1/metering/analytics/usage?dimensions=nope")
        assert r.status_code == 422
        assert "unknown grouping field" in r.json()["detail"]

    def test_task_id_as_a_grouping_axis_is_422(self):
        """Correlation ids are filter-only (design D9) — grouping by one would
        build a bucket per run."""
        self._seed()
        r = self._get("/api/v1/metering/analytics/usage?dimensions=task_id")
        assert r.status_code == 422

    def test_task_id_filter_scopes_to_one_unit(self):
        parent, sub = self._seed()
        r = self._get(f"/api/v1/metering/analytics/usage?task_id={parent.id}")
        assert r.json()["total_provider_cost_micros"] == 1_000

    def test_include_subtasks_rolls_the_tree_up(self):
        parent, sub = self._seed()
        r = self._get(f"/api/v1/metering/analytics/usage?task_id={parent.id}"
                      "&include_subtasks=true")
        assert r.json()["total_provider_cost_micros"] == 7_000

    def test_usage_list_filters_by_task(self):
        parent, sub = self._seed()
        r = self._get(f"/api/v1/metering/customers/{self.customer.id}/usage"
                      f"?task_id={sub.id}")
        assert len(r.json()["data"]) == 2

    def test_margin_group_by_any_declared_key(self):
        self._seed()
        r = self._get("/api/v1/margin/by-grouping-field?group_by=subtask_type")
        assert r.status_code == 200
        assert {x["grouping_field_value"] for x in r.json()["rows"]} == {"ocr"}


@pytest.mark.django_db
class TestTheOpenAnalyticsRowsNameTheirGroupedValue:
    """Both open-dict rollups name a row's grouped value what the contract does.

    `/margin/by-grouping-field` DECLARES its rows, and its published property is
    `grouping_field_value` (`MarginRowOut`, `openapi/v1.json`). These two rollups
    answer the same question about the same axes — including the reserved ones,
    which that route already covers — and return `list[dict]`, so nothing in the
    schema, the drift gate or the breaking gate can hold them to it. This class
    is what holds them to it.

    **EVERY ASSERTION IS A WHOLE ROW, and that is the point of the class.** A key
    lookup (`row["grouping_field_value"]`) passes whatever the row is called as
    long as the test and the code agree, which is exactly the agreement that was
    wrong before: a renamed read plus a renamed write agree with each other and
    disagree with the console. Equality against a literal dict fails on a key
    added, a key dropped and a key renamed alike, so the console's two constants
    and the SDK's README can be checked against something.

    The seed is deliberately ONE posting on ONE day: a whole-row assertion is
    only readable if every number in it is a value somebody chose.
    """

    def setup_method(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.client = Client()
        GroupingField.objects.create(tenant=self.tenant, key="region",
                                     slot="grouping_field_1", scope="task")
        Posting.objects.create(
            tenant=self.tenant, customer=self.customer, request_id="r0",
            idempotency_key="k0", provider="aws_textract", event_type="ocr_page",
            grouping_field_1="eu-west-1",
            effective_at=datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc),
            provider_cost_micros=1_000, billed_cost_micros=3_000)

    def _get(self, path):
        return self.client.get(path, HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def test_the_usage_breakdown_row_is_exactly_this(self):
        r = self._get("/api/v1/metering/analytics/usage?dimensions=region")
        assert r.status_code == 200
        assert r.json()["breakdowns"] == {"region": [{
            "grouping_field_value": "eu-west-1",
            "event_count": 1,
            "total_provider_cost_micros": 1_000,
            "total_billed_cost_micros": 3_000,
        }]}

    def test_the_timeseries_bucket_row_is_exactly_this(self):
        """The second site, written independently of the first.

        `apps/metering/queries.py` builds this row and `api/v1/metering_endpoints.py`
        builds the one above; neither reads the other's spelling, which is why
        one pin cannot stand for both.
        """
        r = self._get("/api/v1/metering/analytics/usage/timeseries"
                      "?granularity=day&group_by=region")
        assert r.status_code == 200
        assert r.json()["series"] == [{
            "bucket": "2026-05-04",
            "grouping_field_value": "eu-west-1",
            "provider_cost_micros": 1_000,
            "billed_cost_micros": 3_000,
            "markup_micros": 2_000,
            "event_count": 1,
        }]

    def test_the_timeseries_omits_the_key_when_nothing_was_grouped(self):
        """The absence is part of the shape the SDK's samples document.

        Without `group_by` there is no grouped value, so the key is not present
        rather than present-and-empty — which is why the README reads it with
        `.get` and why an over-eager rename could not simply add the new key
        beside the old one.
        """
        r = self._get("/api/v1/metering/analytics/usage/timeseries?granularity=day")
        assert r.status_code == 200
        assert r.json()["series"] == [{
            "bucket": "2026-05-04",
            "provider_cost_micros": 1_000,
            "billed_cost_micros": 3_000,
            "markup_micros": 2_000,
            "event_count": 1,
        }]
