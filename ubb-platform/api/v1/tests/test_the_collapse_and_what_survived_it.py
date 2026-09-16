"""Nine published routes stop existing, and three things do not (#501, slice 7 §1).

**The break block says nine paths and nine operations; this says the same thing
from the other side.** A generated document is a claim about what a server
serves, and a path that answers 200 while the document omits it is the failure
mode a removal has — so both halves are asked here: the published document has
no operation at that path, and a properly authenticated request to it 404s.

⚠ **AND THE HARDER HALF IS WHAT SURVIVED.** Three things sit close enough to the
nine to be swept away with them, and each would be a silent capability loss:

* **the count of unprofitable customers**, which the tenant-wide margin total
  published beside its figures. It reads the ALERTING record rather than a
  margin, so under §8 it belongs with the alerting surfaces that keep their own
  contracts. Deleting it with the route is the defect §8 exists to prevent,
  wearing the opposite sign.
* **the per-customer event list**, which is a FILTER surface rather than a
  grouping one. It returns paginated event ROWS, and no combination of
  parameters makes the one query return those — the one query returns grouped
  measures. Collapsing it would remove the only per-customer event listing on
  the contract.
* **the surfaces §14 names**: the business/seat tree (a tree, not a group-by
  table), the task cost distribution (one observation per unit of work, not per
  posting) and slice 6's two spend-control reports, inherited unchanged.

⚠ **THIS MODULE NEVER SPELLS A RETIRED GROUPING PARAMETER.** Their ceiling is a
SPREAD ceiling — a new file naming one fails `term_spread` before any payment is
attempted — so the two the collapse takes away are read off the registry that
retired them, through `_helpers.retired_aliases`.
"""
import datetime

import pytest
from django.test import Client
from django.utils import timezone

from api.v1.tests._helpers import retired_aliases
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work.models import Task
from apps.subscriptions.economics.models import CustomerEconomics
from core.widget_auth import create_widget_token

#: The nine, and what each one answered. The list is the ticket's table, in its
#: order, because a reader checking the break block against this file should be
#: able to read them side by side.
THE_NINE = {
    "/api/v1/metering/analytics/usage":
        "the usage analytics report — totals, four fixed breakdown blocks and "
        "several ad-hoc ones",
    "/api/v1/metering/analytics/usage/timeseries":
        "its timeseries sibling — the same totals, bucketed by day or hour",
    "/api/v1/margin/by-grouping-field":
        "the grouped margin breakdown — the same rows and the same arithmetic "
        "as the metering rollup, over a silently different revenue basis",
    "/api/v1/billing/analytics/revenue":
        "the billing revenue report — a tenant-wide duplicate of the timeseries",
    "/api/v1/margin/customers":
        "the per-customer margin list",
    "/api/v1/margin/customers/{customer_id}":
        "one customer's margin",
    "/api/v1/margin/customers/{customer_id}/trend":
        "one customer's margin trend, read out of the alerting snapshot",
    "/api/v1/me/usage-summary":
        "the customer-scoped usage summary, on the widget mount",
    "/api/v1/margin/summary":
        "the tenant-wide margin total — the degenerate case of the one query",
}

#: The surfaces §14 keeps, by published path. Named positively rather than left
#: to the absence above: a removal that took one of these would satisfy every
#: assertion about the nine.
THE_SURVIVORS = (
    "/api/v1/metering/customers/{customer_id}/usage",
    "/api/v1/metering/analytics/tasks",
    "/api/v1/metering/analytics/economics",
    "/api/v1/metering/analytics/grouping-options",
    "/api/v1/margin/business/{external_id}",
    "/api/v1/margin/unprofitable",
    "/api/v1/margin/threshold",
    "/api/v1/spend-controls/stops-and-breaches",
    "/api/v1/spend-controls/utilisation-and-headroom",
    # ⚠ NOT A SURVIVOR — AN ADDITION. It is in this list because the list's job
    # is to say what a caller can still reach, and this is the one path the
    # collapse had to put back; the class below says why.
    "/api/v1/platform/customers/{customer_id}",
)

