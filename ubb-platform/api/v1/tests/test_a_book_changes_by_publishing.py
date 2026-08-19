"""A book's mutation surface becomes one act, published (#358).

Declaring a change, publishing it and discarding it — three routes, three audit
actions, one record. The service module in `apps/metering/pricing/tests/`
carries the behaviour: one clock over the boundary, the record's immutability
through three doors, the diff computed at the effective instant. What is asked
HERE is what only the route can answer — the request shape a tenant sends, the
refusals it gets back, the governance entries the acts leave, and the vocabulary
the contract publishes.

**⚠ THE CHANGE BODY NAMES A GROUPING FIELD BY THE TENANT'S OWN KEY, WHICH IS
WHY SLOT SEVEN IS REACHABLE HERE AND NOT THROUGH THE ROUTE THIS REPLACES.** The
immediate reprice body names six of the ten slots by their physical spelling, so
a rule pinned on the seventh cannot be addressed through it at all — a
functional gap, not a naming one. A change body carries an object keyed by what
the tenant declared, so every slot is reachable and no physical slot reaches the
contract. One case below is that gap, closed.

**GOVERNANCE, NOT TELEMETRY.** All three acts decide what a customer is charged,
so none of them takes the audit sweep's exemption list — that carve is for usage
ingestion and the start-gate call.
"""
import json

from django.test import Client, TestCase

from apps.metering.pricing.models import PricingBookPublish, Rate
from apps.metering.pricing.tests._helpers import (
    rate_in_default_book, the_book_holding)
from apps.platform.audit.actions import is_registered_action
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.models import AuditRecord
from apps.platform.event_types.tests._helpers import declares_a_quantity
from apps.platform.grouping_fields.services import DimensionService
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.vocabulary import (
    DECLARATION_STATUS_DRAFT, DECLARATION_STATUS_PUBLISHED)

DECLARED = "pricing_book_publish.declared"
PUBLISHED = "pricing_book_publish.published"
DISCARDED = "pricing_book_publish.discarded"

RESOURCE_TYPE = "pricing_book_publish"

QUANTITY = "input_tokens"
ANOTHER_QUANTITY = "output_tokens"
PROVIDER = "gemini"
EVENT_TYPE = "chat"

BEFORE = 1_000_000
AFTER = 7_000_000

#: The declared grouping field this module prices on, bound to the SEVENTH slot
#: — the one the immediate reprice body cannot name at all.
UNREACHABLE_SLOT = "grouping_field_7"
TIER = "tier"


