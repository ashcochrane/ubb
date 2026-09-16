"""The discovery contract, through its route (#498, slice 7 §6 and §7).

**Tested through the route rather than through the read contract**, which is the
slice's own seam rule: a read contract tested only directly is a contract
nothing holds to its published shape. The one thing asserted at the function is
the refusal, and it has its own module beside the read contract — the surface
that expresses a grouping request against a set of measures arrives with the one
economic query, so there is no route here that can express the combination yet.

⚠ **THIS MODULE NEVER SPELLS THE FOUR PARAMETERS THIS VOCABULARY REPLACES.** The
registry retires them and the sweep refuses a living file that names one, so the
only honest source is the document that retired them — `_helpers.retired_aliases`
reads them off it. Declarations are made against the model for the same reason:
the existing write route spells a retired word in its own request body.
"""
import inspect

import pytest
from django.test import Client
from django.utils import timezone

from api.v1.tests._helpers import retired_aliases
from apps.subscriptions.api.margin_endpoints import business_margin
from apps.metering.queries import (
    GRAIN_MEASUREMENT, GROUPING_GRAINS, GROUPING_KIND_SEPARATOR,
    GROUPING_SURFACES, SURFACE_ANALYTICS, SURFACE_INVOICE_LINES,
    grouping_refusal,
)
from apps.platform.customers.models import Customer
from apps.platform.grouping_fields.models import GroupingField
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.metering.usage.models import Posting
from core.vocabulary import (
    ANALYTICS_GROUPING_KIND_FIELD, ANALYTICS_GROUPING_KIND_ROLLUP,
    ANALYTICS_MEASURE_CUSTOMER_REVENUE, ANALYTICS_MEASURE_GROSS_MARGIN,
    ANALYTICS_MEASURE_RECORDED_EVENTS,
    ANALYTICS_MEASURE_SUPPLIER_COGS, ANALYTICS_ROLLUP_EVENT_CATEGORY,
    ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT,
)

OPTIONS = "/api/v1/metering/analytics/grouping-options"

#: The axes every posting carries, which is what makes them not a catalogue: a
#: catalogue is a list of VALUES UBB would be shipping on a tenant's behalf, and
#: these are columns. Spelled here rather than imported so that the read
#: contract's own list is asserted against something and not against itself.
ALWAYS_PRESENT = ["field:customer", "field:provider", "field:event_type",
                  "field:task_type", "field:subtask_type"]
ROLLUPS = ["rollup:event_category", "rollup:measurement_concept"]


def a_tenant(name, *, fields=()):
    """A metering tenant and a raw key for it, with its declarations made.

    `products=["metering"]` is not optional — the route is product-gated, so a
    tenant without it answers 403 rather than 200, which reads as an auth bug.
    """
    tenant = Tenant.objects.create(name=name, products=["metering"])
    for position, (key, scope, cap) in enumerate(fields, start=1):
        GroupingField.objects.create(tenant=tenant, key=key,
                                     slot=f"grouping_field_{position}",
                                     scope=scope, max_cardinality=cap)
    _, raw_key = TenantApiKey.create_key(tenant)
    return tenant, raw_key


def read(raw_key, path=OPTIONS):
    return Client().get(path, HTTP_AUTHORIZATION=f"Bearer {raw_key}")


@pytest.mark.django_db
class TestItIsComputedForOneTenantAndNotShipped:
    """UBB ships no catalogue and its registries start empty, so an answer that
    did not vary by tenant would be UBB shipping one."""

    def test_it_answers_with_this_tenants_declarations_and_the_two_ubb_rollups(self):
        _, key = a_tenant("T", fields=[("region", "task", 20),
                                       ("model_family", "event", 100)])
        response = read(key)
        assert response.status_code == 200
        assert [option["key"] for option in response.json()["options"]] == (
            ALWAYS_PRESENT + ["field:region", "field:model_family"] + ROLLUPS)

    def test_a_second_tenant_with_different_declarations_gets_a_different_answer(self):
        _, first = a_tenant("First", fields=[("region", "task", 20)])
        _, second = a_tenant("Second", fields=[("deployment", "event", 5)])
        assert [o["key"] for o in read(first).json()["options"]] != (
            [o["key"] for o in read(second).json()["options"]])
        assert "field:region" not in {o["key"] for o in read(second).json()["options"]}

    def test_a_tenant_that_has_declared_nothing_gets_the_columns_and_the_rollups(self):
        """An empty registry is every tenant on day one, and the answer is still
        useful: the axes every posting carries are columns rather than a
        catalogue, and the two rollups are UBB's own."""
        _, key = a_tenant("Fresh")
        assert [o["key"] for o in read(key).json()["options"]] == (
            ALWAYS_PRESENT + ROLLUPS)

    def test_a_retired_field_is_still_offered_because_its_history_is_grouped_by_it(self):
        """Retirement blocks new VALUES, never reads (ADR-0005 D8). A posting
        recorded before its field was retired must still be groupable, so an
        axis that can still answer is still offered."""
        tenant, key = a_tenant("T", fields=[("region", "task", 20)])
        GroupingField.objects.filter(tenant=tenant, key="region").update(
            retired_at=timezone.now())
        assert "field:region" in {o["key"] for o in read(key).json()["options"]}

    def test_no_axis_carries_another_tenants_declaration(self):
        _, first = a_tenant("First", fields=[("region", "task", 20)])
        a_tenant("Second", fields=[("deployment", "event", 5)])
        assert "field:deployment" not in {o["key"] for o in read(first).json()["options"]}


