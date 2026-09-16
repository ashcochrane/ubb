"""The grouping contract at the read contract (#498, slice 7 §6, §7 and §14).

**What is asserted HERE rather than through a route**, and why each one has to
be: the slice's seam rule puts everything a caller can observe on the route, and
the route module beside this one does that. Three claims have no route yet or no
route ever.

* **The refusal.** The surface that expresses a grouping request against a set of
  measures is the one economic query, and it arrives in the next ticket. Until
  it does there is no route that can express the combination, so the refusal is
  driven at the function it will call.
* **The join.** A rollup resolves an identity to a heading. Nothing publishes
  the mapping itself and nothing should — it is what the grouping reads, not
  what a tenant asks for — so it is asserted where it lives.
* **Neither kind ever selects a rule.** That is a property of the tree rather
  than of a response: no route could show it, because the whole claim is that
  there is no route.

⚠ **THIS MODULE NEVER SPELLS THE PARAMETERS THIS VOCABULARY REPLACES.** The
registry retires them, the sweep refuses a living file that names one, and a new
file spelling one fails before any of this runs.
"""
import ast
import uuid
from pathlib import Path

import pytest
from django.test import TestCase
from django.utils import timezone

from apps.metering.pricing.models import Charge, Rate
from apps.metering.queries import (
    SURFACE_ANALYTICS, SURFACE_INVOICE_LINES, grouping_axis, grouping_options,
    grouping_refusal, parse_grouping_axis, rollup_membership,
)
from apps.metering.usage.models import Posting, PostingMeasurement
from apps.platform.customers.models import Customer
from apps.platform.event_types.models import (
    EventCategory, EventType, Measurement, MeasurementConcept)
from apps.platform.grouping_fields.models import GroupingField
from apps.platform.tenants.models import Tenant
from apps.platform.work.models import Task
from core.vocabulary import (
    ANALYTICS_GROUPING_KIND_FIELD, ANALYTICS_GROUPING_KIND_ROLLUP,
    ANALYTICS_MEASURE_CUSTOMER_REVENUE, ANALYTICS_MEASURE_GROSS_MARGIN,
    ANALYTICS_MEASURE_RECORDED_EVENTS, ANALYTICS_MEASURE_SUPPLIER_COGS,
    ANALYTICS_ROLLUP_EVENT_CATEGORY, ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT,
    COSTING_METHOD_CALCULATED, SOURCE_KIND_CALLER_SUPPLIED, UNIT_TOKEN,
)

MEASUREMENT_ROLLUP = grouping_axis(ANALYTICS_GROUPING_KIND_ROLLUP,
                                   ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT)
CATEGORY_ROLLUP = grouping_axis(ANALYTICS_GROUPING_KIND_ROLLUP,
                                ANALYTICS_ROLLUP_EVENT_CATEGORY)