#: The fused field the usage report published, and the timeseries' and revenue
#: report's names for the same subtraction. It was never a markup and never a
#: margin — it was billed minus supplier cost over a window — and after this
#: slice that difference is the gross-margin measure, computed at a bucket and
#: carrying its own state.
THE_FUSED_NAMES = ("usage_markup_margin_micros", "total_markup_micros",
                   "markup_micros")

#: The metering analytics operations that survive. The retired grouping
#: parameters must not appear on any of them: the per-customer event list keeps
#: one of those words as a FILTER, which is a different capability and is why
#: this claim is scoped to the analytics surfaces rather than to the tree.
SURVIVING_ANALYTICS = ("/api/v1/metering/analytics/economics",
                       "/api/v1/metering/analytics/tasks",
                       "/api/v1/metering/analytics/grouping-options")


def published():
    """The live document, off the API rather than off the committed file.

    The committed `openapi/v1.json` is regenerated from this, so reading the
    file would test the export step; what is asked here is what the server
    publishes.
    """
    from api.v1.api import api

    return api.get_openapi_schema()


def a_tenant():
    tenant = Tenant.objects.create(name="Collapse", products=["metering"])
    _, raw_key = TenantApiKey.create_key(tenant)
    return tenant, raw_key


@pytest.mark.django_db
class TestTheNinePathsAreGone:
    """One case per path, parametrized so a survivor names itself in the test
    id rather than hiding inside a list of nine."""

    @pytest.fixture(autouse=True)
    def fixture(self):
        self.tenant, self.key = a_tenant()
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")

    @pytest.mark.parametrize("path", sorted(THE_NINE))
    def test_the_document_publishes_no_operation_there(self, path):
        assert path not in published()["paths"], (
            f"{path} is still published — it answered: {THE_NINE[path]}")

    @pytest.mark.parametrize("path", sorted(THE_NINE))
    def test_an_authenticated_request_finds_nothing_there(self, path):
        """⚠ AUTHENTICATED ON PURPOSE, because an unauthenticated 404 proves
        nothing about the path: the interesting failure is a route that outlived
        its removal from the document, and a caller who cannot get past the door
        would see the same status either way.

        The widget-mounted one is the exception and takes a real widget token
        for the same reason — with the route present, a caller without one got
        401, so a 404 here is the path resolving to nothing rather than auth
        answering first.
        """
        concrete = path.replace("{customer_id}", str(self.customer.id))
        if concrete.startswith("/api/v1/me/"):
            token = create_widget_token(self.tenant.widget_secret,
                                        str(self.customer.id),
                                        str(self.tenant.id))
            header = f"Bearer {token}"
        else:
            header = f"Bearer {self.key}"

        response = Client().get(concrete, HTTP_AUTHORIZATION=header)

        assert response.status_code == 404, (
            f"{path} still answers {response.status_code}")

    @pytest.mark.parametrize("path", THE_SURVIVORS)
    def test_the_surfaces_that_keep_their_contracts_still_do(self, path):
        assert path in published()["paths"], (
            f"{path} left the contract, and no ticket asked for that")


