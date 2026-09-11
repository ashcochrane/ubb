"""One-rule enforcement — the #37 acceptance pins (spec §L, task legs).

Pin 1  — the tipping event lands and bills, and the task limit bites on the
         one recording path — at record time, with nothing deferred to a
         later sweep (#192). Since #452 the tipping event lands EXACTLY on
         the ceiling: at or above the line stops, everywhere.
Pin 2  — events on a killed task land, bill, and count into both totals.
Pin 3  — Wallet carries no floor CHECK constraint (ADR-002 pin): spend policy
         is enforced in application code, never a DB constraint on the ledger.
         (The per-task floor snapshot this pin used to also cover was deleted
         — see the billing-surface-correctness plan, task 1 — in favor of the
         durable drawdown lane's hard-floor stop, the correct scope for a
         wallet-wide fact.)
Pin 7  — every recorded event answers 200; no code path returns 429/409 for a
         usage report.
Pin 14 — only the provider (COGS) total races the task limit; both totals on
         the record and the response.
Pin 15 — RETIRED by #321, and by deletion rather than rehoming. It pinned a
         coverage gate that refused a limited start unless the tenant had set
         a flag promising full cost coverage. #320 removed the premise (an
         uncosted event is now recorded with its cost unresolved rather than
         counted as zero), so the gate was refusing work on a promise nothing
         keeps. What survives of it is the half that was never about coverage:
         that an explicit ceiling beats the tenant default, and that a start
         with no ceiling anywhere is uncapped — kept below under its own name.
Pin 16 — the label fallback is removed: metadata={"task": ...} with no task_id
         gets no unit attribution, no limit, no kill.
Pin 17 — the clean-cut sweep: no run-era event type in the catalog, neither
         retired Redis key family is ever written, the old per-task cap
         config is gone, and no API/SDK/event surface answers to a run-era
         name.
"""
import json
import uuid
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, Client

from apps.billing.gating.models import RiskConfig
from apps.billing.gating.patrol import sweep_over_limit_tasks
from apps.billing.tenant_billing.models import BillingTenantConfig
from apps.billing.wallets.models import Wallet
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.metering.pricing.tests._helpers import (
    a_rule_that_prices_what_it_measures, priced_at, what_it_bills)
from apps.platform.event_types.tests._helpers import (
    DECLARED, declares_a_caller_supplied_cost)
from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import TaskKilled
from apps.platform.work.models import Task, TaskType
from apps.platform.work.services import TaskService
from apps.platform.work import reasons
from apps.platform.work.services import STOP_CAUSE_KEY
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.vocabulary import (
    CEILING_STATUS_CEILING_REACHED, CEILING_STATUS_INDETERMINATE,
    CEILING_STATUS_NOT_APPLICABLE, CEILING_STATUS_WITHIN_CEILING,
    COSTING_STATUS_UNRESOLVED,
    TASK_OUTCOME_DELIVERED, TASK_STATUS_ACTIVE, TASK_STATUS_COMPLETED,
    TASK_TYPE_KIND_TASK,
    TASK_STATUS_KILLED, TRIGGER_SOURCE_USAGE_INGEST)


class OneRulePinTestBase(TestCase):
    def setUp(self):
        cache.clear()
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="OneRule", products=["metering", "billing"],
            billing_mode="prepaid",
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.wallet = Wallet.objects.create(
            customer=self.customer, balance_micros=100_000_000)
        declares_a_caller_supplied_cost(self.tenant, DECLARED)
        a_rule_that_prices_what_it_measures(self.tenant)

    def tearDown(self):
        cache.clear()

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _task(self, limit=10_000_000, balance=100_000_000):
        return TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=balance,
            task_cogs_ceiling_micros=limit,
            billing_owner_id=self.customer.id)

    def _record(self, **extra):
        data = {
            "customer_id": str(self.customer.id),
            "idempotency_key": f"idem-{uuid.uuid4()}",
            # Every body here states the supplier's own cost, admissible only
            # against an Event Type that declares it arrives on the call
            # (#324). `extra` still wins, so a test may name another key.
            "event_type": DECLARED,
        }
        # ⚠ WHAT AN EVENT BILLS IS CONFIGURED, NOT SENT (#365). Callers say
        # `bills=N` exactly as they used to say the deleted request field; the
        # shared door turns it into the quantities this tenant's own rule
        # charges N for, so one number goes in and no caller here learns which
        # key it lands under.
        data.update(what_it_bills(extra))
        data.update(extra)
        return self.http_client.post(
            "/api/v1/metering/usage", data=json.dumps(data),
            content_type="application/json", **self._auth())

    def _limit_events(self):
        return OutboxEvent.objects.filter(event_type=TaskKilled.EVENT_TYPE)

    def _start(self, **extra):
        """Register a unit of work through the one route that registers one.

        ⚠ THIS USED TO BE THE AFFORDABILITY CALL WITH A FLAG ON IT (#410).
        Registering work is `POST /api/v1/tasks` now — at the root, ungated,
        and with the caller's key required — so a refusal is an HTTP refusal
        rather than a verdict riding inside a 200.
        """
        data = {"customer_id": str(self.customer.id),
                "idempotency_key": f"attempt-{uuid.uuid4()}"}
        data.update(extra)
        return self.http_client.post(
            "/api/v1/tasks", data=json.dumps(data),
            content_type="application/json", **self._auth())

    def _started(self, **extra):
        """...and the body of a start that was admitted."""
        response = self._start(**extra)
        assert response.status_code == 200, response.json()
        return response.json()

    def _tenant_declares_a_default_ceiling(self, micros, *, contained=False):
        """The tenant's default COGS ceiling for work with no declared kind,
        at one altitude — a kernel setting on the tenant row (#453)."""
        rung = ("default_subtask_cogs_ceiling_micros" if contained
                else "default_task_cogs_ceiling_micros")
        setattr(self.tenant, rung, micros)
        self.tenant.save(update_fields=[rung])