@pytest.mark.django_db
class TestEveryRowIsInterpretableFromRawHttp:
    """Map #137 constraint 6 limits the Code Builder to the Python SDK and raw
    HTTP, and the generator reads this contract — so a shape needing a typed
    client to interpret makes the builder's input unusable."""

    def test_every_option_carries_the_whole_row(self):
        _, key = a_tenant("T", fields=[("region", "task", 20)])
        for option in read(key).json()["options"]:
            assert set(option) == {"key", "kind", "rollup", "label",
                                   "source_grain", "supported_surfaces",
                                   "max_cardinality", "unsupported_measures"}
            assert option["kind"] in (ANALYTICS_GROUPING_KIND_FIELD,
                                      ANALYTICS_GROUPING_KIND_ROLLUP)
            assert option["source_grain"] in GROUPING_GRAINS
            assert option["supported_surfaces"]
            assert set(option["supported_surfaces"]) <= set(GROUPING_SURFACES)

    def test_the_request_word_carries_its_kind_and_the_row_states_it_too(self):
        """§6: the kind is part of the request vocabulary rather than metadata
        beside it — and the row states it separately so that READING the
        contract needs no string splitting."""
        _, key = a_tenant("T", fields=[("region", "task", 20)])
        for option in read(key).json()["options"]:
            kind, separator, name = option["key"].partition(
                GROUPING_KIND_SEPARATOR)
            assert separator and name
            assert kind == option["kind"]

    def test_a_rollup_names_which_one_and_a_field_names_none(self):
        _, key = a_tenant("T", fields=[("region", "task", 20)])
        rollups = {o["key"]: o["rollup"] for o in read(key).json()["options"]}
        assert rollups["rollup:event_category"] == ANALYTICS_ROLLUP_EVENT_CATEGORY
        assert (rollups["rollup:measurement_concept"]
                == ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT)
        assert rollups["field:region"] is None
        assert rollups["field:provider"] is None

    def test_the_tenants_own_word_is_published_and_ubbs_wording_is_not(self):
        """ADR-0008 §4: the registry owns identity and the localisation layer
        owns expression. A tenant's key has nowhere else to come from; deriving
        "Event Category" from a token would be UBB manufacturing user-facing
        terminology out of an implementation token, which that section names as
        a defect by that exact example."""
        _, key = a_tenant("T", fields=[("region", "task", 20)])
        labels = {o["key"]: o["label"] for o in read(key).json()["options"]}
        assert labels["field:region"] == "region"
        assert labels["rollup:event_category"] == ""
        assert labels["field:provider"] == ""

    def test_a_declared_field_publishes_the_cap_the_tenant_set(self):
        """§7 makes cardinality one of the three things a request is validated
        against, and the invoice-line surface warns from this same read."""
        _, key = a_tenant("T", fields=[("region", "task", 7)])
        caps = {o["key"]: o["max_cardinality"] for o in read(key).json()["options"]}
        assert caps["field:region"] == 7
        assert caps["field:provider"] is None
        assert caps["rollup:event_category"] is None

    def test_the_parameters_this_vocabulary_replaces_are_retired_to_it(self):
        """The registry names the bespoke per-surface parameters as retiring to
        this concept, and none of them is a word this vocabulary answers to.

        Read off the registry rather than spelled: a living file that named one
        would fail the sweep before any of this ran.
        """
        retired = retired_aliases("economics", "analytics_grouping_kind")
        # PINNED, not floored. `>= 3` passes when one alias is swapped for
        # another, which is exactly the edit that would quietly drop a door
        # from the list of what this vocabulary replaced.
        assert len(retired) == 3
        _, key = a_tenant("T", fields=[("region", "task", 20)])
        offered = {o["key"] for o in read(key).json()["options"]}
        assert offered.isdisjoint(retired)
        # And each one is refused as a request word rather than merely absent:
        # they were bare axis names, so they earn the sentence that teaches the
        # shape instead of a "you have not declared that" that would read as a
        # missing declaration.
        for door in retired:
            assert "names no grouping kind" in grouping_refusal(
                Tenant.objects.get(name="T").id, axes=[door])