@pytest.mark.django_db
class TestTheUnprofitableCountDidNotDieWithTheTotal:
    """AC 2: it survives on an alerting surface and still reads the alerting
    record.

    The tenant-wide margin total published this count beside three money
    figures, and it was the one field on that response that was not a margin: it
    counts customers a threshold rule has NAMED, which is stored alerting state
    maintained by the evaluator. So it moves with the alerting surfaces rather
    than with the reports.
    """

    @pytest.fixture(autouse=True)
    def fixture(self):
        self.tenant, self.key = a_tenant()
        self.unprofitable = Customer.objects.create(
            tenant=self.tenant, external_id="losing")
        self.fine = Customer.objects.create(tenant=self.tenant,
                                            external_id="winning")

    def _named(self, customer, *, unprofitable, margin_micros):
        return CustomerEconomics.objects.create(
            tenant=self.tenant, customer=customer,
            period_start="2026-03-01", period_end="2026-04-01",
            provider_cost_micros=1_000_000,
            usage_billed_micros=0 if unprofitable else 9_000_000,
            gross_margin_micros=margin_micros,
            margin_percentage=-50 if unprofitable else 50,
            is_unprofitable=unprofitable)

    def _count(self):
        response = Client().get(
            "/api/v1/margin/unprofitable?period_start=2026-03-01",
            HTTP_AUTHORIZATION=f"Bearer {self.key}")
        assert response.status_code == 200, response.content
        return len(response.json()["customers"])

    def test_the_count_is_still_readable_after_the_total_went(self):
        self._named(self.unprofitable, unprofitable=True,
                    margin_micros=-1_000_000)
        self._named(self.fine, unprofitable=False, margin_micros=8_000_000)

        assert self._count() == 1

    def test_it_reads_the_alerting_record_and_not_a_margin_figure(self):
        """THE DISCRIMINATING CASE, and the reason this is a test rather than a
        comment.

        A customer whose stored margin is NEGATIVE but which the evaluator has
        not named is not on the list, and a customer the evaluator HAS named is
        on it whatever its margin reads. That is what *reads the alerting
        record* means: the flag is the fact, and a count derived from the
        arithmetic instead would disagree with the webhook the tenant was sent.
        """
        self._named(self.unprofitable, unprofitable=True,
                    margin_micros=4_000_000)
        self._named(self.fine, unprofitable=False, margin_micros=-7_000_000)

        assert self._count() == 1
        listed = Client().get(
            "/api/v1/margin/unprofitable?period_start=2026-03-01",
            HTTP_AUTHORIZATION=f"Bearer {self.key}").json()["customers"]
        assert listed[0]["external_id"] == "losing"


@pytest.mark.django_db
class TestThePerCustomerEventListStillReturnsEvents:
    """AC 3: it keeps its route because no question the one query answers
    returns event rows.

    It is in no parity row of the matrix, and the reason is that it is not a
    report: it filters and pages the postings themselves. The one query returns
    grouped MEASURES — one row per bucket per group — so there is no parameter
    combination that would make it serve this.
    """

    @pytest.fixture(autouse=True)
    def fixture(self):
        self.tenant, self.key = a_tenant()
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")
        for index in range(3):
            Posting.objects.create(
                tenant=self.tenant, customer=self.customer,
                idempotency_key=f"i{index}", event_type="chat.completion",
                billed_cost_micros=1_000 * (index + 1))

    def test_it_returns_paginated_event_rows(self):
        response = Client().get(
            f"/api/v1/metering/customers/{self.customer.id}/usage",
            HTTP_AUTHORIZATION=f"Bearer {self.key}")

        assert response.status_code == 200, response.content
        body = response.json()
        assert set(body) >= {"data", "has_more"}, body
        assert len(body["data"]) == 3
        # Rows, not groups: each one carries the identity of a single recorded
        # posting, which is the whole difference from a measure row.
        assert len({row["id"] for row in body["data"]}) == 3

    def test_it_still_filters_those_rows_by_unit_of_work(self):
        """Moved here from the module that tested it beside the collapsed
        report's own filters (#501). The listing keeps every filter it had;
        what it never had, and still does not, is a grouping."""
        task = Task.objects.create(tenant=self.tenant, customer=self.customer,
                                   balance_snapshot_micros=0,
                                   task_type="invoice_batch")
        under_the_task = Posting.objects.create(
            tenant=self.tenant, customer=self.customer, idempotency_key="t1",
            event_type="chat.completion", task_id=task.id,
            billed_cost_micros=9_000)

        response = Client().get(
            f"/api/v1/metering/customers/{self.customer.id}/usage",
            {"task_id": str(task.id)},
            HTTP_AUTHORIZATION=f"Bearer {self.key}")

        assert response.status_code == 200, response.content
        # The one posting under that unit of work, and not the three beside it.
        assert [row["id"] for row in response.json()["data"]] == [
            str(under_the_task.id)]

    def test_the_one_query_answers_measures_and_never_rows(self):
        """The other half of the claim, asserted rather than asserted-about.

        The reply to *why does this route survive* is that its answer is a
        different KIND of thing. So the one query is asked the nearest question
        it can be asked — everything filtered to this one customer — and what
        comes back is measure rows with no event identity on them.
        """
        response = Client().get(
            "/api/v1/metering/analytics/economics",
            {"measures": "supplier_cogs", "customer_id": str(self.customer.id)},
            HTTP_AUTHORIZATION=f"Bearer {self.key}")

        assert response.status_code == 200, response.content
        for row in response.json()["rows"]:
            assert set(row) == {"bucket_start", "grouping_field_value",
                                "grouping_field_value_status", "measures"}