@patch("apps.platform.events.tasks.process_single_event")
class Pin1SyncTippingEventTest(OneRulePinTestBase):
    """⚠ THE ARITHMETIC LANDS EXACTLY ON THE CEILING, DELIBERATELY (#452,
    #150 §10.3). Until slice 6 this pin tipped the unit one million micros
    OVER its ceiling, which the live lane's strictly-above compare and the
    patrol's at-or-above compare agreed on — and the disagreement between
    them, a unit landing ON the line, was never exercised. At or above the
    line stops, everywhere, so the boundary is now the pin: a pin is evidence
    of today, not a constraint on the re-model."""

    def test_tipping_event_lands_bills_and_kills(self, _mock):
        task = self._task(limit=10_000_000)
        # The kill executes on the recording transaction's on_commit (#112).
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._record(task_id=str(task.id),
                                provider_cost_micros=10_000_000,
                                bills=15_000_000)

        # The event that reached the ceiling answers 200 and is durably
        # recorded + billed — never rolled back.
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        event = Posting.objects.get(id=body["event_id"])
        self.assertEqual(event.billed_cost_micros, 15_000_000)
        self.assertEqual(event.provider_cost_micros, 10_000_000)
        self.assertEqual(event.task_id, task.id)
        self.assertEqual(OutboxEvent.objects.filter(
            event_type="usage.recorded").count(), 1)

        # Both totals include the tipping event; the task flipped to killed.
        task.refresh_from_db()
        self.assertEqual(task.total_provider_cost_micros, 10_000_000)
        self.assertEqual(task.total_billed_cost_micros, 15_000_000)
        self.assertEqual(task.status, TASK_STATUS_KILLED)
        self.assertEqual(task.metadata[STOP_CAUSE_KEY], reasons.TASK_COGS_CEILING)

        # The stop verdict rides the 200; the fan-out event fired exactly once.
        self.assertTrue(body["stop"])
        self.assertEqual(body["stop_reason"], reasons.TASK_COGS_CEILING)
        self.assertEqual(body["stop_scope"], "task")
        self.assertEqual(body["task_total_provider_cost_micros"], 10_000_000)
        self.assertEqual(body["task_total_billed_cost_micros"], 15_000_000)
        # The assessment beside the verdict says the same thing in the
        # registry's word, and the utilisation is the whole ceiling used.
        self.assertEqual(body["ceiling_status"], CEILING_STATUS_CEILING_REACHED)
        self.assertEqual(body["ceiling_used_percentage"], 100)
        self.assertEqual(body["ceiling_remaining_micros"], 0)
        # ...AND THE STOP HAS A TIPPING EVENT TO ATTRIBUTE: this report is
        # marked as the one that landed the unit on its ceiling, which the
        # strictly-above compare could not do for exactly this report — it
        # would have passed, and the patrol's kill an hour later would have
        # had no event to point at.
        (context,) = body["stop_context"]
        self.assertEqual(context["limit"], reasons.TASK_COGS_CEILING)
        self.assertIs(context["arrived_after"], False)
        self.assertEqual(self._limit_events().count(), 1)
        payload = self._limit_events().get().payload
        self.assertEqual(payload["reason_code"], reasons.TASK_COGS_CEILING)
        # WHICH MECHANISM APPLIED IT, beside why (#412). This crossing was
        # tipped by the usage report the test just made, and the field is what
        # tells a subscriber that apart from the patrol finding the same
        # crossing later — the reason string cannot, because both lanes reach
        # this one. Asserted through the ROUTE, on the emitted payload, since
        # a hand-built one would hard-code the key the producer sets.
        self.assertEqual(payload["trigger_source"], TRIGGER_SOURCE_USAGE_INGEST)
        self.assertEqual(payload["task_id"], str(task.id))
        self.assertEqual(payload["total_provider_cost_micros"], 10_000_000)
        self.assertEqual(payload["task_cogs_ceiling_micros"], 10_000_000)
        # And the patrol then finds nothing to sweep: the event that landed
        # the unit on its ceiling is the event that stopped it, so the repair
        # lane has nothing left to repair.
        self.assertEqual(sweep_over_limit_tasks(self.tenant), 0)
        self.assertEqual(self._limit_events().count(), 1)

    def test_one_micro_under_the_ceiling_is_not_a_crossing(self, _mock):
        """The other side of the line, so the pin above is about `>=` and
        not merely about a large enough number."""
        task = self._task(limit=10_000_000)
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._record(task_id=str(task.id),
                                provider_cost_micros=9_999_999,
                                bills=15_000_000)
        body = resp.json()
        self.assertFalse(body["stop"])
        self.assertIsNone(body["stop_reason"])
        self.assertEqual(body["ceiling_status"], CEILING_STATUS_WITHIN_CEILING)
        self.assertEqual(body["ceiling_used_percentage"], 99)
        self.assertEqual(body["ceiling_remaining_micros"], 1)
        task.refresh_from_db()
        self.assertEqual(task.status, TASK_STATUS_ACTIVE)
        self.assertEqual(self._limit_events().count(), 0)
        self.assertEqual(sweep_over_limit_tasks(self.tenant), 0)