class _APublishingTenantMixin:

    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(
            name="Publishing Tenant", products=["metering", "billing"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="k")
        for code in (QUANTITY, ANOTHER_QUANTITY):
            declares_a_quantity(self.tenant, code)
        self.rule = rate_in_default_book(
            self.tenant, provider=PROVIDER, event_type=EVENT_TYPE,
            measurement_key=QUANTITY, rate_per_unit_micros=BEFORE)
        self.book = the_book_holding(self.rule)
        self.publishes = (f"/api/v1/metering/pricing/rate-cards/"
                          f"{self.book.id}/publishes")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _post(self, path, body=None):
        return self.http.post(path, data=json.dumps(body or {}),
                              content_type="application/json", **self._auth())

    def _get(self, path):
        return self.http.get(path, **self._auth())

    def _delete(self, path):
        return self.http.delete(path, **self._auth())

    def a_change(self, kind="reprice", measurement_key=QUANTITY, **terms):
        """One change as a tenant SENDS it — the wire shape, not the service's.

        Deliberately not shared with the service module's fixture of the same
        name, which builds the other one: this names its kind with the string
        that crosses the wire and carries its grouping fields as an object keyed
        by the tenant's own declaration, while the service works in column
        names. Sharing them would mean sharing a translation, which is the thing
        under test on this side.
        """
        return {"kind": kind, "measurement_key": measurement_key,
                "provider": PROVIDER, "event_type": EVENT_TYPE, **terms}

    def declare(self, *changes):
        return self._post(self.publishes, {
            "changes": list(changes) or [
                self.a_change(rate_per_unit_micros=AFTER)]})


class DeclaringAChangeWritesNoRuleTest(_APublishingTenantMixin, TestCase):

    def test_declaring_answers_a_draft_and_its_diff(self):
        response = self.declare()

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["declaration_status"], DECLARATION_STATUS_DRAFT)
        self.assertEqual(body["book_id"], str(self.book.id))
        self.assertEqual(body["opened_rule_ids"], [])
        self.assertEqual(body["closed_rule_ids"], [])
        self.assertIsNone(body["published_at"])
        self.assertEqual(body["actor_display"], "")

        row, = body["diff"]
        self.assertEqual(row["kind"], "reprice")
        self.assertEqual(row["measurement_key"], QUANTITY)
        self.assertEqual(row["provider"], PROVIDER)
        self.assertEqual(row["before"]["rate_per_unit_micros"], BEFORE)
        self.assertEqual(row["after"]["rate_per_unit_micros"], AFTER)

    def test_declaring_leaves_the_book_where_it_was(self):
        self.declare()

        self.rule.refresh_from_db()
        self.book.refresh_from_db()
        self.assertEqual(self.rule.rate_per_unit_micros, BEFORE)
        self.assertIsNone(self.rule.valid_to)
        self.assertEqual(self.book.version, 1)
        self.assertEqual(Rate.objects.filter(tenant=self.tenant).count(), 1)

    def test_a_draft_is_readable_back_with_its_diff(self):
        declared = self.declare().json()

        body = self._get(f"{self.publishes}/{declared['id']}").json()

        self.assertEqual(body["id"], declared["id"])
        self.assertEqual(body["diff"], declared["diff"])

    def test_the_books_pending_changes_are_listable(self):
        declared = self.declare().json()

        rows = self._get(self.publishes).json()["data"]

        self.assertEqual([row["id"] for row in rows], [declared["id"]])
        self.assertEqual(rows[0]["diff"], declared["diff"])


class PublishingIsWhatWritesRulesTest(_APublishingTenantMixin, TestCase):

    def test_publishing_closes_the_old_rule_and_opens_its_replacement(self):
        declared = self.declare().json()

        response = self._post(f"{self.publishes}/{declared['id']}/publish")

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["declaration_status"],
                         DECLARATION_STATUS_PUBLISHED)
        self.assertIsNotNone(body["published_at"])
        self.assertEqual(body["closed_rule_ids"], [str(self.rule.id)])
        self.assertIsNone(body["diff"],
                          "a published record's diff is a statement about a "
                          "change that has already happened")

        self.rule.refresh_from_db()
        replacement = Rate.objects.get(pk=body["opened_rule_ids"][0])
        self.assertEqual(self.rule.valid_to, replacement.valid_from)
        self.assertEqual(replacement.rate_per_unit_micros, AFTER)

    def test_the_publishing_principal_is_recorded_on_the_record(self):
        """The key that published it, snapshotted at the moment of the act."""
        declared = self.declare().json()

        body = self._post(f"{self.publishes}/{declared['id']}/publish").json()

        self.assertEqual(body["actor_kind"], "api_key")
        self.assertEqual(body["actor_display"], "k")
        self.assertNotEqual(body["actor_id"], "")

    def test_adding_and_retiring_are_the_same_act_as_repricing(self):
        declared = self.declare(
            self.a_change(kind="add", measurement_key=ANOTHER_QUANTITY,
                          rate_per_unit_micros=AFTER),
            self.a_change(kind="retire")).json()

        body = self._post(f"{self.publishes}/{declared['id']}/publish").json()

        self.assertEqual(len(body["opened_rule_ids"]), 1)
        self.assertEqual(body["closed_rule_ids"], [str(self.rule.id)])
        added = Rate.objects.get(pk=body["opened_rule_ids"][0])
        self.assertEqual(added.measurement_key, ANOTHER_QUANTITY)
        self.rule.refresh_from_db()
        self.assertIsNotNone(self.rule.valid_to)

    def test_publishing_the_same_record_twice_is_refused(self):
        declared = self.declare().json()
        self._post(f"{self.publishes}/{declared['id']}/publish")

        response = self._post(f"{self.publishes}/{declared['id']}/publish")

        self.assertEqual(response.status_code, 422, response.content)
        self.assertIn("already published", response.json()["detail"])


