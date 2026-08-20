"""A Resolution Run is executed at the surface, by an admin, on three axes
(#363, spec §10, rulings 12a–12c).

The half of the mechanism a tenant actually touches. What each class holds:

* *Only an admin may run one* — every lower role refused at the route, and the
  floor argued rather than guessed: a run writes money-adjacent numbers into
  closed periods' reporting, it is irreversible under the receipt's sealing
  rule, and there is no second act to undo one with.
* *The selector is three axes and never a predicate* — each axis alone and all
  three together, and a body carrying a condition of its own refused rather
  than silently dropped.
* *It is governance, and the ledger says who and what* — one registered action,
  recording the actor and the selector, with the route on no exemption list.
* *Running it twice is not an error* — the second call answers an outcome, not
  a refusal, which is the property a guard placed above the work would destroy.

**THE RETIRED WORDS THIS MODULE NEVER SPELLS.** The book discriminator is
carried by `pricing/tests/_helpers` for its callers, and the receipt column is
addressed through `Posting.RECEIPT_COLUMN`.
"""
import json

from django.test import Client, TestCase

from apps.metering.pricing.models import ResolutionRun
from apps.metering.pricing.tests._helpers import (
    ONE_CALL, RECOVERABLE_QUANTITY as QUANTITY, WHAT_IT_COST,
    a_tenant_with_unresolved_postings, an_unresolved_posting,
    declares_a_markup)
from apps.metering.usage.models import Posting
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.audit.actions import is_registered_action
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.models import AuditRecord
from apps.platform.customers.models import Customer
from apps.platform.event_types.tests._helpers import declares_a_quantity
from apps.platform.membership.roles import ADMIN, READ, WRITE
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.vocabulary import PRICING_STATUS_KNOWN, PRICING_STATUS_UNKNOWN

#: The route, as the contract publishes it.
RUNS = "/api/v1/metering/pricing/resolution-runs"
EXECUTED = "resolution_run.executed"
RESOURCE_TYPE = "resolution_run"


class _ATenantWithSomethingToRecoverMixin:

    def setUp(self):
        self.http = Client()
        # The seed is the service module's own, from `pricing/tests/_helpers`:
        # what a run repairs is the same state at both seams, and a second copy
        # of it here is a second thing to edit the day the recording path's
        # answer moves (`docs/conventions/testing.md`).
        self.tenant, self.customer = a_tenant_with_unresolved_postings()
        self.key, self.raw_key = TenantApiKey.create_key(self.tenant, label="k")

    def a_posting(self, key, **fields):
        """A posting with a cost UBB knows and a price no rule ever gave it —
        which is the state a run exists to repair."""
        return an_unresolved_posting(self.tenant, self.customer, key, **fields)

    def _as(self, role):
        """The same key, at a role. The floor reads the principal's own role,
        so this is the whole of what a lower principal is."""
        TenantApiKey.objects.filter(pk=self.key.pk).update(role=role)
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def execute(self, body=None, role=ADMIN):
        return self.http.post(RUNS, data=json.dumps(body or {}),
                              content_type="application/json", **self._as(role))