@patch("apps.platform.events.tasks.process_single_event")
class TheAcknowledgementAssessesTheCeilingTest(OneRulePinTestBase):
    """The four-way assessment on the recording acknowledgement (#452, slice
    6 §3, §13) — TD claims 2 and 3, through the route.

    Utilisation is INFORMATION (#150 §9): the two figures beside the status
    are computed over the KNOWN total in every evaluated state, and it is the
    status that tells a reader how to read them. No warning event, no
    threshold, no amber state (§12) — the stop stays binary and these three
    fields say where the unit stands.
    """

    def test_known_below_with_one_unresolved_is_indeterminate_and_not_stopped(self, _mock):
        task = self._task(limit=10_000_000)
        with self.captureOnCommitCallbacks(execute=True):
            self._record(task_id=str(task.id), provider_cost_micros=4_000_000,
                         bills=1_000_000)
            # A report whose supplier cost UBB could not resolve: the Event
            # Type declares a caller-supplied cost and the caller sent none.
            resp = self._record(task_id=str(task.id), bills=1_000_000)
        body = resp.json()
        self.assertEqual(body["costing_status"], COSTING_STATUS_UNRESOLVED)
        self.assertEqual(body["task_total_unresolved_event_count"], 1)
        self.assertFalse(body["stop"])
        self.assertIsNone(body["stop_reason"])
        # UBB tried and could not tell — and says so rather than "within".
        self.assertEqual(body["ceiling_status"], CEILING_STATUS_INDETERMINATE)
        # The percentage is over the KNOWN total, which is why a reader must
        # treat it as a floor: the unresolved cost is not in it.
        self.assertEqual(body["ceiling_used_percentage"], 40)
        self.assertEqual(body["ceiling_remaining_micros"], 6_000_000)
        task.refresh_from_db()
        self.assertEqual(task.status, TASK_STATUS_ACTIVE)

    def test_known_at_the_ceiling_is_reached_and_stopped_whatever_remains_unresolved(self, _mock):
        """Known-over always fires (#150 §4.2): the unresolved cost can only
        add to a total that has already reached the line, so it never buys
        the unit a softer answer or a reprieve."""
        task = self._task(limit=10_000_000)
        with self.captureOnCommitCallbacks(execute=True):
            self._record(task_id=str(task.id), bills=1_000_000)  # unresolved
            resp = self._record(task_id=str(task.id),
                                provider_cost_micros=10_000_000,
                                bills=1_000_000)
        body = resp.json()
        self.assertEqual(body["task_total_unresolved_event_count"], 1)
        self.assertTrue(body["stop"])
        self.assertEqual(body["stop_reason"], reasons.TASK_COGS_CEILING)
        self.assertEqual(body["ceiling_status"], CEILING_STATUS_CEILING_REACHED)
        self.assertEqual(body["ceiling_used_percentage"], 100)
        self.assertEqual(body["ceiling_remaining_micros"], 0)
        task.refresh_from_db()
        self.assertEqual(task.status, TASK_STATUS_KILLED)

    def test_no_pinned_ceiling_is_not_applicable_with_null_utilisation(self, _mock):
        """Nothing was evaluated, so nothing was concluded (#158 §12.4) —
        never `within_ceiling`, never `indeterminate`, however the costs
        stand. Both shapes of cost are driven so the absence of a ceiling is
        shown to answer first, which is what the registry's rule says."""
        task = self._task(limit=None)
        with self.captureOnCommitCallbacks(execute=True):
            costed = self._record(task_id=str(task.id),
                                  provider_cost_micros=10**9, bills=1_000_000)
            uncosted = self._record(task_id=str(task.id), bills=1_000_000)
        for resp in (costed, uncosted):
            body = resp.json()
            self.assertEqual(body["ceiling_status"],
                             CEILING_STATUS_NOT_APPLICABLE)
            self.assertIsNone(body["ceiling_used_percentage"])
            self.assertIsNone(body["ceiling_remaining_micros"])
            self.assertFalse(body["stop"])
        task.refresh_from_db()
        self.assertEqual(task.status, TASK_STATUS_ACTIVE)

    def test_a_unit_of_an_uncapped_kind_is_not_applicable(self, _mock):
        """TD claim 3 (#453): a kind declared `uncapped` pins no ceiling, and
        every surface that asks says `not_applicable` with null utilisation —
        the acknowledgement and the unit read alike — however far the cost
        runs. Never `within_ceiling`, never `indeterminate`, and never a stop."""
        TaskType.objects.create(tenant=self.tenant, key="free",
                                kind=TASK_TYPE_KIND_TASK,
                                uncapped=True)
        started = self._started(task_type="free")
        self.assertIsNone(started["task_cogs_ceiling_micros"])
        with self.captureOnCommitCallbacks(execute=True):
            body = self._record(task_id=started["task_id"],
                                provider_cost_micros=10**9, bills=1_000).json()
        self.assertEqual(body["ceiling_status"], CEILING_STATUS_NOT_APPLICABLE)
        self.assertIsNone(body["ceiling_used_percentage"])
        self.assertIsNone(body["ceiling_remaining_micros"])
        self.assertFalse(body["stop"])
        read = self.http_client.get(
            f"/api/v1/tasks/{started['task_id']}", **self._auth()).json()
        self.assertEqual(read["ceiling_status"], CEILING_STATUS_NOT_APPLICABLE)
        self.assertIsNone(read["ceiling_used_percentage"])
        self.assertIsNone(read["ceiling_remaining_micros"])
        self.assertEqual(read["status"], TASK_STATUS_ACTIVE)

    def test_undeclared_work_on_a_tenant_with_no_default_is_not_applicable(self, _mock):
        """The other cause of `not_applicable` (#453; the two are not told
        apart on the wire, by decision): no declared kind and no tenant
        default at this altitude, so nothing applies and nothing is evaluated."""
        started = self._started()
        self.assertIsNone(started["task_cogs_ceiling_micros"])
        with self.captureOnCommitCallbacks(execute=True):
            body = self._record(task_id=started["task_id"],
                                provider_cost_micros=10**9, bills=1_000).json()
        self.assertEqual(body["ceiling_status"], CEILING_STATUS_NOT_APPLICABLE)
        self.assertIsNone(body["ceiling_used_percentage"])
        self.assertFalse(body["stop"])
        read = self.http_client.get(
            f"/api/v1/tasks/{started['task_id']}", **self._auth()).json()
        self.assertEqual(read["ceiling_status"], CEILING_STATUS_NOT_APPLICABLE)

    def test_undeclared_work_on_a_tenant_with_a_default_is_evaluated_against_it(self, _mock):
        """The tenant's rung is a real ceiling for work with no declared kind
        (#453): the unit pins it, the assessment evaluates against it, and
        landing on it stops the unit."""
        self._tenant_declares_a_default_ceiling(7_000_000)
        started = self._started()
        self.assertEqual(started["task_cogs_ceiling_micros"], 7_000_000)
        with self.captureOnCommitCallbacks(execute=True):
            under = self._record(task_id=started["task_id"],
                                 provider_cost_micros=3_500_000, bills=1_000).json()
            self.assertEqual(under["ceiling_status"], CEILING_STATUS_WITHIN_CEILING)
            self.assertEqual(under["ceiling_used_percentage"], 50)
            on = self._record(task_id=started["task_id"],
                              provider_cost_micros=3_500_000, bills=1_000).json()
        self.assertEqual(on["ceiling_status"], CEILING_STATUS_CEILING_REACHED)
        self.assertTrue(on["stop"])
        task = Task.objects.get(id=started["task_id"])
        self.assertEqual(task.status, TASK_STATUS_KILLED)

    def test_a_declared_kind_is_never_assessed_against_the_tenant_default(self, _mock):
        """A tenant default LOWER than the kind's own figure, and lower than
        the spend of an uncapped kind: neither unit is stopped by it, because
        a declared kind answers for itself (#453, slice 6 §2). The start-time
        half is `CeilingResolutionAtStartTest`; this is the assessment."""
        self._tenant_declares_a_default_ceiling(1_000_000)
        TaskType.objects.create(tenant=self.tenant, key="capped",
                                kind=TASK_TYPE_KIND_TASK,
                                task_cogs_ceiling_micros=5_000_000)
        TaskType.objects.create(tenant=self.tenant, key="free",
                                kind=TASK_TYPE_KIND_TASK,
                                uncapped=True)
        capped = self._started(task_type="capped")
        free = self._started(task_type="free")
        with self.captureOnCommitCallbacks(execute=True):
            on_capped = self._record(task_id=capped["task_id"],
                                     provider_cost_micros=2_000_000,
                                     bills=1_000).json()
            on_free = self._record(task_id=free["task_id"],
                                   provider_cost_micros=2_000_000,
                                   bills=1_000).json()
        self.assertEqual(on_capped["ceiling_status"], CEILING_STATUS_WITHIN_CEILING)
        self.assertEqual(on_capped["ceiling_used_percentage"], 40)
        self.assertFalse(on_capped["stop"])
        self.assertEqual(on_free["ceiling_status"], CEILING_STATUS_NOT_APPLICABLE)
        self.assertFalse(on_free["stop"])

    def test_a_report_naming_no_unit_carries_no_assessment(self, _mock):
        """Null exactly when no unit is named: nothing to assess.
        `not_applicable` would be the wrong word — that is a unit with no
        ceiling, and here there is no unit at all."""
        with self.captureOnCommitCallbacks(execute=True):
            body = self._record(provider_cost_micros=1_000, bills=1_000).json()
        self.assertIsNone(body["task_id"])
        self.assertIsNone(body["task_total_provider_cost_micros"])
        self.assertIsNone(body["ceiling_status"])
        self.assertIsNone(body["ceiling_used_percentage"])
        self.assertIsNone(body["ceiling_remaining_micros"])

    def test_a_replayed_acknowledgement_carries_the_units_standing_now(self, _mock):
        """An idempotent replay answers with the unit's CURRENT assessment,
        on `stop`'s own footing (the durable flag is read at replay time),
        while the unit totals stay null because they say what this recording
        did and a replay did nothing. Driven past the original: a later
        report moves the unit onto its ceiling, and the replay of the FIRST
        report says so rather than repeating what the first one saw."""
        task = self._task(limit=10_000_000)
        with self.captureOnCommitCallbacks(execute=True):
            first = self._record(task_id=str(task.id), idempotency_key="k-1",
                                 provider_cost_micros=4_000_000, bills=1_000)
            self.assertEqual(first.json()["ceiling_status"],
                             CEILING_STATUS_WITHIN_CEILING)
            self._record(task_id=str(task.id), provider_cost_micros=6_000_000,
                         bills=1_000)
            replay = self._record(task_id=str(task.id), idempotency_key="k-1",
                                  provider_cost_micros=4_000_000,
                                  bills=1_000).json()
        self.assertEqual(replay["event_id"], first.json()["event_id"])
        self.assertIsNone(replay["task_total_provider_cost_micros"])
        self.assertEqual(replay["ceiling_status"], CEILING_STATUS_CEILING_REACHED)
        self.assertEqual(replay["ceiling_used_percentage"], 100)
        self.assertEqual(replay["ceiling_remaining_micros"], 0)

    def test_the_stops_shape_on_the_acknowledgement_is_unchanged(self, _mock):
        """`stop`, `stop_reason` and `stop_scope` keep their names, types and
        positions (#180 §11 makes them the shell target's exit-20 contract).
        Asserted rather than assumed: the body's key ORDER is what a
        streaming reader sees first, so the three sit exactly where they did
        and the assessment arrives after them."""
        task = self._task(limit=10_000_000)
        with self.captureOnCommitCallbacks(execute=True):
            body = self._record(task_id=str(task.id),
                                provider_cost_micros=10_000_000,
                                bills=1_000).json()
        keys = list(body)
        at = keys.index("stop")
        self.assertEqual(keys[at:at + 3], ["stop", "stop_reason", "stop_scope"])
        self.assertIs(body["stop"], True)
        self.assertIsInstance(body["stop_reason"], str)
        self.assertIsInstance(body["stop_scope"], str)
        self.assertGreater(keys.index("ceiling_status"), at + 2)
        self.assertEqual(
            keys[keys.index("ceiling_status"):][:3],
            ["ceiling_status", "ceiling_used_percentage",
             "ceiling_remaining_micros"])

    def test_the_unit_read_carries_the_same_assessment(self, _mock):
        """The unit read publishes what the row derives, so a reader who
        missed the acknowledgement gets the same three answers."""
        task = self._task(limit=10_000_000)
        with self.captureOnCommitCallbacks(execute=True):
            self._record(task_id=str(task.id), provider_cost_micros=2_500_000,
                         bills=1_000)
            self._record(task_id=str(task.id), bills=1_000)  # unresolved
        body = self.http_client.get(
            f"/api/v1/tasks/{task.id}", **self._auth()).json()
        self.assertEqual(body["ceiling_status"], CEILING_STATUS_INDETERMINATE)
        self.assertEqual(body["ceiling_used_percentage"], 25)
        self.assertEqual(body["ceiling_remaining_micros"], 7_500_000)
        uncapped = self._task(limit=None)
        body = self.http_client.get(
            f"/api/v1/tasks/{uncapped.id}", **self._auth()).json()
        self.assertEqual(body["ceiling_status"], CEILING_STATUS_NOT_APPLICABLE)
        self.assertIsNone(body["ceiling_used_percentage"])
        self.assertIsNone(body["ceiling_remaining_micros"])