@pytest.mark.django_db
class TestTheOneCapabilityTheCollapseHadToPutBack:
    """⚠ **THE COLLAPSE TOOK AWAY THE ONLY READ THAT ANSWERED "WHO IS THIS
    CUSTOMER?", AND THIS IS WHERE IT WENT.**

    One customer's margin published `external_id` beside its figures, and that
    was the single place on the contract mapping the identity UBB assigned a
    customer to the word the tenant uses for them. The one economic query groups
    by IDENTITY and publishes no external id — a tenant's own vocabulary is not
    a measure, and a report is not a directory — so the capability was never the
    report's to hold, and it is now `GET /platform/customers/{customer_id}`.

    It is load-bearing rather than cosmetic: the subscription lifecycle is
    addressed by the EXTERNAL id and every metering and billing read by the
    UUID, so a surface holding one and needing the other has nowhere else to go.
    """

    @pytest.fixture(autouse=True)
    def fixture(self):
        self.tenant, self.key = a_tenant()
        self.business = Customer.objects.create(
            tenant=self.tenant, external_id="acme-corp",
            account_type="business", billing_topology="pooled")
        self.seat = Customer.objects.create(
            tenant=self.tenant, external_id="acme-corp:eng",
            account_type="seat", parent=self.business)

    def _get(self, customer, key=None):
        return Client().get(f"/api/v1/platform/customers/{customer.id}",
                            HTTP_AUTHORIZATION=f"Bearer {key or self.key}")

    def test_it_answers_the_id_the_tenant_gave_the_customer(self):
        response = self._get(self.business)

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["id"] == str(self.business.id)
        assert body["external_id"] == "acme-corp"

    def test_a_seat_names_the_business_it_belongs_to(self):
        """A seat's bill is its business's, and a caller that had to ask a
        second question to find that out would be one round trip from rendering
        a seat as if it paid its own way."""
        body = self._get(self.seat).json()

        assert body["account_type"] == "seat"
        assert body["parent_external_id"] == "acme-corp"

    def test_a_customer_with_no_business_names_none(self):
        """The discriminating half: an empty string here is a fact, and a
        fixture where every customer had a parent could not tell it from a
        lookup that always answered one."""
        alone = Customer.objects.create(tenant=self.tenant, external_id="solo")

        assert self._get(alone).json()["parent_external_id"] == ""

    def test_it_answers_about_identity_and_never_about_money(self):
        """⚠ THE LINE THIS ROUTE EXISTS TO KEEP. It was added because a REPORT
        was carrying identity; adding a figure back to it would recreate the
        coupling the collapse removed, one mount over."""
        body = self._get(self.business).json()

        assert not [key for key in body if key.endswith("_micros")], body

    def test_another_tenants_customer_is_not_found(self):
        stranger, _ = a_tenant()
        theirs = Customer.objects.create(tenant=stranger, external_id="theirs")

        assert self._get(theirs).status_code == 404


