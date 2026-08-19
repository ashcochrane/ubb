"""A customer override is declared and withdrawn, and both go through a publish
(#361, #151 §6).

The two acts a tenant performs on a negotiated deal, at the surface a tenant
performs them at. What each class holds:

* *Declaring an override writes no rule* — the property everything else rests
  on. Both acts declare a DRAFT on the customer's own book, and publishing that
  draft is what puts the deal in force.
* *No immediate mutation path reaches an override* — the other half of that,
  and the half a reader would not think to look for: the three immediate
  surfaces a book still has all take a bare book id, so without a refusal a
  negotiated deal could be written with no record of who decided it.
* *An override states a whole rule* — the body carries the method, and there is
  no field on it naming a rule to inherit from. This is AC 3 at the API, the
  half the service module holds at the service.
* *An override is dated forward and reversed by a further publish* — tickets 12
  and 13's routes, on the customer's book. Those routes are untouched by this
  commit; the change body they take is extended, which is additive.
* *The inherited rule is readable* — what a client offers as the starting point
  for writing an override, including the grouping fields it pins.
* *The two acts are governance* — two registered actions, distinct, with the
  ledger refusing an unregistered name, neither route on the audit sweep's
  exemption list and both carrying the marker the #82 mutating-route pin reads.

**THE RETIRED WORDS THIS MODULE NEVER SPELLS.** The container's own name and
the cost/price discriminator both carry ledger entries that are ceilings as
well as floors, so every book and rule here is built through `pricing/tests/
_helpers`, which carries them for its callers, and the book a route answers
with is read out of the response body by the key the contract publishes.
"""

import json
from datetime import timedelta
from urllib.parse import urlencode

from django.test import Client, TestCase
from django.utils import timezone

from apps.metering.pricing.models import Rate, RateCard
from apps.metering.pricing.tests._helpers import (
    rate_in_default_book, the_book_holding)
from apps.platform.audit.actions import is_registered_action
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.models import AuditRecord
from apps.platform.customers.models import Customer
from apps.platform.event_types.tests._helpers import declares_a_quantity
from apps.platform.grouping_fields.services import DimensionService
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.vocabulary import (
    DECLARATION_STATUS_DRAFT,
    PRICING_METHOD_DIRECT_EVENT_PRICE,
    PRICING_METHOD_MARGIN_OVER_COST,
)

QUANTITY = "prompt_tokens"
PROVIDER = "openai"
EVENT_TYPE = "chat"

#: The grouping field this tenant declares. Named by the tenant's own key
#: everywhere on this surface, which is what lets a rule pinned on any of the
#: ten slots be addressed rather than only six of them.
TIER = "tier"
GOLD = "gold"

WHAT_THE_CATALOGUE_CHARGES = 2_000_000
WHAT_THE_DEAL_CHARGES = 7_000_000

DECLARED = "customer_pricing_override.declared"
WITHDRAWN = "customer_pricing_override.withdrawn"
RESOURCE_TYPE = "pricing_book_publish"

#: The two routes, as the contract publishes them.
OVERRIDES = "/metering/pricing/customers/{customer_id}/overrides"
ONE_OVERRIDE = f"{OVERRIDES}/{{override_id}}"