@patch("apps.platform.events.tasks.process_single_event")
class Pin1NothingDeferredTest(OneRulePinTestBase):
    """Preserves: the Task COGS ceiling bites, and the tipping event lands and
    bills with its exact provider cost counted into the task's total.

    This pin used to prove that on the deferred lane, where the ceiling was
    rolled up on a later sweep and accept deliberately rejected nothing, so
    the ceiling bit only after the caller had been told the event was taken.
    The surviving path prices exactly and rolls the total up inline, so the
    same guarantee now holds with **nothing deferred** — which is what this
    case asserts, and the claim #149 §6.5 rests on."""

    def test_task_limit_bites_at_record_time_with_nothing_deferred(self, _mock):
        task = self._task(limit=10_000_000)
        # The kill executes on the recording transaction's on_commit (#112).
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._record(task_id=str(task.id),
                                provider_cost_micros=12_000_000,
                                bills=12_000_000)
        self.assertEqual(resp.status_code, 200)

        # Everything the deferred lane made the caller wait for is already
        # true by the time this response is readable: the exact provider cost
        # is recorded and counted, the task is killed, the event has fired.
        event = Posting.objects.get(id=resp.json()["event_id"])
        self.assertEqual(event.task_id, task.id)
        self.assertEqual(event.provider_cost_micros, 12_000_000)
        task.refresh_from_db()
        self.assertEqual(task.status, TASK_STATUS_KILLED)
        self.assertEqual(task.total_provider_cost_micros, 12_000_000)
        self.assertEqual(self._limit_events().count(), 1)
        self.assertEqual(self._limit_events().get().payload["reason_code"],
                         reasons.TASK_COGS_CEILING)

        # The stop verdict rides the same 200 — no later call is needed to
        # learn that the ceiling bit.
        self.assertTrue(resp.json()["stop"])
        self.assertEqual(resp.json()["stop_reason"], reasons.TASK_COGS_CEILING)