@pytest.mark.django_db
class TestWhatDiedWithTheRoutesStaysDead:
    """AC 4: the fused field and the free-text-key breakdown are gone, and
    nothing reintroduces either."""

    def test_no_published_schema_carries_the_fused_field(self):
        """Walked structurally rather than grepped, because the question is
        about the document's shape: a property of one of these names is a field
        a generated client would still expose."""
        document = published()
        carried = []

        def walk(node, pointer=""):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "properties" and isinstance(value, dict):
                        carried.extend(f"{pointer}/{name}" for name in value
                                       if name in THE_FUSED_NAMES)
                    walk(value, f"{pointer}/{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{pointer}/{index}")

        walk(document)
        assert not carried, (
            "the difference between two aggregates is published under a name "
            "that suggests a rate again:\n" + "\n".join(carried))

    def test_no_surviving_analytics_operation_takes_a_retired_grouping_word(
            self):
        """The free-text-key breakdown, and the ad-hoc axis list beside it.

        ⚠ SCOPED TO THE ANALYTICS SURFACES AND NOT TO THE TREE. One of these
        words survives as a FILTER on the per-customer event list — filtering by
        a key out of the open bag is a different capability from GROUPING by
        one, and #501 takes away only the second. A tree-wide assertion would
        condemn a spelling this ticket does not own.
        """
        retired = retired_aliases("economics", "analytics_grouping_kind")
        document = published()
        offenders = []
        for path in SURVIVING_ANALYTICS:
            assert path in document["paths"], f"{path} is not published"
            for method, operation in document["paths"][path].items():
                for parameter in operation.get("parameters", []):
                    if parameter["name"] in retired:
                        offenders.append(
                            f"{method.upper()} {path} — {parameter['name']}")

        assert not offenders, (
            "a surviving analytics operation publishes a grouping parameter "
            "the registry retired:\n" + "\n".join(offenders))

    def test_the_words_this_case_is_about_are_really_retired(self):
        """The vacuity guard. An absence proved against an empty list of words
        is no proof, and the walk that reads them is a line walk over a YAML
        file that a reformat could quietly empty."""
        retired = retired_aliases("economics", "analytics_grouping_kind")

        assert len(retired) >= 3, retired


def months_back(count):
    """The first day of each of the last `count` months, oldest first.

    Walked from today rather than written as literals: a fixed month would put
    this module's data outside the six-year economic horizon eventually, and
    outside the 366-day request bound long before that.
    """
    first = timezone.now().date().replace(day=1)
    months = [first]
    for _ in range(count - 1):
        first = (first - datetime.timedelta(days=1)).replace(day=1)
        months.insert(0, first)
    return months