class DiscardingADraftReopensNothingTest(_APublishingTenantMixin, TestCase):

    def test_discarding_removes_the_draft_and_leaves_the_book_alone(self):
        declared = self.declare().json()

        response = self._delete(f"{self.publishes}/{declared['id']}")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "discarded")
        self.assertFalse(PricingBookPublish.objects.exists())
        self.rule.refresh_from_db()
        self.book.refresh_from_db()
        self.assertEqual(self.rule.rate_per_unit_micros, BEFORE)
        self.assertIsNone(self.rule.valid_to)
        self.assertEqual(self.book.version, 1)

    def test_a_published_record_cannot_be_discarded(self):
        declared = self.declare().json()
        self._post(f"{self.publishes}/{declared['id']}/publish")

        response = self._delete(f"{self.publishes}/{declared['id']}")

        self.assertEqual(response.status_code, 422, response.content)
        self.assertTrue(PricingBookPublish.objects.filter(
            pk=declared["id"]).exists())


class AChangeIsRefusedWhileTheTenantIsStillDecidingTest(
        _APublishingTenantMixin, TestCase):

    def assert_refused_and_nothing_written(self, response, fragment):
        self.assertEqual(response.status_code, 422, response.content)
        self.assertIn(fragment, response.json()["detail"])
        self.assertFalse(PricingBookPublish.objects.exists())
        self.assertEqual(Rate.objects.filter(tenant=self.tenant).count(), 1)

    def test_a_quantity_the_tenant_has_not_declared_cannot_be_priced(self):
        self.assert_refused_and_nothing_written(
            self.declare(self.a_change(kind="add",
                                       measurement_key="nobody_declared_this",
                                       rate_per_unit_micros=AFTER)),
            "no declared quantity")

    def test_a_rule_that_is_not_there_cannot_be_repriced(self):
        self.assert_refused_and_nothing_written(
            self.declare(self.a_change(measurement_key=ANOTHER_QUANTITY,
                                       rate_per_unit_micros=AFTER)),
            "nothing to reprice")

    def test_a_grouping_field_the_tenant_has_not_declared_is_refused(self):
        """And it is refused rather than ignored, which is the point.

        A key the registry does not carry cannot be resolved to a slot. Dropping
        it would leave every slot unpinned, which matches a DIFFERENT rule — the
        blanket one — so the publish would quietly reprice something the tenant
        did not name.
        """
        self.assert_refused_and_nothing_written(
            self.declare(self.a_change(rate_per_unit_micros=AFTER,
                                       grouping_fields={"nobody_declared": "x"})),
            "no grouping field is declared")

    def test_an_unknown_kind_of_change_is_refused(self):
        self.assert_refused_and_nothing_written(
            self.declare(self.a_change(kind="repriced")), "kind must be one of")


class EverySlotIsReachableThroughAChangeBodyTest(_APublishingTenantMixin,
                                                 TestCase):
    """⚠ The functional gap in the surface this replaces, closed.

    A rule pinned on the seventh slot can be written server-side and cannot be
    named by the immediate reprice body at all — that body publishes six slots
    by their physical spelling and no request can reach the other four. A change
    body names the tenant's declared key instead, so the registry resolves it to
    whichever slot the tenant bound it to.
    """

    def test_a_rule_pinned_on_the_seventh_slot_can_be_repriced(self):
        DimensionService.declare(self.tenant, key=TIER,
                                 slot=UNREACHABLE_SLOT, scope="tenant")
        pinned = rate_in_default_book(
            self.tenant, provider=PROVIDER, event_type=EVENT_TYPE,
            measurement_key=QUANTITY, rate_per_unit_micros=BEFORE,
            **{UNREACHABLE_SLOT: "gold"})

        declared = self.declare(
            self.a_change(rate_per_unit_micros=AFTER,
                          grouping_fields={TIER: "gold"})).json()
        row, = declared["diff"]
        self.assertEqual(row["grouping_fields"], {TIER: "gold"})

        body = self._post(f"{self.publishes}/{declared['id']}/publish").json()

        self.assertEqual(body["closed_rule_ids"], [str(pinned.id)],
                         "the pinned rule is the one superseded, not the "
                         "blanket rule beside it")
        self.rule.refresh_from_db()
        self.assertIsNone(self.rule.valid_to)