@patch("apps.platform.events.tasks.process_single_event")
class Pin2KilledTaskStillCountsTest(OneRulePinTestBase):
    def test_events_on_killed_task_land_bill_and_count(self, _mock):
        task = self._task(limit=10_000_000)
        # Trip the limit (kills the task; the kill executes on the recording
        # transaction's on_commit — #112) ...
        with self.captureOnCommitCallbacks(execute=True):
            self._record(task_id=str(task.id), provider_cost_micros=11_000_000,
                         bills=11_000_000)
        # ... then a late event arrives on the killed task.
        resp = self._record(task_id=str(task.id), provider_cost_micros=2_000_000,
                            bills=3_000_000)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["stop"])
        self.assertEqual(body["stop_reason"], "task_not_active")
        self.assertEqual(body["stop_scope"], "task")

        # The late event landed, billed, and counted into BOTH totals.
        self.assertEqual(Posting.objects.count(), 2)
        task.refresh_from_db()
        self.assertEqual(task.status, TASK_STATUS_KILLED)
        self.assertEqual(task.total_provider_cost_micros, 13_000_000)
        self.assertEqual(task.total_billed_cost_micros, 14_000_000)
        self.assertEqual(body["task_total_provider_cost_micros"], 13_000_000)
        self.assertEqual(body["task_total_billed_cost_micros"], 14_000_000)
        # No re-announcement for late events: still exactly one kill event.
        self.assertEqual(self._limit_events().count(), 1)