class TheRefusalNamesWhatItRefused(TestCase):
    """§7: the query validates against the discovery contract and rejects
    invalid combinations rather than returning subtly misleading data.

    *A caveat a client may ignore is a caveat that will be ignored, and that is
    how three free-text hatches survived ADR-0005 in the first place* — and a
    refusal a client cannot act on is the same failure one step later. Each
    assertion below therefore checks what the sentence NAMES, not just that
    there was one.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="T", products=["metering"])
        GroupingField.objects.create(tenant=cls.tenant, key="region",
                                     slot="grouping_field_1", scope="task")

    def test_a_declared_axis_with_an_accepted_measure_is_not_refused(self):
        assert grouping_refusal(
            self.tenant.id, axes=["field:region", CATEGORY_ROLLUP],
            measures=[ANALYTICS_MEASURE_SUPPLIER_COGS]) is None

    def test_a_word_carrying_no_kind_is_refused_and_both_forms_are_named(self):
        """The bare axis name is what all four retired parameters took, so the
        refusal has to teach the shape rather than say 'invalid'."""
        refusal = grouping_refusal(self.tenant.id, axes=["region"])
        assert "'region'" in refusal
        assert f"{ANALYTICS_GROUPING_KIND_FIELD}:" in refusal
        assert f"{ANALYTICS_GROUPING_KIND_ROLLUP}:" in refusal

    def test_a_kind_the_registry_does_not_declare_is_refused_the_same_way(self):
        refusal = grouping_refusal(self.tenant.id, axes=["column:region"])
        assert "names no grouping kind" in refusal

    def test_an_axis_this_tenant_has_not_declared_is_refused_by_name(self):
        refusal = grouping_refusal(self.tenant.id, axes=["field:deployment"])
        assert refusal == ("'field:deployment' is not a grouping axis this "
                           "tenant has declared")

    def test_another_tenants_declaration_is_not_this_tenants_axis(self):
        other = Tenant.objects.create(name="Other", products=["metering"])
        GroupingField.objects.create(tenant=other, key="deployment",
                                     slot="grouping_field_1", scope="event")
        assert grouping_refusal(self.tenant.id, axes=["field:deployment"])
        assert grouping_refusal(other.id, axes=["field:deployment"]) is None

    def test_a_measure_an_axis_declares_unsupported_names_the_axis_and_the_measure(self):
        """And carries the axis's OWN declared reason through, read off the
        discovery contract rather than quoted here — a literal would go stale
        the moment the sentence is reworded, and the claim is that the two
        agree, not that either says any particular thing."""
        option = next(o for o in grouping_options(self.tenant.id)
                      if o["key"] == MEASUREMENT_ROLLUP)
        declared = next(r for r in option["unsupported_measures"]
                        if r["measure"] == ANALYTICS_MEASURE_SUPPLIER_COGS)
        refusal = grouping_refusal(
            self.tenant.id, axes=[MEASUREMENT_ROLLUP],
            measures=[ANALYTICS_MEASURE_SUPPLIER_COGS])
        assert ANALYTICS_MEASURE_SUPPLIER_COGS in refusal
        assert MEASUREMENT_ROLLUP in refusal
        assert declared["reason"] in refusal

    def test_every_money_measure_is_refused_at_that_axis(self):
        """⚠ **THE DECLARATION WAS COMPLETED IN #499 AND THIS CASE MOVED WITH
        IT.** It used to assert that the customer revenue WAS answerable here,
        because #498 could name only one measure — naming all of them would have
        made this read the measure concept's serving consumer and paid #499's
        ledger entry by mention — and it said so at the time. The reason written
        at that axis was never about cost: UBB holds an amount per POSTING on
        both sides of the margin, so revenue at this grain repeats one event's
        price once per quantity exactly as a supplier cost would.
        """
        for measure in (ANALYTICS_MEASURE_SUPPLIER_COGS,
                        ANALYTICS_MEASURE_CUSTOMER_REVENUE,
                        ANALYTICS_MEASURE_GROSS_MARGIN):
            refusal = grouping_refusal(self.tenant.id,
                                       axes=[MEASUREMENT_ROLLUP],
                                       measures=[measure])
            assert refusal is not None, measure
            assert measure in refusal and MEASUREMENT_ROLLUP in refusal

    def test_the_axis_is_not_refused_outright(self):
        """The narrowing is a set of measures, not the axis. An axis refused
        outright would be the shortfall §7 rules against — and the count is what
        survives, because it counts the POSTINGS a heading reaches rather than
        the measurement records, so it keeps the one meaning it has everywhere.
        """
        assert grouping_refusal(
            self.tenant.id, axes=[MEASUREMENT_ROLLUP],
            measures=[ANALYTICS_MEASURE_RECORDED_EVENTS]) is None

    def test_an_axis_is_refused_on_a_surface_that_does_not_take_it(self):
        refusal = grouping_refusal(self.tenant.id, axes=[MEASUREMENT_ROLLUP],
                                   surface=SURFACE_INVOICE_LINES)
        assert refusal == (f"'{MEASUREMENT_ROLLUP}' is not available on "
                           f"'{SURFACE_INVOICE_LINES}'")
        assert grouping_refusal(self.tenant.id, axes=[MEASUREMENT_ROLLUP],
                                surface=SURFACE_ANALYTICS) is None

    def test_the_first_unanswerable_axis_is_the_one_reported(self):
        """One sentence, about one axis: a caller fixes what it is told about
        and asks again, which is what makes the message actionable."""
        refusal = grouping_refusal(self.tenant.id,
                                   axes=["field:deployment", "field:elsewhere"])
        assert "deployment" in refusal and "elsewhere" not in refusal


class TheOneRequestWord(TestCase):
    """§6: the kind is part of the request vocabulary, not metadata beside it."""

    def test_a_word_is_built_and_read_back_by_the_same_module(self):
        word = grouping_axis(ANALYTICS_GROUPING_KIND_FIELD, "region")
        assert word == "field:region"
        assert parse_grouping_axis(word) == (ANALYTICS_GROUPING_KIND_FIELD,
                                             "region")

    def test_a_word_with_no_kind_reads_back_as_nothing(self):
        assert parse_grouping_axis("region") is None

    def test_a_word_with_a_kind_the_registry_does_not_declare_reads_back_as_nothing(self):
        assert parse_grouping_axis("column:region") is None

    def test_a_kind_with_no_axis_after_it_reads_back_as_nothing(self):
        assert parse_grouping_axis("field:") is None

    def test_a_declared_key_holding_the_separator_still_reads_back_whole(self):
        """UBB invented no charset for a tenant's own key — the registry says so
        at the column, because a charset UBB invented would be UBB
        second-guessing a tenant's catalogue. So the split is at the FIRST
        separator and everything after it is the name."""
        word = grouping_axis(ANALYTICS_GROUPING_KIND_FIELD, "eu:west")
        assert parse_grouping_axis(word) == (ANALYTICS_GROUPING_KIND_FIELD,
                                             "eu:west")


class ADeclaredKeyIsTakenAsTheTenantSpelledIt(TestCase):
    """The round trip through the read contract, not just through the pair of
    functions: a key UBB would have had to invent a charset to refuse is offered
    and accepted under the tenant's own spelling."""

    def test_a_key_holding_the_separator_is_offered_and_accepted(self):
        tenant = Tenant.objects.create(name="T", products=["metering"])
        GroupingField.objects.create(tenant=tenant, key="eu:west",
                                     slot="grouping_field_1", scope="event")
        assert "field:eu:west" in {option["key"] for option
                                   in grouping_options(tenant.id)}
        assert grouping_refusal(tenant.id, axes=["field:eu:west"]) is None