class ADraftTheBookHasMovedUnderIsStillReadableTest(_APublishingTenantMixin,
                                                    TestCase):
    """⚠ A DRAFT CAN BE LEFT STATING A CHANGE THAT CAN NO LONGER BE CARRIED OUT.

    Not a defensive branch — a reachable state, through surfaces this commit
    deliberately keeps alive. A book still has three immediate mutation routes,
    and two drafts can name one rule while only one of them publishes; the
    survivor then names a rule that is closed. Reading it has to say so. Letting
    the planner's refusal escape a GET would have answered `internal_error`, and
    since the list serializes every pending draft, ONE stale draft would have
    taken the whole book's pending list with it.
    """

    def _a_draft_whose_rule_was_retired_beside_it(self):
        """Declare a reprice, then retire the rule through the OTHER surface.

        ⚠ Two drafts naming one rule is NOT this state, and checking was worth
        it: a change names a rule by its identity — the quantity and the
        selectors — rather than by version, so a second draft repricing the
        replacement is perfectly coherent and publishes fine. What strands a
        draft is the rule acquiring a close it cannot move: the immediate retire
        route stamps `valid_to` at the moment of the call, which is AFTER this
        draft was declared, so at the draft's own effective instant the rule is
        still in force and already closing — and `Rate.valid_to` is declared
        set_once, so no publish may move it.
        """
        draft = self.declare().json()
        retired = self._delete(
            f"/api/v1/metering/pricing/rate-cards/{self.book.id}"
            f"/rates/{self.rule.id}")
        self.assertEqual(retired.status_code, 200, retired.content)
        return draft

    def test_reading_it_answers_the_reason_rather_than_a_diff(self):
        stale = self._a_draft_whose_rule_was_retired_beside_it()

        body = self._get(f"{self.publishes}/{stale['id']}").json()

        self.assertEqual(body["declaration_status"], DECLARATION_STATUS_DRAFT)
        self.assertIsNone(body["diff"])
        self.assertIn("already scheduled to close",
                      body["diff_unavailable_reason"])

    def test_one_stale_draft_does_not_take_the_pending_list_with_it(self):
        stale = self._a_draft_whose_rule_was_retired_beside_it()
        healthy = self.declare(
            self.a_change(kind="add", measurement_key=ANOTHER_QUANTITY,
                          rate_per_unit_micros=AFTER)).json()

        response = self._get(self.publishes)

        self.assertEqual(response.status_code, 200, response.content)
        rows = {row["id"]: row for row in response.json()["data"]}
        self.assertEqual(set(rows), {stale["id"], healthy["id"]})
        self.assertIsNotNone(rows[stale["id"]]["diff_unavailable_reason"])
        self.assertIsNone(rows[healthy["id"]]["diff_unavailable_reason"])
        self.assertIsNotNone(rows[healthy["id"]]["diff"])

    def test_it_cannot_be_published_and_can_be_discarded(self):
        """The way out, which is what makes the reason worth reading."""
        stale = self._a_draft_whose_rule_was_retired_beside_it()

        refused = self._post(f"{self.publishes}/{stale['id']}/publish")
        self.assertEqual(refused.status_code, 422, refused.content)

        discarded = self._delete(f"{self.publishes}/{stale['id']}")
        self.assertEqual(discarded.status_code, 200, discarded.content)

    def test_a_published_record_carries_no_reason_either(self):
        """The two ways a diff is absent are told apart by the STATUS, not by a
        second null: a published record has no diff because there is nothing to
        state, and no reason because nothing refused anything."""
        declared = self.declare().json()

        body = self._post(f"{self.publishes}/{declared['id']}/publish").json()

        self.assertEqual(body["declaration_status"],
                         DECLARATION_STATUS_PUBLISHED)
        self.assertIsNone(body["diff"])
        self.assertIsNone(body["diff_unavailable_reason"])