class OnlyAnAdminMayRunOneTest(
        _ATenantWithSomethingToRecoverMixin, TestCase):
    """Ruling 12a. The highest floor UBB has, and every lower role refused."""

    def setUp(self):
        super().setUp()
        self.posting = self.a_posting("k1")
        declares_a_markup(self.tenant, percentage_micros=0)

    def test_every_lower_role_is_refused_at_the_route(self):
        for role in (READ, WRITE):
            with self.subTest(role=role):
                answered = self.execute(role=role)

                self.assertEqual(answered.status_code, 403)
                self.assertEqual(answered.json()["type"].rsplit("/", 1)[-1],
                                 "forbidden")

    def test_a_refused_request_completes_nothing_and_records_nothing(self):
        """A floor that refused after the work would be a floor in name only."""
        self.execute(role=READ)

        self.posting.refresh_from_db()
        self.assertEqual(self.posting.pricing_status, PRICING_STATUS_UNKNOWN)
        self.assertEqual(ResolutionRun.objects.count(), 0)
        self.assertFalse(AuditRecord.objects.filter(action=EXECUTED).exists())

    def test_an_admin_runs_one_and_it_completes(self):
        answered = self.execute()

        self.assertEqual(answered.status_code, 200)
        self.posting.refresh_from_db()
        self.assertEqual(self.posting.pricing_status, PRICING_STATUS_KNOWN)
        self.assertEqual(self.posting.billed_cost_micros, WHAT_IT_COST)

    def test_the_route_declares_the_floor_the_walker_reads(self):
        """The declaration beside the enforcement, because the carve-table
        walker reads the declaration and a route enforcing without declaring
        would pass one and not the other."""
        from api.v1.metering_endpoints import execute_resolution_run

        self.assertEqual(execute_resolution_run._role_floor, ADMIN)


class TheSelectorIsThreeAxesAndNeverAPredicateTest(
        _ATenantWithSomethingToRecoverMixin, TestCase):
    """Ruling 12b: it offers a filter, on the axes the rule ladder uses."""

    def setUp(self):
        super().setUp()
        self.other = Customer.objects.create(
            tenant=self.tenant, external_id="other")
        self.mine = self.a_posting("mine")
        self.elsewhere = self.a_posting("elsewhere", event_type="other.call")
        result = UsageService.record_usage(
            self.tenant, self.other, "corr-theirs", "theirs",
            event_type="chat", measurements={QUANTITY: ONE_CALL})
        self.theirs = Posting.objects.get(id=result["event_id"])
        declares_a_markup(self.tenant, percentage_micros=0)

    def priced(self, posting):
        posting.refresh_from_db()
        return posting.pricing_status == PRICING_STATUS_KNOWN

    def test_a_date_range_alone(self):
        answered = self.execute({
            "selected_from": (self.mine.effective_at
                              .replace(microsecond=0).isoformat()),
            "selected_to": "2099-01-01T00:00:00Z"})

        self.assertEqual(answered.status_code, 200)
        self.assertEqual(answered.json()["postings_examined"], 3)

    def test_a_customer_alone(self):
        answered = self.execute({"selected_customer_id": str(self.other.id)})

        self.assertEqual(answered.status_code, 200)
        self.assertEqual(answered.json()["prices_resolved"], 1)
        self.assertTrue(self.priced(self.theirs))
        self.assertFalse(self.priced(self.mine))

    def test_an_event_type_alone(self):
        answered = self.execute({"selected_event_type": "other.call"})

        self.assertEqual(answered.json()["prices_resolved"], 1)
        self.assertTrue(self.priced(self.elsewhere))
        self.assertFalse(self.priced(self.mine))

    def test_all_three_together(self):
        answered = self.execute({
            "selected_from": "2000-01-01T00:00:00Z",
            "selected_to": "2099-01-01T00:00:00Z",
            "selected_customer_id": str(self.customer.id),
            "selected_event_type": "chat"})

        self.assertEqual(answered.json()["prices_resolved"], 1)
        self.assertTrue(self.priced(self.mine))
        self.assertFalse(self.priced(self.theirs))
        self.assertFalse(self.priced(self.elsewhere))

    def test_none_of_them_reaches_every_unresolved_posting(self):
        answered = self.execute({})

        self.assertEqual(answered.json()["prices_resolved"], 3)

    def test_a_body_carrying_a_condition_of_its_own_is_refused(self):
        """⚠ AC 7, and the reason it needs a refusal rather than a silence.

        Django Ninja DROPS a body key no schema names, so without
        `extra="forbid"` a caller sending a predicate would get a 200 and a run
        that quietly ignored it — a filter that looks honoured and is not. The
        refusal is what makes *this surface accepts no predicate* a fact.
        """
        answered = self.execute({"where": "billed_cost_micros IS NULL"})

        self.assertEqual(answered.status_code, 422)
        self.assertEqual(answered.json()["type"].rsplit("/", 1)[-1],
                         "validation_error")
        self.assertEqual(ResolutionRun.objects.count(), 0)

    def test_a_customer_of_another_tenant_is_not_found_rather_than_ignored(self):
        """A selector naming somebody this tenant cannot see is a 404, not a
        run over everything: an axis that silently widened when it could not be
        resolved would be the opposite of a filter."""
        elsewhere = Tenant.objects.create(name="Other", products=["metering"])
        theirs = Customer.objects.create(tenant=elsewhere, external_id="x")

        answered = self.execute({"selected_customer_id": str(theirs.id)})

        self.assertEqual(answered.status_code, 404)
        self.assertEqual(ResolutionRun.objects.count(), 0)