class TheJoinIsReadLive(TestCase):
    """A rollup is a controlled mapping from an identity the tenant already
    declared to a broader analytical heading, and it is resolved when it is
    read — which is what makes changing one reclassify history."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="T", products=["metering"])
        cls.generation = EventCategory.objects.create(tenant=cls.tenant,
                                                      key="generation")
        cls.event_type = EventType.objects.create(
            tenant=cls.tenant, key="chat.completion",
            costing_method=COSTING_METHOD_CALCULATED,
            category=cls.generation)
        EventType.objects.create(tenant=cls.tenant, key="unfiled.call",
                                 costing_method=COSTING_METHOD_CALCULATED)
        cls.tokens = MeasurementConcept.objects.create(tenant=cls.tenant,
                                                       key="tokens_in")
        Measurement.objects.create(event_type=cls.event_type,
                                   code="prompt_tokens", unit=UNIT_TOKEN,
                                   source_kind=SOURCE_KIND_CALLER_SUPPLIED,
                                   concept=cls.tokens)
        Measurement.objects.create(event_type=cls.event_type,
                                   code="unfiled_quantity", unit=UNIT_TOKEN,
                                   source_kind=SOURCE_KIND_CALLER_SUPPLIED)

    def test_it_answers_the_tenants_own_spellings_on_both_sides(self):
        assert rollup_membership(
            self.tenant.id, ANALYTICS_ROLLUP_EVENT_CATEGORY) == {
                "chat.completion": "generation"}
        assert rollup_membership(
            self.tenant.id, ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT) == {
                ("chat.completion", "prompt_tokens"): "tokens_in"}

    def test_one_name_declared_twice_may_be_filed_two_ways_and_both_survive(self):
        """A declaration is Event-Type-local, so a matching name never proves
        equivalence and a tenant may file two same-named quantities under
        different headings. Keyed by the code alone, one of these would have to
        be dropped — and whichever went would quietly file one Event Type's
        quantity under the other's heading."""
        elsewhere = EventType.objects.create(
            tenant=self.tenant, key="embedding.create",
            costing_method=COSTING_METHOD_CALCULATED)
        other = MeasurementConcept.objects.create(tenant=self.tenant,
                                                  key="embedding_input")
        Measurement.objects.create(event_type=elsewhere, code="prompt_tokens",
                                   unit=UNIT_TOKEN,
                                   source_kind=SOURCE_KIND_CALLER_SUPPLIED,
                                   concept=other)
        assert rollup_membership(
            self.tenant.id, ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT) == {
                ("chat.completion", "prompt_tokens"): "tokens_in",
                ("embedding.create", "prompt_tokens"): "embedding_input"}

    def test_an_identity_filed_under_nothing_is_absent_rather_than_sentinelled(self):
        """The axis is opt-in on both sides, so 'nobody has filed this' and
        'this is filed under nothing' are the same fact — and a sentinel would
        be the bucket §5 forbids, one layer down."""
        membership = rollup_membership(self.tenant.id,
                                       ANALYTICS_ROLLUP_EVENT_CATEGORY)
        assert "unfiled.call" not in membership
        assert "" not in membership.values()
        quantities = rollup_membership(self.tenant.id,
                                       ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT)
        assert ("chat.completion", "unfiled_quantity") not in quantities
        assert "" not in quantities.values()

    def test_it_answers_for_one_tenant(self):
        other = Tenant.objects.create(name="Other", products=["metering"])
        category = EventCategory.objects.create(tenant=other, key="generation")
        EventType.objects.create(tenant=other, key="theirs.call",
                                 costing_method=COSTING_METHOD_CALCULATED,
                                 category=category)
        assert "theirs.call" not in rollup_membership(
            self.tenant.id, ANALYTICS_ROLLUP_EVENT_CATEGORY)

    def test_an_axis_that_is_not_a_declared_rollup_is_refused(self):
        with pytest.raises(ValueError):
            rollup_membership(self.tenant.id, "provider")


