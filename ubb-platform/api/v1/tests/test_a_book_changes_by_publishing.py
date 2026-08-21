"""A book's mutation surface becomes one act, published (#358).

Declaring a change, publishing it and discarding it — three routes, three audit
actions, one record. The service module in `apps/metering/pricing/tests/`
carries the behaviour: one clock over the boundary, the record's immutability
through three doors, the diff computed at the effective instant. What is asked
HERE is what only the route can answer — the request shape a tenant sends, the
refusals it gets back, the governance entries the acts leave, and the vocabulary
the contract publishes.

**⚠ THE CHANGE BODY NAMES A GROUPING FIELD BY THE TENANT'S OWN KEY, AND THAT IS
WHY SLOT SEVEN WAS REACHABLE HERE FIRST.** When this act landed, the immediate
reprice body named six of the ten slots by their physical spelling, so a rule
pinned on the seventh could not be addressed through it at all — a functional
gap, not a naming one. A change body carries an object keyed by what the tenant
declared, so every slot was reachable through this route while four were
reachable through no other. One case below is that gap, closed.

⚠ **IT IS NO LONGER THE ONLY ROUTE THAT CAN REACH THEM (#366).** The immediate
reprice body publishes all ten slots now, under the column names, and
`api/v1/tests/test_a_rate_on_any_slot_can_be_repriced.py` reprices a rule pinned
on the seventh end to end through exactly that route. So the case below is no
longer evidence that this act is the ONLY way in; what it still asserts, and
what nothing else does, is that a tenant can address a slot **without knowing
which slot it is** — by the key they declared, which survives a rebinding that
a body naming the column silently would not.

**GOVERNANCE, NOT TELEMETRY.** All three acts decide what a customer is charged,
so none of them takes the audit sweep's exemption list — that carve is for usage
ingestion and the start-gate call.
"""
import json
from datetime import timedelta
from uuid import uuid4

from django.test import Client, TestCase
from django.utils import timezone

from apps.metering.pricing.models import PricingBookPublish, Rate
from apps.metering.pricing.tests._helpers import (
    rate_in_default_book, the_book_holding)
from apps.platform.audit.actions import is_registered_action
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.models import AuditRecord
from apps.platform.event_types.tests._helpers import declares_a_quantity
from apps.platform.grouping_fields.services import DimensionService
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.scheduling import MAX_FORWARD_SCHEDULING_DAYS
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


def _in_days(days):
    """An instant `days` from now, as a tenant would state it.

    Relative rather than a fixed date, because the horizon is measured from the
    request's own moment. The calendar cases — *"the same day next year"* across
    a leap year — are held where the clock is a parameter,
    `core/tests/test_scheduling.py`, rather than by patching one here.
    """
    return timezone.now() + timedelta(days=days)


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

    def declare_at(self, effective_at, *changes):
        """The same body, dated. Separate from `declare` on purpose: the great
        majority of cases here are about a change rather than about when it
        lands, and a body carrying no instant is the one they should send."""
        return self._post(self.publishes, {
            "changes": list(changes) or [
                self.a_change(rate_per_unit_micros=AFTER)],
            "effective_at": effective_at.isoformat()})


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
        """Declare a reprice, then close the rule through the OTHER surface.

        ⚠ Two drafts naming one rule is NOT this state, and checking was worth
        it: a change names a rule by its identity — the quantity and the
        selectors — rather than by version, so a second draft repricing the
        replacement is perfectly coherent and publishes fine. What strands a
        draft is the rule acquiring a close it cannot move: the surviving
        immediate route stamps `valid_to` at the moment of the call, which is
        AFTER this draft was declared, so at the draft's own effective instant
        the rule is still in force and already closing — and `Rate.valid_to` is
        declared set_once, so no publish may move it.

        ⚠ **THE OTHER SURFACE IS NOW THE ATOMIC REPRICE, NOT THE IMMEDIATE
        RETIRE (#367).** The retire route is deleted; what still closes a rule
        the instant it is called is the reprice, which supersedes the rule and
        opens a replacement. The stranding is the same and for the same reason
        — an unmovable close standing between the draft and its instant — and
        it is worth saying that the state stops being reachable at all when the
        last immediate route leaves with #369, at which point this class is
        asserting about something that cannot happen.
        """
        draft = self.declare().json()
        closed = self._post(
            f"/api/v1/metering/pricing/rate-cards/{self.book.id}/publish",
            {"changes": [self.a_change(rate_per_unit_micros=AFTER + 1)]})
        self.assertEqual(closed.status_code, 200, closed.content)
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


