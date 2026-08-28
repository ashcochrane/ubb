"""The lifecycle at the root, and a close that must say how it ended (#409).

Two claims, and they are independent of each other:

* **THE MOUNT AND THE GATE.** Reading one unit of work, listing them and
  closing one are at the root prefix and are UNGATED — a unit of work is a
  kernel concept neither metering nor billing owns. The old
  metering-prefixed paths are gone rather than aliased, which is what makes
  this the clean break rather than a second name for one thing.
* **THE CLOSE DECLARES AN OUTCOME.** Required, one of three, and the state
  follows from it. A repeated identical close replays; a contradicting one is
  refused and says what the unit really is.

⚠ EVERY ASSERTION HERE NAMES A CONSTANT, NEVER A STRING VALUE, for the reason
the lifecycle-state module beside it gives: a test spelling `"delivered"` would
still pass against a boundary that had stopped importing the registry, which is
the exact debt this ticket pays. The ONE deliberate exception is the
unrecognised-value test, whose whole subject is a string the registry does not
contain — it is spelled as an obvious non-word so it can never collide with a
value some later slice declares.
"""
import json
import uuid

import pytest
from django.test import Client

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work.models import Task
from apps.platform.work.services import (
    OUTCOMES_ACCEPTING_A_REASON, OUTCOMES_REQUIRING_A_REASON,
    STATUS_FOR_OUTCOME, TaskService,
)
from core.vocabulary import (
    OUTCOME_REASON_CUSTOMER_CANCELLED, OUTCOME_REASON_UPSTREAM_PROVIDER_ERROR,
    OUTCOME_REASON_VALUES, TASK_OUTCOME_CANCELLED, TASK_OUTCOME_DELIVERED,
    TASK_OUTCOME_FAILED, TASK_STATUS_CANCELLED, TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED, TASK_STATUS_KILLED,
)

#: A string the registry does not declare and never will. Spelled here once, as
#: an obvious non-word, so the one test whose subject IS an unrecognised value
#: cannot be read as a value set somebody forgot to import.
NOT_A_DECLARED_REASON = "not-a-declared-reason"


class LifecycleEndpointTestBase:
    """One tenant, one customer, and the three calls under test."""

    #: Which products the tenant declares. Overridden below to prove the calls
    #: do not depend on it. It is never empty because `Tenant.clean` refuses a
    #: tenant that declares no product at all — which is exactly why "ungated"
    #: has to be proved by varying it rather than by removing it.
    PRODUCTS = ["metering"]

    def setup_method(self):
        self.tenant = Tenant.objects.create(name="T", products=self.PRODUCTS)
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1")
        self.client = Client()

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _unit(self, **kwargs):
        return Task.objects.create(
            tenant=self.tenant, customer=self.customer,
            balance_snapshot_micros=0, **kwargs)

    def _get(self, path):
        return self.client.get(path, **self._auth())

    def _close(self, unit, **declaration):
        return self.client.post(
            f"/api/v1/tasks/{unit.id}/close", data=json.dumps(declaration),
            content_type="application/json", **self._auth())


@pytest.mark.django_db
class TestTheLifecycleIsAtTheRootAndUngated(LifecycleEndpointTestBase):
    """The mount, and the absence of a product gate on all three calls."""

    def test_all_three_reach_a_metering_only_tenant(self):
        unit = self._unit()
        assert self._get("/api/v1/tasks").status_code == 200
        assert self._get(f"/api/v1/tasks/{unit.id}").status_code == 200
        assert self._close(unit, outcome=TASK_OUTCOME_DELIVERED).status_code == 200

    def test_the_metering_prefixed_paths_are_gone(self):
        """Gone, not aliased. Map constraint 1 buys exactly one clean break,
        and two live spellings of one call would spend it on nothing."""
        unit = self._unit()
        assert self._get("/api/v1/metering/tasks").status_code == 404
        assert self._get(f"/api/v1/metering/tasks/{unit.id}").status_code == 404
        assert self.client.post(
            f"/api/v1/metering/tasks/{unit.id}/close",
            data=json.dumps({"outcome": TASK_OUTCOME_DELIVERED}),
            content_type="application/json", **self._auth()).status_code == 404

    def test_the_job_analytics_report_deliberately_stayed(self):
        """It belongs to the analytics collapse, not to this move — and moving
        it on the way past would break one path twice."""
        assert self._get("/api/v1/metering/analytics/tasks").status_code == 200