class ItIsGovernanceAndTheLedgerSaysWhoAndWhatTest(
        _ATenantWithSomethingToRecoverMixin, TestCase):
    """Ruling 12a's other half: a run is recorded, with its actor and its
    selector, under a registered name."""

    def setUp(self):
        super().setUp()
        self.a_posting("k1")
        declares_a_markup(self.tenant, percentage_micros=0)

    def test_the_action_is_registered(self):
        self.assertTrue(is_registered_action(EXECUTED))

    def test_the_recording_function_refuses_an_unregistered_name(self):
        """The mechanism that makes the registry contractual rather than
        advisory — asserted here because it is what a route and its action
        being one commit rests on."""
        with self.assertRaisesRegex(ValueError, "unregistered audit action"):
            audit_record(action="resolution_run.rerun",
                         tenant_id=self.tenant.id,
                         resource_type=RESOURCE_TYPE)

    def test_the_route_carries_the_marker_the_mutating_route_pin_reads(self):
        from api.v1.metering_endpoints import execute_resolution_run

        self.assertEqual(execute_resolution_run._audit_actions, (EXECUTED,))

    def test_the_route_is_not_on_the_audit_sweeps_exemption_list(self):
        """The exemption list is telemetry, and a run is the opposite of it."""
        from api.v1.tests.test_audit_sweep import _EXEMPT

        self.assertNotIn(("POST", "/metering/pricing/resolution-runs"), _EXEMPT)

    def test_the_entry_records_the_actor_and_the_selector(self):
        answered = self.execute({"selected_event_type": "chat"})

        entry = AuditRecord.objects.get(action=EXECUTED)
        self.assertEqual(entry.resource_type, RESOURCE_TYPE)
        self.assertEqual(entry.resource_id, answered.json()["id"])
        self.assertEqual(entry.metadata["selector"]["selected_event_type"],
                         "chat")
        self.assertEqual(entry.actor_kind, "api_key")
        self.assertEqual(entry.actor_id, str(self.key.id))

    def test_the_record_and_the_entry_name_the_same_actor(self):
        """Two records of one act, taken from one contextvar — so a governance
        reader cannot find two answers to *who ran this*."""
        answered = self.execute()

        run = ResolutionRun.objects.get(id=answered.json()["id"])
        entry = AuditRecord.objects.get(action=EXECUTED)
        self.assertEqual((run.actor_kind, run.actor_id, run.actor_display),
                         (entry.actor_kind, entry.actor_id,
                          entry.actor_display))
        self.assertEqual(answered.json()["actor_kind"], entry.actor_kind)