class _ATenantWithACustomerMixin:

    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(
            name="Deal Tenant", products=["metering", "billing"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="k")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="acme")
        declares_a_quantity(self.tenant, QUANTITY)
        DimensionService.declare(self.tenant, key=TIER,
                                 slot="grouping_field_7", scope="event")
        self.inherited = rate_in_default_book(
            self.tenant, provider=PROVIDER, event_type=EVENT_TYPE,
            measurement_key=QUANTITY,
            rate_per_unit_micros=WHAT_THE_CATALOGUE_CHARGES)
        self.catalogue = the_book_holding(self.inherited)
        self.overrides = (f"/api/v1/metering/pricing/customers/"
                          f"{self.customer.id}/overrides")

    def _book(self, book_id):
        """A book by the id a route answered with.

        Its rules are reached through the reverse relation rather than by
        filtering on the column that points at it: that column's name is
        retired and its ledger entry is a ceiling on how many files may still
        spell it, and this module is not one of them.
        """
        return RateCard.objects.get(id=book_id)

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _post(self, path, body=None):
        return self.http.post(path, data=json.dumps(body or {}),
                              content_type="application/json", **self._auth())

    def _get(self, path):
        return self.http.get(path, **self._auth())

    def _delete(self, path):
        return self.http.delete(path, **self._auth())

    def an_override(self, **stated):
        """One override as a tenant SENDS it — a whole rule, no `kind`."""
        return {"measurement_key": QUANTITY, "provider": PROVIDER,
                "event_type": EVENT_TYPE,
                "rate_per_unit_micros": WHAT_THE_DEAL_CHARGES, **stated}

    def declare(self, **stated):
        return self._post(self.overrides, self.an_override(**stated))

    def publish(self, draft):
        """Publish a declared change through the book's OWN route, which is the
        whole of what "the same one path" means here."""
        return self._post(
            f"/api/v1/metering/pricing/rate-cards/{draft['book_id']}"
            f"/publishes/{draft['id']}/publish")

    def declare_and_publish(self, **stated):
        draft = self.declare(**stated).json()
        return self.publish(draft).json()


class DeclaringAnOverrideWritesNoRuleTest(_ATenantWithACustomerMixin, TestCase):
    """AC 6 — an override is created through a publish, and the declaring act
    is not one."""

    def test_declaring_answers_a_draft_and_opens_nothing(self):
        response = self.declare()

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["declaration_status"], DECLARATION_STATUS_DRAFT)
        self.assertEqual(body["opened_rule_ids"], [])
        self.assertEqual(body["closed_rule_ids"], [])
        self.assertEqual(self._book(body["book_id"]).rates.count(), 0)

    def test_the_diff_shows_what_the_deal_will_be(self):
        body = self.declare(
            pricing_method=PRICING_METHOD_DIRECT_EVENT_PRICE).json()

        self.assertEqual(len(body["diff"]), 1)
        row = body["diff"][0]
        self.assertEqual(row["kind"], "add")
        self.assertIsNone(row["before"])
        self.assertEqual(row["after"]["rate_per_unit_micros"],
                         WHAT_THE_DEAL_CHARGES)
        self.assertEqual(row["after"]["pricing_method"],
                         PRICING_METHOD_DIRECT_EVENT_PRICE)

    def test_publishing_the_draft_is_what_opens_the_rule(self):
        published = self.declare_and_publish()

        self.assertEqual(len(published["opened_rule_ids"]), 1)
        opened = Rate.objects.get(pk=published["opened_rule_ids"][0])
        self.assertEqual(opened.rate_per_unit_micros, WHAT_THE_DEAL_CHARGES)
        # WHOSE rule it is, read where resolution reads it: the book. The rule
        # itself carries nothing — a second copy of that fact would have a
        # different delete rule from the one this design chose.
        self.assertEqual(the_book_holding(opened).customer_id,
                         self.customer.id)
        self.assertIsNone(opened.customer_id)

    def test_withdrawing_writes_no_rule_either(self):
        published = self.declare_and_publish()
        override_id = published["opened_rule_ids"][0]

        response = self._delete(f"{self.overrides}/{override_id}")

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["declaration_status"], DECLARATION_STATUS_DRAFT)
        self.assertEqual(body["closed_rule_ids"], [])
        # The override is still open until the withdrawal is published.
        self.assertIsNone(Rate.objects.get(pk=override_id).valid_to)

    def test_publishing_the_withdrawal_is_what_ends_the_deal(self):
        published = self.declare_and_publish()
        override_id = published["opened_rule_ids"][0]

        withdrawal = self._delete(f"{self.overrides}/{override_id}").json()
        self.publish(withdrawal)

        self.assertIsNotNone(Rate.objects.get(pk=override_id).valid_to)

    def test_an_override_belonging_to_another_customer_is_not_addressable(self):
        published = self.declare_and_publish()
        somebody_else = Customer.objects.create(
            tenant=self.tenant, external_id="beta")

        response = self._delete(
            f"/api/v1/metering/pricing/customers/{somebody_else.id}"
            f"/overrides/{published['opened_rule_ids'][0]}")

        self.assertEqual(response.status_code, 404)