@pytest.mark.django_db
class TestTheTrendIsTheSameQuestionWithABucket:
    """AC 1, the third of its four subjects: one customer's margin by month.

    The route this replaces (`/margin/customers/{id}/trend`) had ONE test, and
    it asserted a status code, an echoed id and the presence of a `points` key —
    a routing test written when #86 moved the path, never a test of the trend.
    Migrating it faithfully means asking the same QUESTION rather than copying
    the same assertions, so this one puts real money in three different months
    and requires the answer to separate them.

    ⚠ **THE TREND IS NOT A REPORT HERE, IT IS A BUCKET.** That is the whole
    of what the collapse claims about it: the question "what did this customer
    earn me, month by month" is the tenant-wide question with a filter and a
    `bucket`, and nothing about it needed its own route, its own response schema
    or its own definition of margin.
    """

    #: Cost and revenue per month, oldest first — three distinct pairs, so a
    #: bucket landing in the wrong month cannot produce the right answer.
    BY_MONTH = ((100_000, 400_000), (200_000, 500_000), (300_000, 900_000))

    @pytest.fixture(autouse=True)
    def fixture(self):
        self.tenant, self.key = a_tenant()
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")
        self.other = Customer.objects.create(tenant=self.tenant,
                                             external_id="c2")
        self.months = months_back(len(self.BY_MONTH))
        for month, (cost, revenue) in zip(self.months, self.BY_MONTH):
            for customer in (self.customer, self.other):
                # The second customer exists to be EXCLUDED, so it carries the
                # same figures: a filter that silently did nothing would still
                # produce plausible months.
                posting = Posting.objects.create(
                    tenant=self.tenant, customer=customer,
                    idempotency_key=f"i-{customer.external_id}-{month}",
                    event_type="chat.completion",
                    provider_cost_micros=cost, billed_cost_micros=revenue)
                Posting.objects.filter(id=posting.id).update(
                    effective_at=timezone.make_aware(datetime.datetime(
                        month.year, month.month, 2, 12, 0, 0)))

    def _ask(self, **extra):
        params = {"measures": ["supplier_cogs", "customer_revenue",
                               "gross_margin"],
                  "start_date": self.months[0].isoformat(),
                  "end_date": timezone.now().date().isoformat(),
                  **extra}
        response = Client().get("/api/v1/metering/analytics/economics", params,
                                HTTP_AUTHORIZATION=f"Bearer {self.key}")
        assert response.status_code == 200, response.content
        return response.json()

    def _amounts(self, body):
        return {row["bucket_start"][:7]:
                {entry["measure"]: entry["amount_micros"]
                 for entry in row["measures"]}
                for row in body["rows"]}

    def test_one_customers_figures_arrive_month_by_month(self):
        body = self._ask(bucket="month", customer_id=str(self.customer.id))

        assert body["bucket"] == "month", body["bucket"]
        by_month = self._amounts(body)
        assert len(by_month) == len(self.BY_MONTH), by_month
        for month, (cost, revenue) in zip(self.months, self.BY_MONTH):
            row = by_month[month.isoformat()[:7]]
            assert row["supplier_cogs"] == cost, (month, row)
            assert row["customer_revenue"] == revenue, (month, row)
            # ⚠ SUBTRACTED AT THE BUCKET, which is the one arithmetic rule
            # the deleted trend could get wrong and this one cannot: each
            # month's margin is that month's two totals and no other month's.
            assert row["gross_margin"] == revenue - cost, (month, row)

    def test_the_filter_is_what_makes_it_one_customers_trend(self):
        """The same request without the filter answers about both customers,
        which is the only thing that proves the filter did the narrowing."""
        one = self._amounts(self._ask(bucket="month",
                                      customer_id=str(self.customer.id)))
        both = self._amounts(self._ask(bucket="month"))

        assert set(one) == set(both), (one, both)
        for month in one:
            assert both[month]["supplier_cogs"] == 2 * one[month]["supplier_cogs"]

    def test_without_a_bucket_the_same_question_is_one_row(self):
        """And the trend and the total are one question at two grains — the
        claim that let the per-customer total and its trend be one route."""
        body = self._ask(customer_id=str(self.customer.id))

        assert body["bucket"] is None, body["bucket"]
        assert len(body["rows"]) == 1, body["rows"]
        whole = {entry["measure"]: entry["amount_micros"]
                 for entry in body["rows"][0]["measures"]}
        assert whole["supplier_cogs"] == sum(cost for cost, _ in self.BY_MONTH)
        assert whole["customer_revenue"] == sum(rev for _, rev in self.BY_MONTH)