@pytest.mark.django_db
class TestABillingTenantReachesAllThreeToo(LifecycleEndpointTestBase):
    """The other half of the claim: a tenant that bills reaches all three."""

    PRODUCTS = ["metering", "billing"]

    def test_all_three_reach_a_billing_tenant(self):
        unit = self._unit()
        assert self._get("/api/v1/tasks").status_code == 200
        assert self._get(f"/api/v1/tasks/{unit.id}").status_code == 200
        assert self._close(unit, outcome=TASK_OUTCOME_DELIVERED).status_code == 200


@pytest.mark.django_db
class TestNoProductGatesTheLifecycle(LifecycleEndpointTestBase):
    """Ungated, proved against the tenant a gate would actually refuse.

    ⚠ THAT TENANT CANNOT BE CREATED, AND FORCING IT IS THE POINT. `Tenant.clean`
    refuses to save a tenant whose products omit metering, which is why the
    neighbouring gated surfaces state that their 403 branch is unreachable and
    assert the constraint instead. **This module's claim is the opposite one** —
    that these three calls carry no product check at all — and a claim about
    what a gate would do cannot be proved by a tenant every gate admits. So the
    column is written through the queryset, which bypasses `save()` and
    therefore `clean()`: the row is one the model declines to author and the
    database holds perfectly well, and it is the only shape under which
    "ungated" says anything.

    The gated report on the SAME row is the control. Without it a green here
    would prove only that the fixture was admitted everywhere.
    """

    def _a_tenant_that_does_not_meter(self):
        Tenant.objects.filter(id=self.tenant.id).update(products=["billing"])
        self.tenant.refresh_from_db()
        return self.tenant

    def test_all_three_reach_a_tenant_that_does_not_meter(self):
        unit = self._unit()
        self._a_tenant_that_does_not_meter()
        assert self._get("/api/v1/tasks").status_code == 200
        assert self._get(f"/api/v1/tasks/{unit.id}").status_code == 200
        assert self._close(unit, outcome=TASK_OUTCOME_DELIVERED).status_code == 200

    def test_the_gated_report_beside_them_refuses_the_same_tenant(self):
        self._a_tenant_that_does_not_meter()
        assert self._get("/api/v1/metering/analytics/tasks").status_code == 403


@pytest.mark.django_db
class TestTheCloseDeclaresAnOutcome(LifecycleEndpointTestBase):
    """One call, one mandatory field, one state per declaration."""

    def test_every_declared_outcome_enters_its_own_state(self):
        for outcome, status in sorted(STATUS_FOR_OUTCOME.items()):
            unit = self._unit()
            reason = (OUTCOME_REASON_UPSTREAM_PROVIDER_ERROR
                      if outcome in OUTCOMES_ACCEPTING_A_REASON else None)
            body = self._close(unit, outcome=outcome,
                               outcome_reason=reason).json()
            assert body["status"] == status, outcome
            assert body["outcome"] == outcome
            unit.refresh_from_db()
            assert unit.status == status

    def test_an_outcome_is_required(self):
        """The forgiving path must never be the money-moving one: a close with
        no declaration is refused rather than defaulted to a delivery."""
        assert self._close(self._unit()).status_code == 422

    def test_an_unrecognised_outcome_is_refused(self):
        assert self._close(self._unit(),
                           outcome=NOT_A_DECLARED_REASON).status_code == 422

    def test_the_response_says_a_charge_was_not_created(self):
        """Honestly false on every path — the Charge does not exist yet, and
        this is the field's true value rather than a placeholder."""
        body = self._close(self._unit(),
                           outcome=TASK_OUTCOME_DELIVERED).json()
        assert body["charge_created"] is False
        assert body["replayed"] is False

    def test_closing_a_parent_withdraws_its_still_running_work(self):
        """Whatever the parent's own outcome was. The tenant declared how the
        whole unit ended and declared nothing about each contained piece."""
        parent = self._unit()
        child = self._unit(parent=parent)
        self._close(parent, outcome=TASK_OUTCOME_FAILED,
                    outcome_reason=OUTCOME_REASON_UPSTREAM_PROVIDER_ERROR)
        parent.refresh_from_db()
        child.refresh_from_db()
        assert parent.status == TASK_STATUS_FAILED
        assert child.status == TASK_STATUS_CANCELLED

    def test_an_unknown_unit_is_a_404(self):
        assert self.client.post(
            f"/api/v1/tasks/{uuid.uuid4()}/close",
            data=json.dumps({"outcome": TASK_OUTCOME_DELIVERED}),
            content_type="application/json", **self._auth()).status_code == 404