@patch("apps.platform.events.tasks.process_single_event")
class Pin3WalletNoFloorCheckTest(OneRulePinTestBase):
    def test_wallet_carries_no_floor_check(self, _mock):
        # ADR-002: DB constraints enforce accounting facts, never spend
        # policy — the wallet must accept a negative balance.
        for constraint in Wallet._meta.constraints:
            self.assertNotIn("balance", constraint.name.lower())
        self.wallet.balance_micros = -42_000_000
        self.wallet.save(update_fields=["balance_micros"])
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, -42_000_000)


@patch("apps.platform.events.tasks.process_single_event")
class Pin7TwoHundredAlwaysTest(OneRulePinTestBase):
    def test_no_usage_report_path_answers_429_or_409(self, _mock):
        task = self._task(limit=1_000_000)
        # Tipping event, then two more on the killed task — singles. Each
        # record's kill executes at its commit (#112), so the kill lands
        # between iterations exactly as it does between real requests.
        for i in range(3):
            with self.captureOnCommitCallbacks(execute=True):
                resp = self._record(task_id=str(task.id),
                                    provider_cost_micros=2_000_000,
                                    bills=2_000_000)
            self.assertEqual(resp.status_code, 200)
            self.assertNotIn("hard_stop", resp.json())

        # Batch parity: every item on the killed task still lands with
        # accepted=True.
        events = [{
            "customer_id": str(self.customer.id),
            "idempotency_key": f"ib{i}",
            "task_id": str(task.id), "provider_cost_micros": 500_000,
            "event_type": DECLARED,
        } for i in range(2)]
        resp = self.http_client.post(
            "/api/v1/metering/usage/batch",
            data=json.dumps({"events": events}),
            content_type="application/json", **self._auth())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["accepted"], 2)
        for item in body["results"]:
            self.assertTrue(item["accepted"])
            self.assertEqual(item["stop_reason"], "task_not_active")

        # Every report recorded: 3 singles + 2 batch items.
        self.assertEqual(Posting.objects.count(), 5)
        task.refresh_from_db()
        self.assertEqual(task.event_count, 5)


@patch("apps.platform.events.tasks.process_single_event")
class Pin14DenominationTest(OneRulePinTestBase):
    def test_only_the_provider_total_races_the_limit(self, _mock):
        task = self._task(limit=10_000_000)
        # Billed way past the limit, provider under it -> nothing fires.
        resp = self._record(task_id=str(task.id), provider_cost_micros=1_000_000,
                            bills=50_000_000)
        body = resp.json()
        self.assertFalse(body["stop"])
        task.refresh_from_db()
        self.assertEqual(task.status, TASK_STATUS_ACTIVE)
        self.assertEqual(self._limit_events().count(), 0)

        # Both totals on the record and the response, denominationally explicit.
        self.assertEqual(task.total_billed_cost_micros, 50_000_000)
        self.assertEqual(task.total_provider_cost_micros, 1_000_000)
        self.assertEqual(body["task_total_billed_cost_micros"], 50_000_000)
        self.assertEqual(body["task_total_provider_cost_micros"], 1_000_000)

        # The provider total crossing is what kills.
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._record(task_id=str(task.id),
                                provider_cost_micros=9_500_000,
                                # The least this tenant's rule can charge. It
                                # used to be one micro; nothing asserts the
                                # figure, and the point is that the number
                                # beside it is the one that races the limit.
                                bills=1_000)
        self.assertTrue(resp.json()["stop"])
        self.assertEqual(resp.json()["stop_reason"], reasons.TASK_COGS_CEILING)
        task.refresh_from_db()
        self.assertEqual(task.status, TASK_STATUS_KILLED)