@pytest.mark.django_db
class TestTheCustomerScopedSummaryIsTheSameQuestionFiltered:
    """AC 1, the fourth subject: what one customer used, broken down by kind.

    `GET /me/usage-summary` answered an end customer holding a widget token with
    a month-to-date rollup of its own usage, one row per Event Type. Its three
    cases are migrated here as the questions they asked, against the one query.

    ⚠⚠ **AND THE ANSWER IS REACHABLE WHILE THE CALLER IS NOT, WHICH IS
    A REAL LOSS AND IS RECORDED RATHER THAN PAPERED OVER.** That route stood on
    the WIDGET mount: its caller was an end customer with a widget token, not
    the tenant. The one query is on the tenant mount at the Read floor, so every
    question below is answerable — by the tenant. A widget holder cannot ask
    it. `me_endpoints.py` carries the same statement where the route used to be;
    restoring a customer-facing rollup is a widget-surface ticket's, and #501
    neither does it nor pretends the collapse did.
    """

    @pytest.fixture(autouse=True)
    def fixture(self):
        self.tenant, self.key = a_tenant()
        self.business = Customer.objects.create(
            tenant=self.tenant, external_id="biz", account_type="business")
        self.seat_a = Customer.objects.create(
            tenant=self.tenant, external_id="seat-a", account_type="seat",
            parent=self.business)
        self.seat_b = Customer.objects.create(
            tenant=self.tenant, external_id="seat-b", account_type="seat",
            parent=self.business)
        self._event(self.seat_a, "a1", event_type="tokens", billed=100_000)
        self._event(self.seat_b, "b1", event_type="tokens", billed=200_000)
        self._event(self.seat_b, "b2", event_type="images", billed=1_000_000)

    def _event(self, customer, key, *, event_type, billed):
        return Posting.objects.create(
            tenant=self.tenant, customer=customer, idempotency_key=f"i-{key}",
            event_type=event_type, billed_cost_micros=billed)

    def _ask(self, **params):
        response = Client().get(
            "/api/v1/metering/analytics/economics",
            {"measures": ["customer_revenue"], **params},
            HTTP_AUTHORIZATION=f"Bearer {self.key}")
        assert response.status_code == 200, response.content
        return response.json()

    def _by_kind(self, body):
        return {row["grouping_field_value"][0]:
                next(entry["amount_micros"] for entry in row["measures"]
                     if entry["measure"] == "customer_revenue")
                for row in body["rows"]}

    def test_one_customer_sees_only_its_own_rollup(self):
        """`test_seat_sees_only_its_own_rollup`, asked of the one query."""
        by_kind = self._by_kind(self._ask(customer_id=str(self.seat_a.id),
                                          group_by="field:event_type"))

        assert by_kind == {"tokens": 100_000}, by_kind

    def test_the_kinds_are_an_axis_rather_than_a_response_shape(self):
        """The rollup's `metrics` list was a shape only that route published;
        here it is a grouping, so the same request answers the whole tenant."""
        by_kind = self._by_kind(self._ask(group_by="field:event_type"))

        assert by_kind == {"tokens": 300_000, "images": 1_000_000}, by_kind

    def test_a_business_does_not_absorb_its_seats_and_the_tree_still_does(self):
        """`test_business_token_aggregates_seats` is the one case that does NOT
        migrate, and the honest answer is that it moved rather than collapsed.

        A filter names a customer; it does not walk a topology. So the business
        answers for its OWN postings — of which it has none — and the
        surface that answers across a business and its seats is the business/seat
        tree (`GET /margin/business/{external_id}`), which §14 keeps
        untouched and `THE_SURVIVORS` asserts is still published.
        """
        body = self._ask(customer_id=str(self.business.id),
                         group_by="field:event_type")

        assert body["rows"] == [], body["rows"]

    def test_the_default_window_is_the_month_to_date(self):
        """`test_prior_month_event_excluded`, and it pins the default the
        deleted rollup had: a question with no dates is this month's."""
        stale = self._event(self.seat_a, "old", event_type="tokens",
                            billed=990_000)
        first_of_month = timezone.now().date().replace(day=1)
        Posting.objects.filter(id=stale.id).update(
            effective_at=timezone.make_aware(datetime.datetime.combine(
                first_of_month - datetime.timedelta(days=2),
                datetime.time(12, 0))))

        default = self._ask(customer_id=str(self.seat_a.id))
        assert default["period_start"] == first_of_month.isoformat()
        assert self._by_kind(
            self._ask(customer_id=str(self.seat_a.id),
                      group_by="field:event_type")) == {"tokens": 100_000}

        # And it is excluded by the WINDOW rather than missing: name a window
        # that reaches it and the same question answers about it.
        named = self._ask(
            customer_id=str(self.seat_a.id), group_by="field:event_type",
            start_date=(first_of_month - datetime.timedelta(days=3)).isoformat(),
            end_date=timezone.now().date().isoformat())
        assert self._by_kind(named) == {"tokens": 1_090_000}