@pytest.mark.django_db
class TestTheReasonBesideTheOutcome(LifecycleEndpointTestBase):
    """Required on `failed`, optional on `cancelled`, refused on `delivered`."""

    def test_a_reason_is_required_on_a_declared_failure(self):
        assert TASK_OUTCOME_FAILED in OUTCOMES_REQUIRING_A_REASON
        assert self._close(self._unit(),
                           outcome=TASK_OUTCOME_FAILED).status_code == 422

    def test_a_reason_is_optional_on_a_declared_cancellation(self):
        assert TASK_OUTCOME_CANCELLED not in OUTCOMES_REQUIRING_A_REASON
        assert TASK_OUTCOME_CANCELLED in OUTCOMES_ACCEPTING_A_REASON
        assert self._close(self._unit(),
                           outcome=TASK_OUTCOME_CANCELLED).status_code == 200
        assert self._close(
            self._unit(), outcome=TASK_OUTCOME_CANCELLED,
            outcome_reason=OUTCOME_REASON_CUSTOMER_CANCELLED).status_code == 200

    def test_a_reason_is_refused_on_a_declared_delivery(self):
        """There is no *why it did not deliver* for work that did."""
        assert TASK_OUTCOME_DELIVERED not in OUTCOMES_ACCEPTING_A_REASON
        assert self._close(
            self._unit(), outcome=TASK_OUTCOME_DELIVERED,
            outcome_reason=OUTCOME_REASON_CUSTOMER_CANCELLED).status_code == 422
        assert self._close(
            self._unit(), outcome=TASK_OUTCOME_DELIVERED,
            reason_detail="a sentence").status_code == 422

    def test_an_unrecognised_reason_is_refused(self):
        """The producer/consumer argument that softens UBB's own stop reasons
        does NOT transfer: this value is caller-supplied, so the closed set is
        a rule on what may come in."""
        assert NOT_A_DECLARED_REASON not in OUTCOME_REASON_VALUES
        assert self._close(self._unit(), outcome=TASK_OUTCOME_FAILED,
                           outcome_reason=NOT_A_DECLARED_REASON).status_code == 422

    def test_every_declared_reason_is_accepted(self):
        """The whole set, derived rather than sampled, so a tenth value is
        covered on the day it is declared."""
        for reason in sorted(OUTCOME_REASON_VALUES):
            unit = self._unit()
            resp = self._close(unit, outcome=TASK_OUTCOME_FAILED,
                               outcome_reason=reason)
            assert resp.status_code == 200, reason

    def test_the_declaration_is_recorded_and_read_back(self):
        unit = self._unit()
        self._close(unit, outcome=TASK_OUTCOME_FAILED,
                    outcome_reason=OUTCOME_REASON_UPSTREAM_PROVIDER_ERROR,
                    reason_detail="the provider returned 503")
        unit.refresh_from_db()
        assert unit.outcome_reason == OUTCOME_REASON_UPSTREAM_PROVIDER_ERROR
        assert unit.reason_detail == "the provider returned 503"

        body = self._get(f"/api/v1/tasks/{unit.id}").json()
        assert body["outcome_reason"] == OUTCOME_REASON_UPSTREAM_PROVIDER_ERROR
        assert body["reason_detail"] == "the provider returned 503"

    def test_a_free_text_sentence_is_never_validated(self):
        """It is the cardinality guard that lets the code beside it stay a
        small closed set, and validating it would defeat what it is for."""
        unit = self._unit()
        self._close(unit, outcome=TASK_OUTCOME_CANCELLED,
                    outcome_reason=OUTCOME_REASON_CUSTOMER_CANCELLED,
                    reason_detail=NOT_A_DECLARED_REASON)
        unit.refresh_from_db()
        assert unit.reason_detail == NOT_A_DECLARED_REASON

    def test_a_unit_nobody_explained_reads_back_null(self):
        unit = self._unit()
        self._close(unit, outcome=TASK_OUTCOME_DELIVERED)
        body = self._get(f"/api/v1/tasks/{unit.id}").json()
        assert body["outcome_reason"] is None
        assert body["reason_detail"] is None