class CeilingResolutionAtStartTest(OneRulePinTestBase):
    """What Pin 15 pinned that was never about coverage (#321).

    This tenant declares no cost rates anywhere and every start below is
    admitted, which is the deleted gate's absence asserted rather than merely
    unexercised — under the old rule the first two would have been refused
    `cost_coverage_required` with no task created.
    """

    def test_a_lower_request_wins_over_the_tenant_default(self):
        self._tenant_declares_a_default_ceiling(7_000_000)

        body = self._started(task_cogs_ceiling_micros=5_000_000)
        task = Task.objects.get(id=body["task_id"])
        self.assertEqual(task.task_cogs_ceiling_micros, 5_000_000)
        self.assertEqual(body["task_cogs_ceiling_micros"], 5_000_000)

    def test_a_request_above_the_tenant_default_is_refused(self):
        """Lower only, against whichever rung answers (#453, #150 §8.3): the
        tenant's default for undeclared work is set by the platform team just
        as a declaration is, and agent code may not widen either."""
        self._tenant_declares_a_default_ceiling(7_000_000)

        refused = self._start(task_cogs_ceiling_micros=9_000_000)
        self.assertEqual(refused.status_code, 422, refused.json())
        self.assertIn("exceeds", refused.json()["detail"])
        self.assertIn("undeclared", refused.json()["detail"])
        self.assertEqual(Task.objects.count(), 0)

    def test_the_tenant_default_applies_absent_an_explicit_ceiling(self):
        self._tenant_declares_a_default_ceiling(7_000_000)

        body = self._started()
        self.assertEqual(body["task_cogs_ceiling_micros"], 7_000_000)

    def test_a_declared_kind_ignores_the_tenant_default_entirely(self):
        """A declaration answers for itself (#453, slice 6 §2): a kind with
        its own figure pins that figure, a kind declared uncapped pins no
        ceiling, and the tenant's default — set higher and lower than the
        figure in turn — reaches neither. The rung is for work with no
        declaration to answer."""
        TaskType.objects.create(tenant=self.tenant, key="capped",
                                kind=TASK_TYPE_KIND_TASK,
                                task_cogs_ceiling_micros=5_000_000)
        TaskType.objects.create(tenant=self.tenant, key="free",
                                kind=TASK_TYPE_KIND_TASK,
                                uncapped=True)
        for tenant_default in (7_000_000, 3_000_000):
            with self.subTest(tenant_default=tenant_default):
                self._tenant_declares_a_default_ceiling(tenant_default)
                capped = self._started(task_type="capped")
                self.assertEqual(capped["task_cogs_ceiling_micros"], 5_000_000)
                free = self._started(task_type="free")
                self.assertIsNone(free["task_cogs_ceiling_micros"])

    def test_a_start_with_no_ceiling_anywhere_pins_none(self):
        body = self._started()
        task = Task.objects.get(id=body["task_id"])
        self.assertIsNone(task.task_cogs_ceiling_micros)


@patch("apps.platform.events.tasks.process_single_event")
class Pin16LabelFallbackRemovedTest(OneRulePinTestBase):
    def test_a_task_label_gets_no_attribution_no_limit_no_kill(self, _mock):
        task = self._task(limit=1)  # would trip on any attributed event
        resp = self._record(metadata={"task": str(task.id)},
                            provider_cost_micros=5_000_000,
                            bills=5_000_000)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsNone(body["task_id"])
        self.assertIsNone(body["task_total_provider_cost_micros"])
        self.assertFalse(body["stop"])

        event = Posting.objects.get(id=body["event_id"])
        self.assertIsNone(event.task_id)
        self.assertEqual(event.metadata, {"task": str(task.id)})  # labels only
        task.refresh_from_db()
        self.assertEqual(task.status, TASK_STATUS_ACTIVE)
        self.assertEqual(task.event_count, 0)
        self.assertEqual(self._limit_events().count(), 0)


# --- Pin 17: the clean-cut sweep -------------------------------------------

# Run-era tokens that must not answer on any wire/config/SDK surface. The
# label-cap reason string and the 429 error code are included: they retired
# with the 429 and are deliberately never reused.
_RUN_ERA_TOKENS = (
    "run_id", "run.limit_exceeded", "RunLimitExceeded", "hard_stop_exceeded",
    "run_not_active", "start_run", "close_run", "external_run_id",
    "run_metadata", "run_total_cost_micros", "ubb:runcost", "ubb:taskcost",
    "max_cost_per_task_micros", "run_cost_limit_micros",
    "hard_stop_balance_micros", "cost_limit_exceeded",
    "balance_floor_exceeded", "task_limit_exceeded", "run_stale_seconds",
)

_PLATFORM_ROOT = Path(__file__).resolve().parents[3]