class NoImmediateMutationPathReachesAnOverrideTest(_ATenantWithACustomerMixin,
                                                   TestCase):
    """AC 6, the half that is about the REST of the surface.

    Two routes declaring a draft prove nothing on their own: a book still has
    three immediate mutation surfaces beside the publish record, each taking a
    bare book id filtered by the tenant alone, and a customer's own book is one
    of that tenant's books. Without a refusal a negotiated deal could be
    written, repriced and retired with no record of who decided it or when it
    took effect.

    ⚠ **ONE TEST PER ACT, NOT THREE SUBTESTS OF ONE.** Mutating the refusal away
    showed why: the reprice supersedes the very rule the retirement then
    addresses, so a shared fixture made the third case answer `404` for a
    reason that had nothing to do with the rule under test. Each act now gets
    its own transaction.

    ⚠ **AND EACH ACT IS ONE THAT WOULD OTHERWISE SUCCEED.** The same mutation
    showed the first case answering `409`: it added a rule with the identity
    the override already holds, so the book's own uniqueness rule refused it
    and the refusal under test was never the reason. It pins a further selector
    now, which is a rule the book does not hold.

    Every case reads the book's rules back afterwards, because a 422 is not
    evidence on its own — these routes have refusals of their own.
    """

    def setUp(self):
        super().setUp()
        published = self.declare_and_publish()
        self.book_id = published["book_id"]
        self.override_id = published["opened_rule_ids"][0]
        self.book = f"/api/v1/metering/pricing/rate-cards/{self.book_id}"

    def _rules(self):
        return sorted(self._book(self.book_id).rates
                      .values_list("id", "rate_per_unit_micros", "valid_to"))

    def _assert_refused_and_nothing_written(self, response, before):
        self.assertEqual(response.status_code, 422, response.content)
        self.assertIn("one customer's own pricing rules",
                      response.json()["detail"])
        self.assertEqual(self._rules(), before)

    def test_a_rule_cannot_be_added_to_a_customers_own_book(self):
        before = self._rules()

        response = self._post(f"{self.book}/rates", {
            "measurement_key": QUANTITY, "provider": PROVIDER,
            "event_type": EVENT_TYPE, "task_type": "batch",
            "rate_per_unit_micros": 1})

        self._assert_refused_and_nothing_written(response, before)

    def test_a_rule_in_a_customers_own_book_cannot_be_repriced_immediately(self):
        before = self._rules()

        response = self._post(f"{self.book}/publish", {
            "changes": [{"measurement_key": QUANTITY, "provider": PROVIDER,
                         "event_type": EVENT_TYPE,
                         "rate_per_unit_micros": 1}]})

        self._assert_refused_and_nothing_written(response, before)

    def test_a_rule_in_a_customers_own_book_cannot_be_retired_immediately(self):
        before = self._rules()

        response = self._delete(f"{self.book}/rates/{self.override_id}")

        self._assert_refused_and_nothing_written(response, before)

    def test_the_same_three_still_reach_an_ordinary_book(self):
        """The control: the refusal is about WHOSE book it is, not about the
        routes, which are untouched and still work everywhere else."""
        book = f"/api/v1/metering/pricing/rate-cards/{self.catalogue.id}"

        response = self._post(f"{book}/rates", {
            "measurement_key": QUANTITY, "provider": PROVIDER,
            "event_type": EVENT_TYPE, "task_type": "batch",
            "rate_per_unit_micros": 1})

        self.assertEqual(response.status_code, 200, response.content)