@pytest.mark.django_db
class TestTheMeasurementRollupShipsNarrowed:
    """§7's ruling: the axis ships supporting measurement quantities with the
    component-grain cost declared unsupported and the reason stated. Declaring
    an unsupported measure is the honest answer the mechanism was built to
    express, and is strictly better than an axis that ships and is quietly
    unusable at volume."""

    def _measurement_rollup(self):
        _, key = a_tenant("T")
        return next(o for o in read(key).json()["options"]
                    if o["key"] == "rollup:measurement_concept")

    def test_it_declares_every_money_measure_unsupported_with_its_reason(self):
        """⚠ **#499 COMPLETED THIS DECLARATION AND THIS CASE MOVED WITH IT.**
        It used to pin the list at the supplier cost alone, because #498 could
        name only one measure without making the read the measure concept's
        serving consumer and paying #499's ledger entry by mention. The reason
        was never about cost: UBB holds an amount per POSTING on both sides of
        the margin, so revenue at this grain repeats one event's price once per
        quantity, and a margin over two repeated figures repeats it twice.
        """
        refused = self._measurement_rollup()["unsupported_measures"]
        assert [r["measure"] for r in refused] == [
            ANALYTICS_MEASURE_SUPPLIER_COGS, ANALYTICS_MEASURE_CUSTOMER_REVENUE,
            ANALYTICS_MEASURE_GROSS_MARGIN]
        for entry in refused:
            assert "per posting" in entry["reason"] or "per measurement" in entry["reason"]
            assert "measurement" in entry["reason"]

    def test_the_count_is_what_survives_the_narrowing(self):
        """The axis is not refused outright, which would be the shortfall §7
        rules against: the count reaches it, because it counts the POSTINGS a
        heading reaches rather than the measurement records."""
        refused = {r["measure"] for r in
                   self._measurement_rollup()["unsupported_measures"]}
        assert ANALYTICS_MEASURE_RECORDED_EVENTS not in refused

    def test_it_resolves_at_the_measurement_grain_and_groups_quantities_there(self):
        """It groups measurement RECORDS rather than events, which is why the
        grain is its own and why the cost above cannot be answered at it without
        repeating one event's whole cost against every quantity it carries."""
        assert self._measurement_rollup()["source_grain"] == GRAIN_MEASUREMENT

    def test_it_is_absent_from_the_surface_where_a_line_is_money(self):
        option = self._measurement_rollup()
        assert option["supported_surfaces"] == [SURFACE_ANALYTICS]
        assert SURFACE_INVOICE_LINES not in option["supported_surfaces"]

    def test_no_other_axis_refuses_a_measure(self):
        """The narrowing is one line of one axis, not a general retreat: every
        other axis accepts every measure and answers with its own state."""
        _, key = a_tenant("T", fields=[("region", "task", 20)])
        refusing = {o["key"] for o in read(key).json()["options"]
                    if o["unsupported_measures"]}
        assert refusing == {"rollup:measurement_concept"}


@pytest.mark.django_db
class TestTheBusinessTreeTakesNoRollupAxis:
    """§14: rollups sit ALONGSIDE the business/seat tree, never inside it. A
    tree and a group-by table are different shapes — which is the whole reason
    that tree keeps its own contract — and making the tree take a rollup axis
    re-opens the collapse this slice exists to close."""

    def test_the_tree_declares_no_grouping_parameter_at_all(self):
        """⚠ **THE CLAIM IS THAT THERE IS NO PARAMETER, NOT THAT ONE IS
        IGNORED.** Driving `?group_by=rollup:event_category` at the route and
        finding the answer unchanged proves nothing on its own: django-ninja
        discards a query parameter an operation does not declare, so that
        assertion passes identically on `origin/main`, and with `?foo=bar`. It
        is kept below as corroboration; THIS is the test AC 6 asks for, read off
        the live router rather than off the source.
        """
        signature = inspect.signature(business_margin)
        assert set(signature.parameters) == {"request", "external_id",
                                             "start_date", "end_date"}

    def test_and_the_tree_answers_the_same_when_one_is_asked_for_anyway(self):
        """Corroboration for the test above, with a tree that has something in
        it: a rollup axis cannot change a figure it was never able to reach."""
        tenant, key = a_tenant("T")
        business = Customer.objects.create(tenant=tenant, external_id="biz",
                                           account_type="business")
        seat = Customer.objects.create(tenant=tenant, external_id="seat",
                                       account_type="seat", parent=business)
        Posting.objects.create(tenant=tenant, customer=seat,
                               idempotency_key="i1",
                               billed_cost_micros=3_000_000,
                               provider_cost_micros=1_000_000)
        tree = "/api/v1/margin/business/biz"
        plain = read(key, tree)
        assert plain.status_code == 200
        assert plain.json()["totals"]["gross_margin_micros"] == 2_000_000
        with_axis = read(key, f"{tree}?group_by=rollup:event_category")
        assert with_axis.json() == plain.json()

    def test_the_declared_surfaces_are_the_two_that_take_an_axis(self):
        """§14: rollups sit ALONGSIDE the tree. The tree is not a surface an
        axis may declare, and the vocabulary of surfaces is where that is true
        — asserting each row's list against the same tuple the rows are built
        from would be asserting the definition.
        """
        assert set(GROUPING_SURFACES) == {SURFACE_ANALYTICS,
                                          SURFACE_INVOICE_LINES}
        _, key = a_tenant("T", fields=[("region", "task", 20)])
        offered = {surface for option in read(key).json()["options"]
                   for surface in option["supported_surfaces"]}
        assert offered == {SURFACE_ANALYTICS, SURFACE_INVOICE_LINES}