class RunningItTwiceIsNotAnErrorTest(
        _ATenantWithSomethingToRecoverMixin, TestCase):
    """⚠ AC 13. A run is idempotent BY CONSTRUCTION — everything it completes
    leaves the set it selects from — and the thing that would break that is a
    refusal placed above the work, which is why there is none.

    A guard reading *that selector has already been run* or *there is nothing
    to do* would refuse the second call forever, while every criterion still
    read as satisfied.
    """

    def setUp(self):
        super().setUp()
        self.posting = self.a_posting("k1")
        declares_a_markup(self.tenant, percentage_micros=0)

    def test_the_second_call_answers_an_outcome_and_not_a_refusal(self):
        first = self.execute()
        second = self.execute()

        self.assertEqual([first.status_code, second.status_code], [200, 200])
        self.assertEqual(first.json()["prices_resolved"], 1)
        self.assertEqual(second.json()["prices_resolved"], 0)
        self.assertEqual(second.json()["postings_examined"], 0)

    def test_the_amount_the_first_run_wrote_is_not_touched_again(self):
        self.execute()
        self.execute()

        self.posting.refresh_from_db()
        self.assertEqual(self.posting.billed_cost_micros, WHAT_IT_COST)

    def test_each_execution_is_its_own_act_in_the_ledger(self):
        """Two runs are two acts and the ledger says so: deduplicating the
        RECORD would lose the fact that somebody ran one, which is exactly what
        the entry exists for."""
        self.execute()
        self.execute()

        self.assertEqual(ResolutionRun.objects.count(), 2)
        self.assertEqual(AuditRecord.objects.filter(action=EXECUTED).count(), 2)


class ATenantThatBillsNobodyMayStillRunOneTest(TestCase):
    """⚠ THE PRODUCT GATE IS METERING'S AND NOT BILLING'S, WHICH IS A DECISION.

    The pricing routes beside this one gate on `billing`, because writing a
    price rule is a billing act. A run is not: it completes BOTH pairs, and one
    of them — a supplier cost UBB never learned — is metering's own, owed to a
    tenant who charges nobody through UBB and still wants their cost reporting
    to stop understating what their traffic cost. The wider gate admits nothing
    extra on the price side: such a tenant's postings price to `not_applicable`,
    which is not a completable status.
    """

    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(
            name="Meters only", products=["metering"])
        self.key, self.raw_key = TenantApiKey.create_key(self.tenant, label="k")

    def test_the_route_admits_a_tenant_with_no_billing_product(self):
        answered = self.http.post(
            RUNS, data=json.dumps({}), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

        self.assertEqual(answered.status_code, 200)
        self.assertEqual(answered.json()["postings_examined"], 0)

    def test_a_tenant_without_metering_is_still_refused(self):
        """The gate that remains, so the widening is not a removal."""
        Tenant.objects.filter(pk=self.tenant.pk).update(products=[])

        answered = self.http.post(
            RUNS, data=json.dumps({}), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

        self.assertEqual(answered.status_code, 403)


class TheResponseSaysWhatTheRunDidTest(
        _ATenantWithSomethingToRecoverMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.posting = self.a_posting("k1")
        declares_a_markup(self.tenant, percentage_micros=0)

    def test_the_whole_body_is_the_published_shape(self):
        """Asserted as the WHOLE body rather than key by key: a per-key check
        passes while a field nobody published rides along beside it."""
        body = self.execute({"selected_event_type": "chat"}).json()
        run = ResolutionRun.objects.get(id=body["id"])

        self.assertEqual(body, {
            "id": str(run.id),
            "executed_at": run.created_at.isoformat(),
            "actor_kind": "api_key",
            "actor_id": str(self.key.id),
            "actor_display": run.actor_display,
            "selector": {"selected_from": None, "selected_to": None,
                         "selected_customer_id": None,
                         "selected_event_type": "chat"},
            "postings_examined": 1,
            "costs_settled": 0,
            "prices_resolved": 1,
            "postings_left_unresolved": 0,
            "more_to_do": False,
        })

    def test_the_record_and_the_published_selector_name_the_same_axes(self):
        """The selector is assembled from the RECORD's own reader and published
        through a schema, and the two are different files. A key added to one
        and not the other would leave the wire and the record describing the
        same run differently — so the two sets are compared rather than the
        agreement being a property of whoever edits both."""
        from api.v1.schemas import ResolutionRunSelectorOut

        run = ResolutionRun.objects.create(tenant=self.tenant)

        self.assertEqual(set(run.selector),
                         set(ResolutionRunSelectorOut.model_fields))