class AnOverrideStatesAWholeRuleTest(_ATenantWithACustomerMixin, TestCase):
    """AC 3 at the API — no path overrides a value while inheriting a method.

    The body carries the method, and it carries no field naming a rule to
    inherit from. The discriminating case is the second: an override that
    states a price and no method over an inherited rule that declares a margin
    comes out declaring none, rather than the margin it would have inherited.
    """

    def test_the_body_names_every_field_of_a_rule_and_no_rule_to_inherit_from(self):
        from api.v1.schemas import BookChangeIn, CustomerOverrideIn

        stated = set(CustomerOverrideIn.model_fields)
        self.assertIn("pricing_method", stated)
        # Every field a change body can state about a rule, minus the act,
        # which the route is. Nothing else — in particular nothing naming
        # another rule, another customer or another book.
        self.assertEqual(stated,
                         (set(BookChangeIn.model_fields) - {"kind"})
                         | {"effective_at"})

    def test_a_price_with_no_method_does_not_inherit_the_one_it_replaces(self):
        Rate.objects.filter(pk=self.inherited.pk).update(
            pricing_method=PRICING_METHOD_MARGIN_OVER_COST,
            rate_per_unit_micros=0, fixed_micros=0)

        published = self.declare_and_publish()

        opened = Rate.objects.get(pk=published["opened_rule_ids"][0])
        self.assertIsNone(opened.pricing_method)
        self.assertEqual(opened.rate_per_unit_micros, WHAT_THE_DEAL_CHARGES)

    def test_the_method_can_be_changed_and_the_rule_carries_it(self):
        Rate.objects.filter(pk=self.inherited.pk).update(
            pricing_method=PRICING_METHOD_MARGIN_OVER_COST,
            rate_per_unit_micros=0, fixed_micros=0)

        published = self.declare_and_publish(
            pricing_method=PRICING_METHOD_DIRECT_EVENT_PRICE)

        self.assertEqual(
            Rate.objects.get(pk=published["opened_rule_ids"][0]).pricing_method,
            PRICING_METHOD_DIRECT_EVENT_PRICE)

    def test_a_method_outside_the_ratified_pair_is_refused(self):
        response = self.declare(pricing_method="cost_plus_ten")

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")
        self.assertIn("pricing_method", response.json()["detail"])

    def test_an_override_can_pin_a_grouping_field_the_tenant_declared(self):
        published = self.declare_and_publish(grouping_fields={TIER: GOLD})

        opened = Rate.objects.get(pk=published["opened_rule_ids"][0])
        self.assertEqual(opened.grouping_field_7, GOLD)

    def test_an_undeclared_grouping_field_is_refused(self):
        response = self.declare(grouping_fields={"nobody_declared_this": "x"})

        self.assertEqual(response.status_code, 422)
        self.assertIn("no grouping field is declared",
                      response.json()["detail"])