class AChangeCanBeDatedForwardTest(_APublishingTenantMixin, TestCase):
    """`effective_at` is what dates a change forward, and omitting it means now
    (#359).

    A tenant who has agreed a rise from the first of next month states that
    instant here and stops having to remember it. Nothing runs at the instant:
    the rows are written when the publish lands and the boundary is a value the
    resolver reads, which is asserted where the writing happens, in
    `pricing/tests/test_a_publish_can_be_dated_forward.py`. What is asked HERE
    is what only the route can answer — that the instant crosses the wire, that
    it is carried onto the record, and which instants are refused.
    """

    def test_a_declared_change_carries_the_instant_it_was_dated_for(self):
        boundary = _in_days(30)

        body = self.declare_at(boundary).json()

        self.assertEqual(body["effective_at"], boundary.isoformat())
        record = PricingBookPublish.objects.get(id=body["id"])
        self.assertEqual(record.effective_at, boundary)

    def test_omitting_the_instant_still_means_now(self):
        """The property #358 shipped, unchanged by the field arriving.

        A body with no instant is the overwhelmingly common one and it must not
        have started meaning something else.
        """
        before = timezone.now()

        body = self.declare().json()

        record = PricingBookPublish.objects.get(id=body["id"])
        self.assertGreaterEqual(record.effective_at, before)
        self.assertLessEqual(record.effective_at, timezone.now())

    def test_publishing_a_forward_dated_change_writes_the_future_boundary(self):
        boundary = _in_days(30)
        declared = self.declare_at(boundary).json()

        self.assertEqual(
            self._post(f"{self.publishes}/{declared['id']}/publish")
            .status_code, 200)

        self.rule.refresh_from_db()
        self.assertEqual(self.rule.valid_to, boundary)
        self.assertLess(timezone.now(), boundary)


class AnInstantBeyondTheHorizonIsRefusedTest(_APublishingTenantMixin,
                                             TestCase):
    """Ruling 14a: 366 days, a platform constant, and a named error.

    The bound exists to stop **a typo becoming a permanent invisible schedule**,
    which is the only failure mode anybody has described. The calendar
    arithmetic and the "no tenant setting moves it" claim are held at the rail
    itself, in `core/tests/test_scheduling.py`; what is asserted here is that
    the route enforces it and answers with a code a tenant's automation can tell
    apart from every other reason a body is refused.
    """

    def test_exactly_366_days_ahead_is_accepted(self):
        # Exactly the bound, and safe against the clock moving between here and
        # the handler: the route reads a LATER `now`, so its horizon is a later
        # instant than this one and an instant on the bound stays inside it.
        response = self.declare_at(_in_days(MAX_FORWARD_SCHEDULING_DAYS))

        self.assertEqual(response.status_code, 200, response.content)

    def test_367_days_ahead_is_refused_with_its_own_code(self):
        response = self.declare_at(_in_days(367))

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "effective_at_too_far_ahead")

    def test_a_naive_instant_is_refused(self):
        """Not a moment at all, and told so by its own code.

        A naive datetime compared against an aware one raises rather than
        answering, so this refusal is what stands between a malformed body and
        a 500.
        """
        response = self._post(self.publishes, {
            "changes": [self.a_change(rate_per_unit_micros=AFTER)],
            "effective_at": "2027-06-01T00:00:00"})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "effective_at_naive")

    def test_an_instant_in_the_past_is_refused(self):
        """A change is dated forward or not at all.

        A boundary behind the present is a retroactive reprice — the thing
        `Rate.valid_from` is declared FROZEN to prevent — rather than a
        schedule. It carries a code of its own for the reason the horizon does:
        on this route `validation_error` already means *"you have not declared
        that grouping field"* and *"that rule is not there to reprice"*, so a
        third meaning would leave a caller unable to tell a date it can fix from
        a body it cannot.
        """
        response = self.declare_at(_in_days(-1))

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "effective_at_in_past")

    def test_the_four_refusals_are_told_apart_by_their_codes(self):
        """The whole point of naming them, asserted as a set.

        Four ways a stated instant can be wrong, four codes, and none of them
        the generic one this route already uses for two other things. A caller
        branching on `code` can act on each differently — fix the date, wait,
        stop sending a date at all, or move it past what is already scheduled.

        ⚠ **THE FOURTH IS THE ONLY ONE THAT DEPENDS ON THE BOOK** (#360), which
        is why it is provoked last: it needs a boundary to be behind, so the
        publish that schedules one has to happen first, and it would change
        the answers of nothing above it.
        """
        naive = self._post(self.publishes, {
            "changes": [self.a_change(rate_per_unit_micros=AFTER)],
            "effective_at": "2027-06-01T00:00:00"})
        past = self.declare_at(_in_days(-1))
        ahead = self.declare_at(_in_days(400))
        self._schedule(_in_days(30))

        self.assertEqual(
            [naive.json()["code"], past.json()["code"], ahead.json()["code"],
             self.declare_at(_in_days(10)).json()["code"]],
            ["effective_at_naive", "effective_at_in_past",
             "effective_at_too_far_ahead",
             "effective_at_before_scheduled_boundary"])

    def test_a_change_behind_a_scheduled_boundary_is_refused_by_the_route(self):
        """Ruling 14b, at the surface a tenant meets it on.

        The book's diary is written forwards: a change may follow what is
        already scheduled or land exactly on it, and never slip in behind.
        """
        self._schedule(_in_days(30))

        response = self.declare_at(_in_days(10))

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"],
                         "effective_at_before_scheduled_boundary")

    def test_a_change_dated_at_the_scheduled_boundary_is_accepted(self):
        """The reversal case, at the route.

        A tenant who scheduled a rise and changed their mind declares the
        reversal at the very same instant. Equal is admitted, and it has to be:
        it is the whole of how a scheduled change is taken back.
        """
        boundary = _in_days(30)
        self._schedule(boundary)

        response = self.declare_at(boundary, self.a_change(
            rate_per_unit_micros=BEFORE))

        self.assertEqual(response.status_code, 200, response.content)

    def test_a_book_may_carry_more_than_one_scheduled_change(self):
        """The one-pending-publish limit is gone (ruling 14b).

        Two boundaries outstanding at once, both still in the future, and the
        second was accepted because it follows the first rather than because
        the first had taken effect.
        """
        self._schedule(_in_days(30))

        response = self._schedule(_in_days(60))

        self.assertEqual(response.status_code, 200, response.content)

    def _schedule(self, effective_at, *changes):
        """Declare a change at `effective_at` and publish it, through the route.

        Publishing is what writes a boundary into the book — a draft writes no
        rule, so a declaration alone leaves nothing for a later change to be
        behind. Every case above that needs a scheduled boundary needs both
        acts, which is why they are one call.
        """
        declared = self.declare_at(effective_at, *changes)
        self.assertEqual(declared.status_code, 200, declared.content)
        return self._post(
            f"{self.publishes}/{declared.json()['id']}/publish")