class TheCostTheMeasurementAxisRefusesDoesNotExistToBeSpread(TestCase):
    """AC 4's other half: the axis must never duplicate a whole event's cost
    across the measurements that event contains.

    The refusal is what a caller meets; THIS is why the refusal is honest rather
    than cautious. An event measured by two quantities carries ONE supplier
    cost, on the posting, and the measurement child record that holds the two
    quantities has no money on it at all — so there is no per-measurement figure
    to return, and the only way to answer at that grain would be to repeat the
    posting's cost against each quantity. Asserted structurally, because a
    column that arrives later would make the refusal stale and nothing else
    would notice.
    """

    def test_one_event_measured_two_ways_carries_one_cost_and_no_split(self):
        tenant = Tenant.objects.create(name="T", products=["metering"])
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        posting = Posting.objects.create(
            tenant=tenant, customer=customer, idempotency_key="i1",
            event_type="chat.completion", provider_cost_micros=900_000)
        measurement = PostingMeasurement.objects.create(
            posting=posting, recorded_at=timezone.now(),
            measurements={"prompt_tokens": 600, "completion_tokens": 300})

        assert len(measurement.measurements) == 2
        assert posting.provider_cost_micros == 900_000
        money = [field.name for field in PostingMeasurement._meta.get_fields()
                 if "micros" in field.name or "cost" in field.name
                 or "amount" in field.name or "currency" in field.name]
        assert money == [], (
            f"the measurement record has grown {money}, so the axis's declared "
            f"reason is stale and the narrowing should be revisited")