# The public surfaces the clean cut renames wholesale — every file whose
# strings can still answer on the wire.
#
# ingest_accept.py used to be in this list: #113 moved the verdict builders
# behind the metering seam, so its strings reached the wire from there. The
# async accept pipeline is deleted and the module with it; the per-item
# verdict builders that survive moved into metering_endpoints.py, already
# listed above. An inventory that goes on naming a deleted file is exactly
# what this pin exists to prevent, so the list shrinks rather than
# substitutes.
_SURFACE_FILES = [
    _PLATFORM_ROOT / "api" / "v1" / "schemas.py",
    _PLATFORM_ROOT / "api" / "v1" / "metering_endpoints.py",
    _PLATFORM_ROOT / "api" / "v1" / "billing_endpoints.py",
    _PLATFORM_ROOT / "api" / "v1" / "tenant_endpoints.py",
    _PLATFORM_ROOT / "apps" / "platform" / "events" / "schemas.py",
    _PLATFORM_ROOT / "apps" / "platform" / "events" / "catalog.py",
]
_SDK_ROOT = _PLATFORM_ROOT.parent / "ubb-sdk" / "ubb"


class Pin17CleanCutSweepTest(OneRulePinTestBase):
    def test_no_run_era_event_type_in_catalog(self):
        from apps.platform.events import catalog, schemas
        self.assertNotIn("run.limit_exceeded", catalog.WEBHOOK_EVENT_TYPES)
        self.assertIn(TaskKilled.EVENT_TYPE, catalog.WEBHOOK_EVENT_TYPES)
        self.assertFalse(hasattr(schemas, "RunLimitExceeded"))

    def test_retired_config_fields_are_gone(self):
        # INVERTED at its own address by #453: the two tenant-default
        # ceilings left the risk row for the tenant row (#141 §6.2), so the
        # pin that once held them ON the risk row now holds them off it and
        # on the tenant, beside the two deadline rungs they joined.
        risk_fields = {f.name for f in RiskConfig._meta.get_fields()}
        self.assertNotIn("max_cost_per_task_micros", risk_fields)
        self.assertNotIn("default_task_cogs_ceiling_micros", risk_fields)
        self.assertNotIn("default_subtask_cogs_ceiling_micros", risk_fields)

        tenant_fields = {f.name for f in Tenant._meta.get_fields()}
        for gone in ("run_cost_limit_micros", "hard_stop_balance_micros",
                     "run_stale_seconds"):
            self.assertNotIn(gone, tenant_fields)
        self.assertIn("task_stale_seconds", tenant_fields)
        self.assertIn("default_task_cogs_ceiling_micros", tenant_fields)
        self.assertIn("default_subtask_cogs_ceiling_micros", tenant_fields)

        btc_fields = {f.name for f in BillingTenantConfig._meta.get_fields()}
        self.assertNotIn("run_cost_limit_micros", btc_fields)
        self.assertNotIn("hard_stop_balance_micros", btc_fields)
        # The per-task floor snapshot (this pin used to require its presence)
        # was itself deleted — billing-surface-correctness plan, task 1: an
        # independent third floor that never read the customer's real floor.
        self.assertNotIn("default_task_floor_snapshot_micros", btc_fields)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_neither_retired_redis_key_family_is_ever_written(self, _mock):
        # Drive the recording path end to end — there is one, and it is the
        # path that once wrote ubb:runcost:* and ubb:taskcost:* — then scan
        # the whole test Redis DB.
        import redis
        from django.conf import settings

        self.tenant.enforcement_mode = "enforcing"
        self.tenant.save(update_fields=["enforcement_mode"])
        task = self._task(limit=1_000_000)
        self._record(task_id=str(task.id), provider_cost_micros=2_000_000,
                     bills=2_000_000, metadata={"task": "labelled"})
        self._record(task_id=str(task.id), bills=3_000_000)

        client = redis.from_url(settings.REDIS_URL)
        for family in (b"ubb:runcost:*", b"ubb:taskcost:*"):
            self.assertEqual(list(client.scan_iter(match=family)), [],
                             f"retired key family {family} was written")

    def test_no_surface_answers_to_a_run_era_name(self):
        surface_files = list(_SURFACE_FILES)
        self.assertTrue(_SDK_ROOT.is_dir(), "ubb-sdk checkout expected beside ubb-platform")
        surface_files += sorted(_SDK_ROOT.glob("*.py"))
        for path in surface_files:
            text = path.read_text(encoding="utf-8")
            for token in _RUN_ERA_TOKENS:
                self.assertNotIn(
                    token, text,
                    f"run-era token {token!r} survives in {path.name}")

    def test_task_routes_replaced_run_routes(self):
        task = self._task(limit=None)
        resp = self.http_client.post(
            f"/api/v1/tasks/{task.id}/close",
            data=json.dumps({"outcome": TASK_OUTCOME_DELIVERED}),
            content_type="application/json", **self._auth())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], TASK_STATUS_COMPLETED)
        self.assertIn("total_billed_cost_micros", body)
        self.assertIn("total_provider_cost_micros", body)
        resp = self.http_client.post(
            f"/api/v1/metering/runs/{task.id}/close", **self._auth())
        self.assertEqual(resp.status_code, 404)