class TheRefusalSpendsNothingTest(_APublishingTenantMixin, TestCase):
    """⚠ A REFUSAL ADDED TO A ROUTE CAN SPEND WHAT IT REFUSES.

    This programme has already paid for that once — a `422` that sat underneath
    an admission and permanently burned tenant keyspace on requests that
    recorded nothing. So the instant is checked before anything else happens,
    and these are what say so rather than the comment beside it.

    **WHAT SITS ABOVE IT, NAMED.** Textually, one statement: the deferred
    `book_service` import ADR-001's boundary discipline puts at the top of every
    handler here, which does nothing. Then the authenticator, which buffers the
    key's last-used marker on *every* request whatever the answer — a property
    of authenticating rather than something this refusal decides — and the role
    floor, which is a pure read of the principal's role. Nothing else: not the
    book lookup, not the product gate, not the slot registry read, and
    therefore nowhere near the two statements that spend anything, which are
    `BookService.declare` and `audit_record`.

    ⚠ **AND ONLY TWO OF THESE CASES ARE LOAD-BEARING AGAINST A DELETED CHECK.**
    Declaring writes no rule, so *the book is where it was* stays green whether
    the instant was refused or accepted — it guards a different regression (a
    declaration that started writing) and is kept for that, not counted as
    evidence about the refusal. Measured: deleting the horizon refusal reddens
    the record case, the audit case and the ordering pin, and leaves that one
    green.
    """

    def test_a_refused_declaration_leaves_no_record(self):
        before = PricingBookPublish.objects.count()

        self.declare_at(_in_days(400))

        self.assertEqual(PricingBookPublish.objects.count(), before)

    def test_a_refused_declaration_records_no_attempt(self):
        """No audit entry of ANY kind, rather than "not the declared one".

        Naming the action a refusal must not have written would leave a second
        entry riding along beside it invisible, and would spell a name this
        assertion has no business spelling.
        """
        self.declare_at(_in_days(400))

        self.assertEqual(AuditRecord.objects.filter(
            tenant_id=self.tenant.id).count(), 0)

    def test_a_refused_declaration_leaves_the_book_exactly_where_it_was(self):
        self.declare_at(_in_days(400))

        self.rule.refresh_from_db()
        self.book.refresh_from_db()
        self.assertEqual(self.rule.rate_per_unit_micros, BEFORE)
        self.assertIsNone(self.rule.valid_to)
        self.assertEqual(self.book.version, 1)
        self.assertEqual(Rate.objects.filter(tenant=self.tenant).count(), 1)

    def test_the_check_runs_before_the_book_is_even_looked_up(self):
        """The ORDER, pinned — it is invisible in a diff otherwise.

        A book id this tenant does not own would 404 if anything above the
        check touched the database. It answers the horizon refusal instead,
        which is only possible if the check ran first. Move the check below the
        lookup and this test reports a 404.
        """
        unknown_book = self.publishes.replace(str(self.book.id), str(uuid4()))

        response = self._post(unknown_book, {
            "changes": [self.a_change(rate_per_unit_micros=AFTER)],
            "effective_at": _in_days(400).isoformat()})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "effective_at_too_far_ahead")

    def test_a_valid_instant_reaches_the_lookup_and_gets_the_404(self):
        """The other half, so the case above cannot pass by the route being
        broken for every request rather than by the ordering being right."""
        unknown_book = self.publishes.replace(str(self.book.id), str(uuid4()))

        response = self._post(unknown_book, {
            "changes": [self.a_change(rate_per_unit_micros=AFTER)],
            "effective_at": _in_days(30).isoformat()})

        self.assertEqual(response.status_code, 404)