class ChangingARollupReclassifiesHistoryAndMovesNoMoney(TestCase):
    """§6: changing a rollup reclassifies history, and that is safe PRECISELY
    because rollups touch no money.

    Asserted in both directions, and the second direction constructs what it
    asserts about rather than checking that an empty set is still empty: a
    posting with both cost columns and a sealed receipt, and a Charge with its
    own frozen amount. A test that asserted 'no Charge changed' without ever
    building one would be the same direction twice.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="T", products=["metering"])
        cls.customer = Customer.objects.create(tenant=cls.tenant,
                                               external_id="c1")
        cls.before = EventCategory.objects.create(tenant=cls.tenant,
                                                  key="generation")
        cls.after = EventCategory.objects.create(tenant=cls.tenant,
                                                 key="retrieval")
        cls.event_type = EventType.objects.create(
            tenant=cls.tenant, key="chat.completion",
            costing_method=COSTING_METHOD_CALCULATED, category=cls.before)
        cls.posting = Posting.objects.create(
            tenant=cls.tenant, customer=cls.customer, idempotency_key="i1",
            event_type="chat.completion", provider_cost_micros=400_000,
            billed_cost_micros=1_000_000,
            **{Posting.RECEIPT_COLUMN: {"totals": {"billed_micros": 1_000_000}}})
        task = Task.objects.create(tenant=cls.tenant, customer=cls.customer,
                                   balance_snapshot_micros=0)
        cls.charge = Charge.objects.create(
            tenant=cls.tenant, task=task, amount_micros=1_000_000,
            currency="usd", agreed_price_line_id=uuid.uuid4(), book_version=1,
            resolved_at=timezone.now(), charged_at=timezone.now(),
            idempotency_key="charge-1")

    def _money(self):
        """Every monetary and economic column the reclassification must not
        touch, read back from the database rather than from the instances.

        The guard is not decoration: two equal snapshots prove nothing if the
        snapshot is empty, and a `values()` list that stopped matching would
        make this whole class pass over money it no longer reads.
        """
        posting = Posting.objects.values(
            "provider_cost_micros", "billed_cost_micros", "costing_status",
            "pricing_status", "event_type", "effective_at",
            Posting.RECEIPT_COLUMN).get(id=self.posting.id)
        charge = Charge.objects.values(
            "amount_micros", "currency", "agreed_price_line_id",
            "book_version", "charged_at").get(id=self.charge.id)
        assert posting["billed_cost_micros"] == 1_000_000
        assert posting["provider_cost_micros"] == 400_000
        assert posting[Posting.RECEIPT_COLUMN]["totals"]
        assert charge["amount_micros"] == 1_000_000
        return posting, charge

    def test_the_heading_moves_and_every_past_row_moves_with_it(self):
        assert rollup_membership(
            self.tenant.id, ANALYTICS_ROLLUP_EVENT_CATEGORY) == {
                "chat.completion": "generation"}
        EventType.objects.filter(id=self.event_type.id).update(
            category=self.after)
        assert rollup_membership(
            self.tenant.id, ANALYTICS_ROLLUP_EVENT_CATEGORY) == {
                "chat.completion": "retrieval"}

    def test_no_original_event_cost_charge_receipt_or_amount_moves_with_it(self):
        was = self._money()
        EventType.objects.filter(id=self.event_type.id).update(
            category=self.after)
        assert self._money() == was

    def test_unfiling_the_identity_altogether_moves_no_money_either(self):
        """The other way a heading changes: a tenant takes the filing away.
        The classification disappears and the money does not."""
        was = self._money()
        EventType.objects.filter(id=self.event_type.id).update(category=None)
        assert rollup_membership(self.tenant.id,
                                 ANALYTICS_ROLLUP_EVENT_CATEGORY) == {}
        assert self._money() == was


class NeitherKindEverSelectsARule(TestCase):
    """§6: both are analytics-only, and neither may ever select a Cost Rate or a
    customer-pricing rule.

    #145 §5 took that role away and #147 §2 took the event heading out of
    pricing by name, so this slice must not readmit either through a reporting
    door. **A customer-pricing rule is a Rate carrying a customer**, so one
    selector list governs both and this asserts against that list rather than
    against two.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="T", products=["metering"])
        GroupingField.objects.create(tenant=cls.tenant, key="region",
                                     slot="grouping_field_1", scope="task")

    def test_no_rollup_axis_is_a_selector(self):
        assert ANALYTICS_ROLLUP_EVENT_CATEGORY not in Rate.SELECTORS
        assert ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT not in Rate.SELECTORS

    def test_no_rule_holds_a_rollup_identity(self):
        """The relation form, caught by its target model rather than by a name,
        so a rename on the far side cannot slip past."""
        for field in Rate._meta.get_fields():
            assert getattr(field, "related_model", None) not in (
                EventCategory, MeasurementConcept), field.name

    def test_a_rule_cannot_even_be_asked_to_pin_one(self):
        for axis in (ANALYTICS_ROLLUP_EVENT_CATEGORY,
                     ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT):
            assert not hasattr(Rate, axis)
            with pytest.raises(TypeError):
                Rate(tenant=self.tenant, **{axis: "generation"})

    def test_the_customer_axis_is_a_grouping_axis_and_not_a_selector(self):
        """The one entry that proves the axis list is not the selector list
        wearing another name: a rule pins a customer through its own relation,
        never through a selector."""
        assert "customer" not in Rate.SELECTORS
        assert "field:customer" in {option["key"] for option
                                    in grouping_options(self.tenant.id)}
        assert Rate._meta.get_field("customer").related_model is Customer

    def test_nothing_in_the_pricing_app_reads_the_grouping_contract(self):
        """The FIELD kind's half of the prohibition, and it needs a source walk
        rather than a comparison.

        ⚠ **A SET COMPARISON CANNOT PROVE THIS ONE.** Asserting that no request
        word is a selector name passes for free — every word carries a `field:`
        or `rollup:` prefix, so the two sets are disjoint whatever the code
        does, and the slot columns underneath genuinely ARE selectors (that is
        ADR-0005's one vocabulary working as designed). What the prohibition
        actually says is that the reporting vocabulary never becomes an input to
        rate selection, and the checkable form of that is: no module where a
        price is decided imports any of it.

        The same shape `apps/platform/tests/test_event_type_satellite
        _invariants.py` uses for the catalogue, narrowed to this contract's own
        names, and with a vacuity guard — a walk that read nothing would
        otherwise report a serene absence of findings.
        """
        pricing = Path(__file__).resolve().parents[1] / "pricing"
        names = {"grouping_options", "grouping_refusal", "parse_grouping_axis",
                 "grouping_axis", "rollup_membership", "ALWAYS_PRESENT_AXES",
                 "ROLLUP_AXES", "GROUPING_SURFACES"}
        read, reaching = 0, []
        for path in sorted(pricing.rglob("*.py")):
            if "migrations" in path.parts or path.name.startswith("test_"):
                continue
            read += 1
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                spelled = (node.id if isinstance(node, ast.Name) else
                           node.attr if isinstance(node, ast.Attribute) else
                           node.name if isinstance(node, ast.alias) else None)
                if spelled in names:
                    reaching.append(f"{path.name}:{node.lineno if hasattr(node, 'lineno') else '?'} "
                                    f"names {spelled}")
        assert read > 10, f"the walk only read {read} pricing modules"
        assert not reaching, "\n".join(reaching)