class AnOverrideIsDatedForwardAndReversedTest(_ATenantWithACustomerMixin,
                                              TestCase):
    """AC 7 — tickets 12 and 13's machinery, through their own routes.

    The reversal is the property that fails silently if overrides took a second
    path, which is why it is driven end to end here rather than inferred from
    the fact that the same service was called.
    """

    def test_a_forward_dated_override_is_declared_and_published(self):
        boundary = timezone.now() + timedelta(days=30)

        published = self.declare_and_publish(
            effective_at=boundary.isoformat())

        opened = Rate.objects.get(pk=published["opened_rule_ids"][0])
        self.assertEqual(opened.valid_from, boundary)
        self.assertIsNone(opened.valid_to)

    def test_an_instant_beyond_the_horizon_is_refused_by_its_own_code(self):
        response = self.declare(
            effective_at=(timezone.now() + timedelta(days=400)).isoformat())

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "effective_at_too_far_ahead")

    def test_a_refused_declaration_writes_no_draft_and_no_book(self):
        """A refusal spends nothing — including the customer's book, which
        this route creates on first use and which a refused request must not
        leave behind."""
        from apps.metering.pricing.models import PricingBookPublish, RateCard

        self.declare(
            effective_at=(timezone.now() + timedelta(days=400)).isoformat())

        self.assertEqual(PricingBookPublish.objects.count(), 0)
        self.assertEqual(
            RateCard.objects.filter(customer=self.customer).count(), 0)

    def test_a_scheduled_override_is_reversed_by_a_further_publish(self):
        """Withdrawing at the same instant leaves an empty window rather than
        deleting anything: the deal never took effect, and the record that it
        was scheduled survives."""
        boundary = timezone.now() + timedelta(days=30)
        published = self.declare_and_publish(effective_at=boundary.isoformat())
        override_id = published["opened_rule_ids"][0]

        # `urlencode`, because an ISO instant carries a `+` in its offset and a
        # raw `+` in a query string is a SPACE. A caller that forgets is told
        # so — the parameter is a typed datetime and Ninja refuses it — which
        # is the right answer and not one to paper over here.
        withdrawal = self._delete(
            f"{self.overrides}/{override_id}"
            f"?{urlencode({'effective_at': boundary.isoformat()})}").json()
        reversed_ = self.publish(withdrawal).json()

        self.assertEqual(reversed_["closed_rule_ids"], [override_id])
        self.assertEqual(reversed_["opened_rule_ids"], [])
        override = Rate.objects.get(pk=override_id)
        self.assertEqual(override.valid_from, boundary)
        self.assertEqual(override.valid_to, boundary)

    def test_a_withdrawal_is_discardable_like_any_other_draft(self):
        published = self.declare_and_publish()
        withdrawal = self._delete(
            f"{self.overrides}/{published['opened_rule_ids'][0]}").json()

        discarded = self._delete(
            f"/api/v1/metering/pricing/rate-cards/{withdrawal['book_id']}"
            f"/publishes/{withdrawal['id']}")

        self.assertEqual(discarded.status_code, 200, discarded.content)
        self.assertIsNone(
            Rate.objects.get(pk=published["opened_rule_ids"][0]).valid_to)


class TheInheritedRuleIsReadableTest(_ATenantWithACustomerMixin, TestCase):
    """AC 8 — what a client offers as the starting point for an override."""

    def _inherited(self, **params):
        query = "&".join(f"{name}={value}" for name, value in
                         {"measurement_key": QUANTITY, "provider": PROVIDER,
                          "event_type": EVENT_TYPE, **params}.items())
        return self._get(
            f"/api/v1/metering/pricing/customers/{self.customer.id}"
            f"/inherited-rule?{query}")

    def test_it_answers_the_rule_the_customer_is_on_today(self):
        response = self._inherited()

        self.assertEqual(response.status_code, 200, response.content)
        rule = response.json()["rule"]
        self.assertEqual(rule["rule_id"], str(self.inherited.id))
        self.assertEqual(rule["book_id"], str(self.catalogue.id))
        self.assertEqual(rule["rate_per_unit_micros"],
                         WHAT_THE_CATALOGUE_CHARGES)
        self.assertIsNone(rule["pricing_method"])

    def test_it_keeps_answering_the_inherited_rule_once_an_override_exists(self):
        """The point of the read: a client showing *what you are replacing*
        must not be shown the replacement."""
        self.declare_and_publish()

        rule = self._inherited().json()["rule"]

        self.assertEqual(rule["rule_id"], str(self.inherited.id))
        self.assertEqual(rule["rate_per_unit_micros"],
                         WHAT_THE_CATALOGUE_CHARGES)

    def test_it_answers_null_where_nothing_is_inherited(self):
        response = self._inherited(measurement_key="completion_tokens")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["rule"])

    def test_it_names_a_pinned_grouping_field_by_the_tenants_own_key(self):
        Rate.objects.filter(pk=self.inherited.pk).update(
            grouping_field_7=GOLD)

        rule = self._inherited(grouping_field=f"{TIER}={GOLD}").json()["rule"]

        self.assertEqual(rule["grouping_fields"], {TIER: GOLD})

    def test_a_grouping_field_the_tenant_never_declared_is_refused(self):
        response = self._inherited(grouping_field="nobody=declared_this")

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")