class TheContractPublishesEveryTermTheServiceMovesTest(TestCase):
    """The published terms and everything a publish can move are one set.

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
        from apps.metering.pricing.services.book_service import _RULE_FIELDS

        self.assertEqual(set(RuleTermsOut.model_fields), set(_RULE_FIELDS))


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
        from api.v1.tests.test_audit_sweep import mutating_operations

        book = "/metering/pricing/rate-cards/{book_id}/publishes"
        marked = {(method, path): getattr(view, "_audit_actions", ())
                  for method, path, view in mutating_operations()
                  if path.startswith(book)}

        self.assertEqual(marked, {
            ("POST", book): (DECLARED,),
            ("POST", f"{book}/{{publish_id}}/publish"): (PUBLISHED,),
            ("DELETE", f"{book}/{{publish_id}}"): (DISCARDED,),
        })


class EveryChangeToABookGoesThroughAPublishTest(TestCase):
    """#367: no unversioned immediate mutation act is left on a book.

    This module's own headline, finally true of the whole surface rather than
    of the act it describes — which is why it lives here, beside the three
    routes that replaced the ones #367 deleted, rather than with the deletion.

    ⚠ **THE ASSERTION IS OVER THE ROUTES THAT COMMIT DID NOT WRITE.** Checking
    that the two deleted routes are gone would be a claim about a diff; what
    matters is the whole surface, and #361 already paid once for the difference
    — three immediate routes each took a bare book id, and a claim made about
    the two that declare a draft said nothing about them.

    So this enumerates every mutating operation on the book's path family off
    the live API and asserts each one either records a publish act or is the
    atomic reprice, which DOES version the book. There is no third kind left.

    ⚠ It walks the router through `mutating_operations`, which is the audit
    sweep's own walker and public for exactly this second caller — a private
    copy would be two searches agreeing with each other rather than evidence.
    """

    #: The one immediate act that survives, and why it is not the thing this
    #: test refuses. It bumps the book's version and closes each superseded
    #: rule at a boundary, so the change it makes is a versioned one; what it
    #: is not is FORWARD-DATED. It leaves with the rest of this slice's
    #: vocabulary (#369) and the customer's own book is already out of its
    #: reach.
    THE_VERSIONED_IMMEDIATE_ACT = "/metering/pricing/rate-cards/{book_id}/publish"

    def _book_family(self):
        from api.v1.tests.test_audit_sweep import mutating_operations

        family = "/metering/pricing/rate-cards/{book_id}"
        return [(method, path) for method, path, _ in mutating_operations()
                if path == family or path.startswith(family + "/")]

    def test_the_walker_still_sees_the_book_family(self):
        self.assertTrue(self._book_family(),
                        "no mutating route was found under the book's path, "
                        "so every assertion below is vacuous")

    def test_no_route_writes_a_rule_outside_a_publish(self):
        """Every survivor names the publish record or is the versioned reprice.

        A route that added or retired a rule directly would answer neither
        description, which is what the two deletions in this commit removed.
        """
        stray = [(method, path) for method, path in self._book_family()
                 if "publishes" not in path
                 and path != self.THE_VERSIONED_IMMEDIATE_ACT]
        self.assertEqual(stray, [])

    def test_the_rules_collection_takes_no_mutating_method(self):
        """Named separately because it is the one that changed.

        `POST .../rates` and `DELETE .../rates/{rate_id}` were the immediate
        add and retire. Both are gone, and the collection now answers reads
        only — which is the sentence the acceptance criterion asks for, made
        against the router rather than against the diff.
        """
        rules = [(method, path) for method, path in self._book_family()
                 if "/rates" in path]
        self.assertEqual(rules, [])