class TheContractPublishesEveryTermTheServiceMovesTest(TestCase):
    """The published terms and the terms a publish can move are one set.

    ⚠ A `Schema` THAT DOES NOT NAME A KEY DROPS IT, silently — which is how a
    read contract once published a ceiling on a margin as the margin. The
    service decides what a rule's terms are and this schema decides what the
    contract says they are, so the day they disagree has to be a red day rather
    than a quiet one. Held at rest here; `rule_terms_out` holds it at request
    time by naming each key, so a term the service gains and the serializer does
    not is a `KeyError` rather than an omission.
    """

    def test_the_two_sets_are_equal(self):
        from api.v1.schemas import RuleTermsOut
        from apps.metering.pricing.services.book_service import _TERM_FIELDS

        self.assertEqual(set(RuleTermsOut.model_fields), set(_TERM_FIELDS))


class TheThreeActsAreGovernanceTest(_APublishingTenantMixin, TestCase):

    def _actions(self):
        return list(AuditRecord.objects.filter(tenant_id=self.tenant.id)
                    .order_by("created_at").values_list("action", flat=True))

    def test_each_act_records_its_own_action_against_the_record(self):
        first = self.declare().json()
        self._post(f"{self.publishes}/{first['id']}/publish")
        second = self.declare(self.a_change(kind="retire")).json()
        self._delete(f"{self.publishes}/{second['id']}")

        self.assertEqual(self._actions(),
                         [DECLARED, PUBLISHED, DECLARED, DISCARDED])
        for entry in AuditRecord.objects.filter(tenant_id=self.tenant.id):
            self.assertEqual(entry.resource_type, RESOURCE_TYPE)
        published = AuditRecord.objects.get(action=PUBLISHED)
        self.assertEqual(published.resource_id, first["id"])
        self.assertEqual(published.metadata["opened"], 1)
        self.assertEqual(published.metadata["closed"], 1)

    def test_a_refused_declaration_records_nothing(self):
        self.declare(self.a_change(measurement_key="nobody_declared_this"))

        self.assertEqual(self._actions(), [])

    def test_the_ledger_refuses_an_unregistered_name(self):
        """Driven over near-misses of the three real names rather than over an
        obvious nonsense string, because what this has to catch is a typo or a
        name somebody meant to add and did not."""
        for unregistered in ("pricing_book_publish.created",
                             "pricing_book_publish.deleted",
                             "pricing_book.declared", f"{PUBLISHED}_"):
            with self.subTest(unregistered):
                self.assertFalse(is_registered_action(unregistered))
                with self.assertRaisesRegex(ValueError, "unregistered audit"):
                    audit_record(action=unregistered, tenant_id=self.tenant.id,
                                 resource_type=RESOURCE_TYPE)

    def test_none_of_the_three_routes_takes_the_audit_sweeps_exemption(self):
        """Read the exemption list directly rather than trusting the sweep's
        own count, which would stay green if a route joined the carve."""
        from api.v1.tests.test_audit_sweep import _EXEMPT

        book = "/metering/pricing/rate-cards/{book_id}/publishes"
        for method, path in (("POST", book),
                             ("POST", f"{book}/{{publish_id}}/publish"),
                             ("DELETE", f"{book}/{{publish_id}}")):
            with self.subTest(path=f"{method} {path}"):
                self.assertNotIn((method, path), _EXEMPT)

    def test_all_three_routes_carry_the_marker_the_mutating_pin_reads(self):
        """The #82 pin walks the live API for exactly this attribute, and a
        route carrying neither it nor an exemption turns it red."""
        from api.v1.tests.test_audit_sweep import _iter_mutating_ops

        book = "/metering/pricing/rate-cards/{book_id}/publishes"
        marked = {(method, path): getattr(view, "_audit_actions", ())
                  for method, path, view in _iter_mutating_ops()
                  if path.startswith(book)}

        self.assertEqual(marked, {
            ("POST", book): (DECLARED,),
            ("POST", f"{book}/{{publish_id}}/publish"): (PUBLISHED,),
            ("DELETE", f"{book}/{{publish_id}}"): (DISCARDED,),
        })