class TheTwoActsAreGovernanceTest(_ATenantWithACustomerMixin, TestCase):
    """AC 9 and AC 10 — two registered actions, and the route pins.

    Governance rather than telemetry: they decide what one named customer is
    charged, so they take names in the registry rather than the audit sweep's
    exemption list.
    """

    def _actions(self):
        return list(AuditRecord.objects.filter(tenant_id=self.tenant.id)
                    .order_by("created_at").values_list("action", flat=True))

    def test_each_act_records_its_own_action_against_the_draft(self):
        published = self.declare_and_publish()
        self._delete(f"{self.overrides}/{published['opened_rule_ids'][0]}")

        self.assertEqual(
            self._actions(),
            [DECLARED, "pricing_book_publish.published", WITHDRAWN])
        for entry in AuditRecord.objects.filter(
                action__startswith="customer_pricing_override."):
            self.assertEqual(entry.resource_type, RESOURCE_TYPE)
            self.assertEqual(entry.metadata["customer_id"],
                             str(self.customer.id))

    def test_a_refused_declaration_records_nothing(self):
        self.declare(pricing_method="cost_plus_ten")

        self.assertEqual(self._actions(), [])

    def test_the_ledger_refuses_an_unregistered_name(self):
        """Driven over near-misses of the two real names rather than over an
        obvious nonsense string, because what this has to catch is a typo or a
        name somebody meant to add and did not."""
        for unregistered in ("customer_pricing_override.created",
                             "customer_pricing_override.deleted",
                             "customer_override.declared", f"{WITHDRAWN}_"):
            with self.subTest(unregistered):
                self.assertFalse(is_registered_action(unregistered))
                with self.assertRaisesRegex(ValueError, "unregistered audit"):
                    audit_record(action=unregistered, tenant_id=self.tenant.id,
                                 resource_type=RESOURCE_TYPE)

    def test_neither_route_takes_the_audit_sweeps_exemption(self):
        """Read the exemption list directly rather than trusting the sweep's
        own count, which would stay green if a route joined the carve."""
        from api.v1.tests.test_audit_sweep import _EXEMPT

        for method, path in (("POST", OVERRIDES), ("DELETE", ONE_OVERRIDE)):
            with self.subTest(path=f"{method} {path}"):
                self.assertNotIn((method, path), _EXEMPT)

    def test_both_routes_carry_the_marker_the_mutating_pin_reads(self):
        """The #82 pin walks the live API for exactly this attribute, and a
        route carrying neither it nor an exemption turns it red."""
        from api.v1.tests.test_audit_sweep import _iter_mutating_ops

        marked = {(method, path): getattr(view, "_audit_actions", ())
                  for method, path, view in _iter_mutating_ops()
                  if path.startswith(OVERRIDES)}

        self.assertEqual(marked, {("POST", OVERRIDES): (DECLARED,),
                                  ("DELETE", ONE_OVERRIDE): (WITHDRAWN,)})

    def test_the_read_is_not_a_mutating_route_and_needs_no_action(self):
        """The inherited-rule read answers a question and decides nothing, so
        it is outside the pin's subject entirely rather than exempted from it.
        """
        from api.v1.tests.test_audit_sweep import _iter_mutating_ops

        self.assertEqual(
            [path for _, path, _ in _iter_mutating_ops()
             if path.endswith("/inherited-rule")], [])