@pytest.mark.django_db
class TestReplayAndRefusal(LifecycleEndpointTestBase):
    """A retry is not a second close, and a contradiction is not a success."""

    def test_an_identical_repeat_replays_and_writes_nothing(self):
        unit = self._unit()
        first = self._close(unit, outcome=TASK_OUTCOME_FAILED,
                            outcome_reason=OUTCOME_REASON_UPSTREAM_PROVIDER_ERROR)
        assert first.json()["replayed"] is False
        unit.refresh_from_db()
        written_at, reason = unit.completed_at, unit.outcome_reason

        second = self._close(unit, outcome=TASK_OUTCOME_FAILED,
                             outcome_reason=OUTCOME_REASON_UPSTREAM_PROVIDER_ERROR)
        assert second.status_code == 200
        body = second.json()
        assert body["replayed"] is True
        assert body["status"] == TASK_STATUS_FAILED
        assert body["charge_created"] is False

        # WROTE NOTHING, asserted on the record rather than on the answer: the
        # completion instant is the one field a second flip could not help
        # moving, so an unchanged one is evidence no second flip happened.
        unit.refresh_from_db()
        assert unit.completed_at == written_at
        assert unit.outcome_reason == reason

    def test_a_contradicting_close_is_refused_and_names_the_real_state(self):
        unit = self._unit()
        self._close(unit, outcome=TASK_OUTCOME_DELIVERED)
        resp = self._close(unit, outcome=TASK_OUTCOME_CANCELLED)
        assert resp.status_code == 409
        body = resp.json()
        assert body["task_status"] == TASK_STATUS_COMPLETED
        assert body["charge_created"] is False
        unit.refresh_from_db()
        assert unit.status == TASK_STATUS_COMPLETED

    def test_a_delivery_declared_on_a_unit_ubb_killed_is_refused(self):
        """THE CASE THAT MATTERS. Once a delivery creates a charge, answering
        200 here would be silent revenue loss whose first symptom is a
        month-end number lower than expected — and letting the late delivery
        win would make ignoring the stop signal free, so the ceiling would stop
        being a ceiling."""
        unit = self._unit()
        TaskService.kill_task(unit.id)

        resp = self._close(unit, outcome=TASK_OUTCOME_DELIVERED)
        assert resp.status_code == 409
        body = resp.json()
        assert body["task_status"] == TASK_STATUS_KILLED
        assert body["charge_created"] is False
        unit.refresh_from_db()
        assert unit.status == TASK_STATUS_KILLED

    def test_no_outcome_can_close_a_unit_ubb_stopped(self):
        """`killed` and `expired` are refused by construction: no declaration
        maps onto either, so this holds for a fourth outcome too."""
        for outcome in sorted(STATUS_FOR_OUTCOME):
            unit = self._unit()
            TaskService.kill_task(unit.id)
            reason = (OUTCOME_REASON_UPSTREAM_PROVIDER_ERROR
                      if outcome in OUTCOMES_ACCEPTING_A_REASON else None)
            resp = self._close(unit, outcome=outcome, outcome_reason=reason)
            assert resp.status_code == 409, outcome


@pytest.mark.django_db
class TestTerminalityNeverTouchesTheUsageRail(LifecycleEndpointTestBase):
    """The regression guard, and it is the one thing terminality must not do.

    Cost is entirely independent of chargeability: a terminal state prevents a
    customer charge and never rejects, deletes or zeroes genuine operational
    usage — including usage that arrives after termination.
    """

    def test_a_late_report_on_a_closed_unit_still_lands_and_rolls_up(self):
        unit = self._unit()
        self._close(unit, outcome=TASK_OUTCOME_DELIVERED)

        _, verdicts = TaskService.accumulate_cost(
            unit.id, billed_cost_micros=7_000, provider_cost_micros=3_000)

        # A verdict, not a refusal — and both totals moved.
        assert verdicts["task_not_active"] is True
        unit.refresh_from_db()
        assert unit.status == TASK_STATUS_COMPLETED
        assert unit.total_billed_cost_micros == 7_000
        assert unit.total_provider_cost_micros == 3_000
        assert unit.event_count == 1

        body = self._get(f"/api/v1/tasks/{unit.id}").json()
        assert body["total_provider_cost_micros"] == 3_000
