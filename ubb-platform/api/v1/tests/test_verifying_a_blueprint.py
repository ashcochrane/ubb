"""Verifying a stored Integration Blueprint, through its route (#580, #567,
#184 §13 steps 4-6 and the Verify operation (a)-(e)).

A generated file is stamped with a `configuration_fingerprint`. Verifying it
loads the snapshot kept under that fingerprint, refuses an Event Type the
snapshot does not publish before anything happens, builds the snapshot's
configuration somewhere that is thrown away afterwards, runs the lifecycle
there with the sample values the request carries — start, a Subtask where one
is asked for, each recording, close — and answers every acknowledgement with a
verdict read off them.

**Everything goes through the tenant's own routes.** Configuration is declared
and published through the registries' and the books' routes, the Blueprint is
resolved through its own, and every assertion is over a response body or over
what the database holds afterwards. A fixture that wrote rows directly would
hide exactly the defect a route-built one exposes — that is how a sandbox
reset failing for an Event Type that names a supplier was found (#593), and
every Event Type here names one.

**"Nothing is left behind" is a count of every table**, read off the
database's own catalogue rather than a list of the tables a reader thought
of: the tenant table and the outbox are in it like any other.
"""
import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from django.db import connection
from django.test import Client
from django.utils import timezone

from apps.platform.code_builder.models import BlueprintSnapshot
from apps.platform.code_builder.tasks import prune_blueprint_snapshots
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox

from ._helpers import (
    EVENT, INPUT_TOKENS, KIND, SEARCHES, SUBTASK_KIND, BlueprintRoutes)

PROVIDER = "openai"

#: A second published Event Type, declared and never selected.
OTHER_EVENT = "image.render"


def verify_path(fingerprint):
    return f"/api/v1/code-builder/blueprints/{fingerprint}/verify"


def every_table():
    """`{table: row count}` for every table the database holds."""
    with connection.cursor() as cursor:
        tables = connection.introspection.table_names(cursor)
        counts = {}
        for table in tables:
            cursor.execute(f'SELECT count(*) FROM "{table}"')
            counts[table] = cursor.fetchone()[0]
    # Not a list somebody chose: if the catalogue read came back short, every
    # "nothing changed" below would be true of nothing.
    assert {"ubb_tenant", "ubb_blueprint_snapshot"} <= set(counts), counts
    assert any("outbox" in table for table in counts), sorted(counts)
    return counts


def what_moved(before, after):
    return {table: (before.get(table), after.get(table))
            for table in set(before) | set(after)
            if before.get(table) != after.get(table)}


class VerifyRoutes(BlueprintRoutes):
    """A tenant that bills, so a recording has a customer price as well as a
    supplier cost; and the books, the markup and the Verify call."""

    def setup_method(self):
        self.tenant = Tenant.objects.create(
            name="T", products=["metering", "billing"],
            billing_mode="postpaid")
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()

    def _cost_rules(self, *rules, provider=PROVIDER, grouping_fields=None):
        """Publish `(kind, measurement, rate per unit)` changes into the
        supplier's default cost book, declaring the book on first use."""
        books = self._call("get", "/api/v1/metering/pricing/cost-books")
        held = [book for book in books["data"]
                if book["provider_key"] == provider]
        book = held[0] if held else self._call(
            "post", "/api/v1/metering/pricing/cost-books",
            {"provider_key": provider, "key": provider, "is_default": True})
        publishes = f"/api/v1/metering/pricing/books/{book['id']}/publishes"
        draft = self._call("post", publishes, {"changes": [
            {"kind": kind, "measurement_key": code, "provider": provider,
             "grouping_fields": grouping_fields or {},
             "rate_per_unit_micros": rate, "unit_quantity": 1}
            for kind, code, rate in rules]})
        self._call("post", f"{publishes}/{draft['id']}/publish")

    def _markup(self, micro_percent):
        self._call("put", "/api/v1/metering/pricing/default-markup",
                   {"markup_micro_percent": micro_percent})

    def _priced_configuration(self):
        """The complete configuration, with both quantities costed and a
        markup over cost."""
        self._complete_configuration()
        self._cost_rules(("add", "input_tokens", 3), ("add", "searches", 7))
        self._markup(50_000_000)

    def _fingerprint(self, **selection):
        return self._complete(**selection)["configuration_fingerprint"]

    def _verify(self, fingerprint, *records, key=None, **body):
        return self._send("post", verify_path(fingerprint),
                          {"records": list(records), **body}, key)

    def _verified(self, fingerprint, *records, **body):
        response = self._verify(fingerprint, *records, **body)
        assert response.status_code == 200, response.content
        return response.json()


def a_record(event_type=EVENT, **fields):
    return {"event_type": event_type, **fields}


THE_SAMPLE = {"input_tokens": 100, "searches": 2}


@pytest.mark.django_db
class TestTheFingerprintIsLoadedFirst(VerifyRoutes):

    def test_a_fingerprint_nobody_resolved_is_not_found_and_creates_nothing(self):
        before = every_table()
        response = self._verify("sha256:" + "0" * 64, a_record())
        assert response.status_code == 404, response.content
        assert response.json()["code"] == "not_found"
        assert what_moved(before, every_table()) == {}

    def test_a_value_that_could_never_be_a_fingerprint_is_not_found(self):
        response = self._verify("not-a-fingerprint", a_record())
        assert response.status_code == 404, response.content

    def test_another_tenants_fingerprint_is_not_found(self):
        self._priced_configuration()
        fingerprint = self._fingerprint()
        other = Tenant.objects.create(name="Other",
                                      products=["metering", "billing"])
        _, other_key = TenantApiKey.create_key(other)
        response = self._verify(fingerprint, a_record(), key=other_key)
        assert response.status_code == 404, response.content


@pytest.mark.django_db
class TestAnEventTypeTheSnapshotDoesNotPublishIsRefused(VerifyRoutes):
    """#567: refused at the Verify boundary, against the SNAPSHOT's published
    content, before anything is recorded or any unit of work started."""

    def _refused(self, fingerprint, claimed):
        before = every_table()
        response = self._verify(fingerprint, a_record(claimed))
        assert response.status_code == 422, response.content
        body = response.json()
        assert body["code"] == "event_type_not_available", body
        assert body["event_types"] == [claimed], body
        assert what_moved(before, every_table()) == {}
        return body

    def test_an_undeclared_event_type(self):
        self._priced_configuration()
        fingerprint = self._fingerprint(event_types=[EVENT, "never.declared"])
        self._refused(fingerprint, "never.declared")

    def test_a_draft_only_event_type(self):
        self._priced_configuration()
        self._event_type(OTHER_EVENT, provider=None, publish=False)
        fingerprint = self._fingerprint(event_types=[EVENT, OTHER_EVENT])
        self._refused(fingerprint, OTHER_EVENT)

    def test_an_event_type_published_live_and_absent_from_the_snapshot(self):
        self._priced_configuration()
        self._event_type(OTHER_EVENT, provider=None)
        fingerprint = self._fingerprint()
        self._refused(fingerprint, OTHER_EVENT)

    def test_a_draft_published_after_resolving_is_still_refused(self):
        """The check reads the snapshot, never the live catalogue."""
        self._priced_configuration()
        self._event_type(OTHER_EVENT, provider=None, publish=False)
        fingerprint = self._fingerprint(event_types=[EVENT, OTHER_EVENT])
        self._publish(OTHER_EVENT)
        self._refused(fingerprint, OTHER_EVENT)

    def test_every_unavailable_claim_is_named_once_in_the_order_claimed(self):
        self._priced_configuration()
        fingerprint = self._fingerprint()
        response = self._verify(fingerprint, a_record("b.event"),
                                a_record(EVENT), a_record("a.event"),
                                a_record("b.event"))
        assert response.status_code == 422, response.content
        assert response.json()["event_types"] == ["b.event", "a.event"]


@pytest.mark.django_db
class TestTheRequestIsCheckedBeforeTheRun(VerifyRoutes):

    def test_a_blocked_blueprint_is_refused_and_creates_nothing(self):
        self._priced_configuration()
        self._event_type(OTHER_EVENT, provider=None, publish=False)
        fingerprint = self._fingerprint(event_types=[EVENT, OTHER_EVENT])
        before = every_table()
        response = self._verify(fingerprint, a_record(EVENT,
                                                      measurements=THE_SAMPLE))
        assert response.status_code == 409, response.content
        body = response.json()
        assert body["code"] == "conflict", body
        assert "blocked" in body["detail"], body
        assert what_moved(before, every_table()) == {}

    def test_a_subtask_kind_the_blueprint_did_not_select_is_refused(self):
        self._priced_configuration()
        fingerprint = self._fingerprint()
        before = every_table()
        response = self._verify(fingerprint, a_record(
            measurements=THE_SAMPLE, subtask_type=SUBTASK_KIND))
        assert response.status_code == 422, response.content
        body = response.json()
        assert body["code"] == "validation_error", body
        assert SUBTASK_KIND in body["detail"], body
        assert what_moved(before, every_table()) == {}

    def test_a_grouping_value_no_selected_kind_requires_is_refused(self):
        """`phase` is required by the Subtask kind, which this Blueprint did
        not select: a value for it would be sent nowhere."""
        self._priced_configuration()
        fingerprint = self._fingerprint()
        before = every_table()
        response = self._verify(fingerprint, a_record(measurements=THE_SAMPLE),
                                grouping_fields={"environment": "prod",
                                                 "phase": "draft"})
        assert response.status_code == 422, response.content
        body = response.json()
        assert body["code"] == "validation_error", body
        assert "'phase'" in body["detail"], body
        assert "'environment'" not in body["detail"], body
        assert what_moved(before, every_table()) == {}


@pytest.mark.django_db
class TestAMatchingSnapshotIsRun(VerifyRoutes):

    def test_it_records_and_answers_the_real_acknowledgement(self):
        self._priced_configuration()
        fingerprint = self._fingerprint()
        body = self._verified(fingerprint, a_record(measurements=THE_SAMPLE))

        assert body["configuration_fingerprint"] == fingerprint
        assert body["verified"] is True, body
        assert body["refusal"] is None
        (record,) = body["records"]
        ack = record["acknowledgement"]
        # 100 tokens at 3 and 2 searches at 7, and half again on top.
        assert ack["provider_cost_micros"] == 314
        assert ack["billed_cost_micros"] == 471
        assert ack["costing_status"] == "known"
        assert ack["pricing_status"] == "known"
        assert ack["unresolved_reason"] is None
        assert ack["uncosted_measurement_keys"] == []
        assert ack["pricing_receipt"], ack
        assert ack["pricing_method"] is not None, ack
        assert ack["measurements"] == THE_SAMPLE
        assert ack["task_id"] == body["task"]["start"]["task_id"]
        assert record["missing_required_measurement_keys"] == []
        assert record["complete"] is True

    def test_the_replay_names_the_same_event_and_its_totals_are_null(self):
        self._priced_configuration()
        body = self._verified(self._fingerprint(),
                              a_record(measurements=THE_SAMPLE))
        (record,) = body["records"]
        assert record["replay"]["event_id"] == \
            record["acknowledgement"]["event_id"]
        assert record["acknowledgement"]["task_total_provider_cost_micros"] \
            == 314
        # Null by design on a replay, and read as expected: the record is
        # still complete.
        assert record["replay"]["task_total_provider_cost_micros"] is None
        assert record["replay"]["task_total_billed_cost_micros"] is None
        assert record["complete"] is True

    def test_the_unit_of_work_is_started_with_the_required_values_and_delivered(self):
        self._priced_configuration()
        body = self._verified(self._fingerprint(),
                              a_record(measurements=THE_SAMPLE))
        task = body["task"]
        assert task["task_type"] == KIND
        assert task["start"]["replayed"] is False
        assert task["close"]["outcome"] == "delivered"
        assert task["close"]["status"] == "completed"
        assert task["close"]["total_provider_cost_micros"] == 314
        environment = body["environment"]
        assert environment["discarded"] is True
        assert list(environment["grouping_fields"]) == ["environment"]
        # What the start was given is what every event under it inherits.
        (record,) = body["records"]
        assert record["acknowledgement"]["grouping_fields"] == \
            environment["grouping_fields"]
        assert environment["customer_external_id"]
        assert environment["rules_effective_at"]
        assert body["subtasks"] == []

    def test_the_requests_grouping_value_is_the_one_the_work_is_started_with(self):
        self._priced_configuration()
        body = self._verified(self._fingerprint(),
                              a_record(measurements=THE_SAMPLE),
                              grouping_fields={"environment": "prod"})
        assert body["environment"]["grouping_fields"] == {
            "environment": "prod"}
        (record,) = body["records"]
        assert record["acknowledgement"]["grouping_fields"] == {
            "environment": "prod"}

    def test_a_rule_pinned_to_a_grouping_value_costs_when_the_request_gives_it(self):
        """A stored rule priced only for `environment=prod`: the sample value
        is what lets it match, and a supplied one would not."""
        self._complete_configuration()
        self._cost_rules(("add", "input_tokens", 3), ("add", "searches", 7),
                         grouping_fields={"environment": "prod"})
        fingerprint = self._fingerprint()

        given = self._verified(fingerprint, a_record(measurements=THE_SAMPLE),
                               grouping_fields={"environment": "prod"})
        assert given["verified"] is True, given
        assert given["records"][0]["acknowledgement"][
            "provider_cost_micros"] == 314

        left_out = self._verified(fingerprint,
                                  a_record(measurements=THE_SAMPLE))
        assert left_out["verified"] is False
        assert left_out["records"][0]["acknowledgement"][
            "unresolved_reason"] == "cost_rate_missing"

    def test_a_subtask_is_started_recorded_under_and_closed(self):
        self._priced_configuration()
        fingerprint = self._fingerprint(subtask_types=[SUBTASK_KIND])
        body = self._verified(fingerprint, a_record(
            measurements=THE_SAMPLE, subtask_type=SUBTASK_KIND),
            a_record(measurements=THE_SAMPLE))
        assert body["verified"] is True, body
        (subtask,) = body["subtasks"]
        assert subtask["task_type"] == SUBTASK_KIND
        parent = body["task"]["start"]["task_id"]
        assert subtask["start"]["parent_task_id"] == parent
        assert subtask["close"]["status"] == "completed"
        under_subtask, under_task = body["records"]
        assert under_subtask["subtask_type"] == SUBTASK_KIND
        assert under_subtask["acknowledgement"]["task_id"] == \
            subtask["start"]["task_id"]
        assert under_subtask["acknowledgement"]["parent_task_id"] == parent
        assert under_task["subtask_type"] is None
        assert under_task["acknowledgement"]["task_id"] == parent
        assert set(body["environment"]["grouping_fields"]) == {
            "environment", "phase"}

    def test_nothing_it_did_is_left_behind_and_the_snapshot_stays(self):
        self._priced_configuration()
        fingerprint = self._fingerprint(subtask_types=[SUBTASK_KIND])
        before = every_table()
        self._verified(fingerprint, a_record(
            measurements=THE_SAMPLE, subtask_type=SUBTASK_KIND))
        assert what_moved(before, every_table()) == {}
        assert BlueprintSnapshot.objects.filter(
            tenant=self.tenant,
            configuration_fingerprint=fingerprint).exists()
        assert self._send("get", f"/api/v1/code-builder/blueprints/"
                                 f"{fingerprint}").status_code == 200

    def test_a_tenant_with_its_own_sandbox_verifies_and_its_sandbox_is_untouched(self):
        """There is one sandbox per tenant and it holds the developer's own
        work, so the run is not one — and a tenant that has one can still
        verify, from either key."""
        self._priced_configuration()
        fingerprint = self._fingerprint()
        sandbox = get_or_create_sandbox(self.tenant)
        _, sandbox_key = TenantApiKey.create_key(sandbox, is_test=True)
        before = every_table()
        assert self._verified(fingerprint, a_record(
            measurements=THE_SAMPLE))["verified"] is True
        assert what_moved(before, every_table()) == {}
        # The sandbox resolves its own Blueprints: its configuration is its
        # own, and so is what it stores.
        assert self._verify(fingerprint, a_record(measurements=THE_SAMPLE),
                            key=sandbox_key).status_code == 404

    def test_nothing_it_did_waits_to_be_delivered(self,
                                                  django_capture_on_commit_callbacks):
        self._priced_configuration()
        fingerprint = self._fingerprint()
        with django_capture_on_commit_callbacks() as held:
            self._verified(fingerprint, a_record(measurements=THE_SAMPLE))
        assert held == []

    def test_an_ordinary_recording_does_wait_to_be_delivered(
            self, django_capture_on_commit_callbacks):
        """The control for the test above: the same recording made through
        the recording route leaves work to do once it commits."""
        self._priced_configuration()
        customer = self._call("post", "/api/v1/platform/customers",
                              {"external_id": "c1"})
        with django_capture_on_commit_callbacks() as held:
            self._call("post", "/api/v1/metering/usage", {
                "customer_id": customer["id"], "idempotency_key": "k1",
                "event_type": EVENT, "provider": PROVIDER,
                "measurements": THE_SAMPLE})
        assert held

    def test_no_response_carries_a_credential(self):
        self._priced_configuration()
        response = self._verify(self._fingerprint(),
                                a_record(measurements=THE_SAMPLE))
        assert response.status_code == 200, response.content
        text = response.content.decode()
        assert self.raw_key not in text
        assert "ubb_live_" not in text and "ubb_test_" not in text
        assert self.tenant.widget_secret not in text

    def test_it_mints_no_key(self, monkeypatch):
        """Watched at the one place a key is made: a key minted inside the
        run would be rolled back with it, so a count afterwards could not
        tell."""
        self._priced_configuration()
        fingerprint = self._fingerprint()
        minted = []
        monkeypatch.setattr(TenantApiKey, "create_key",
                            lambda *a, **k: minted.append(a))
        self._verified(fingerprint, a_record(measurements=THE_SAMPLE))
        assert minted == []

    def test_it_touches_neither_the_live_counter_nor_the_admission_window(
            self, monkeypatch):
        """Both live outside the database, where a rollback cannot reach.
        The run's tenant has spend enforcement off and no admission bound, so
        neither is asked — watched at each one's store."""
        from apps.billing.gating.services import live_counter
        from apps.platform.work import admission
        self._priced_configuration()
        fingerprint = self._fingerprint()
        live = []
        monkeypatch.setattr(live_counter, "_client",
                            lambda: live.append("asked"))
        window = MagicMock()
        monkeypatch.setattr(admission, "cache", window)
        assert self._verified(fingerprint, a_record(
            measurements=THE_SAMPLE))["verified"] is True
        assert live == []
        assert window.mock_calls == []


@pytest.mark.django_db(transaction=True)
class TestOutsideAnyTransactionTheRunIsStillDiscarded(VerifyRoutes):
    """Every other case here runs inside the test's own transaction, so the
    run's rollback is to a savepoint. In production nothing wraps a request,
    and the rollback is the transaction's own: this is that case."""

    def test_nothing_it_did_is_committed(self):
        self._priced_configuration()
        fingerprint = self._fingerprint(subtask_types=[SUBTASK_KIND])
        before = every_table()
        assert self._verified(fingerprint, a_record(
            measurements=THE_SAMPLE,
            subtask_type=SUBTASK_KIND))["verified"] is True
        assert what_moved(before, every_table()) == {}


@pytest.mark.django_db
class TestAGapFailsTheVerdictAndNotTheRequest(VerifyRoutes):

    def test_a_missing_required_measurement_is_named(self):
        self._priced_configuration()
        body = self._verified(self._fingerprint(), a_record(
            measurements={"searches": 2}))
        assert body["verified"] is False
        (record,) = body["records"]
        assert record["missing_required_measurement_keys"] == ["input_tokens"]
        assert record["complete"] is False
        # Read off the acknowledgement: what was recorded is what was sent.
        assert record["acknowledgement"]["measurements"] == {"searches": 2}

    def test_a_missing_cost_rate_is_named(self):
        self._complete_configuration()
        self._cost_rules(("add", "input_tokens", 3))
        self._markup(50_000_000)
        body = self._verified(self._fingerprint(),
                              a_record(measurements=THE_SAMPLE))
        assert body["verified"] is False
        (record,) = body["records"]
        ack = record["acknowledgement"]
        assert ack["costing_status"] == "unresolved"
        assert ack["unresolved_reason"] == "cost_rate_missing"
        assert ack["uncosted_measurement_keys"] == ["searches"]
        assert ack["provider_cost_micros"] is None
        assert record["missing_required_measurement_keys"] == []
        assert record["complete"] is False

    def test_a_refused_recording_stops_the_run_and_withdraws_the_work(self):
        """A supplier cost the Event Type does not admit is refused as a
        recording refuses it; the run stops there and says where."""
        self._priced_configuration()
        body = self._verified(self._fingerprint(), a_record(
            measurements=THE_SAMPLE, provider_cost_micros=5),
            a_record(measurements=THE_SAMPLE))
        assert body["verified"] is False
        refusal = body["refusal"]
        assert refusal["operation_id"] == \
            "api_v1_metering_endpoints_record_usage"
        assert refusal["problem"]["code"] == "validation_error"
        assert refusal["problem"]["status"] == 422
        (record,) = body["records"]
        assert record["acknowledgement"] is None
        assert record["complete"] is False
        assert body["task"]["close"]["outcome"] == "cancelled"

    def test_a_refused_start_stops_the_run_before_anything_is_recorded(self):
        """A kind of work sold at one agreed price, for a tenant that bills:
        the stored configuration carries no agreed price yet, so the start
        is refused exactly as a tenant's own would be."""
        self._grouping_fields(("environment", "task"))
        self._kinds({"key": "whole", "pricing_mode": "fixed",
                     "uncapped": True})
        self._event_type(provider=PROVIDER)
        self._cost_rules(("add", "input_tokens", 3))
        fingerprint = self._fingerprint(task_type="whole")
        body = self._verified(fingerprint, a_record(measurements=THE_SAMPLE))
        assert body["verified"] is False
        assert body["refusal"]["operation_id"] == \
            "api_v1_task_endpoints_start_task"
        assert body["refusal"]["problem"]["code"] == \
            "fixed_task_price_unresolved"
        assert body["task"] == {"task_type": "whole", "start": None,
                                "close": None}
        assert body["records"] == []


@pytest.mark.django_db
class TestItRunsTheSnapshotAndNotLiveConfiguration(VerifyRoutes):

    def test_configuration_edited_and_republished_after_resolving(self):
        self._priced_configuration()
        fingerprint = self._fingerprint()

        # Live configuration moves on: the rule is repriced, the markup is
        # dropped, and the Event Type gains a required quantity and is
        # published again.
        self._cost_rules(("reprice", "input_tokens", 1000))
        self._markup(0)
        self._call("put", f"/api/v1/event-types/{EVENT}/measurements/images",
                   {**SEARCHES, "unit": "image", "required_for_costing": True,
                    "display_name": "Images"})
        self._publish(EVENT)
        assert self._fingerprint() != fingerprint

        body = self._verified(fingerprint, a_record(measurements=THE_SAMPLE))
        (record,) = body["records"]
        assert record["acknowledgement"]["provider_cost_micros"] == 314
        assert record["acknowledgement"]["billed_cost_micros"] == 471
        assert record["missing_required_measurement_keys"] == []
        assert body["verified"] is True, body


@pytest.mark.django_db
class TestASnapshotIsKeptForThirtyDaysAfterItWasLastResolved(VerifyRoutes):

    #: Just past the period, and just inside it: an hour either side of
    #: thirty days, so a period of twenty-nine or thirty-one goes red.
    PAST = timedelta(days=30, hours=1)
    INSIDE = timedelta(days=29, hours=23)

    def _age(self, fingerprint, by):
        BlueprintSnapshot.objects.filter(
            configuration_fingerprint=fingerprint).update(
            updated_at=timezone.now() - by)

    def test_a_pruned_fingerprint_is_not_found_by_the_read_or_by_verify(self):
        self._priced_configuration()
        fingerprint = self._fingerprint()
        self._age(fingerprint, self.PAST)
        assert prune_blueprint_snapshots() == 1
        read = self._send("get", f"/api/v1/code-builder/blueprints/"
                                 f"{fingerprint}")
        assert read.status_code == 404, read.content
        verified = self._verify(fingerprint, a_record(measurements=THE_SAMPLE))
        assert verified.status_code == 404, verified.content

    def test_one_inside_the_period_is_kept(self):
        self._priced_configuration()
        fingerprint = self._fingerprint()
        self._age(fingerprint, self.INSIDE)
        assert prune_blueprint_snapshots() == 0
        assert self._verify(
            fingerprint, a_record(measurements=THE_SAMPLE)).status_code == 200

    def test_resolving_the_same_selection_again_restarts_the_period(self):
        self._priced_configuration()
        fingerprint = self._fingerprint()
        self._age(fingerprint, self.PAST)
        assert self._fingerprint() == fingerprint
        assert prune_blueprint_snapshots() == 0
        assert BlueprintSnapshot.objects.filter(
            configuration_fingerprint=fingerprint).exists()


@pytest.mark.django_db
class TestTheFloor(VerifyRoutes):

    def test_a_read_key_may_not_verify(self):
        self._priced_configuration()
        fingerprint = self._fingerprint()
        response = self._verify(fingerprint, a_record(measurements=THE_SAMPLE),
                                key=self._a_read_key())
        assert response.status_code == 403, response.content


@pytest.mark.django_db
class TestOrdinaryRecordingHasNoVerificationSwitch(VerifyRoutes):
    """#567's ruling: no flag and no environment switch touches the ordinary
    record endpoint. What it does with an Event Type nobody declared is
    pinned where it always was
    (`test_an_undeclared_event_type_holds_nothing_and_costs_as_it_always_did`);
    this pins that nothing here added a way round it."""

    #: Every field the recording request publishes, as it stood before
    #: verification existed.
    RECORDING_FIELDS = {
        "customer_id", "idempotency_key", "metadata", "provider_cost_micros",
        "claimed_provider_cost_micros", "measurements", "currency", "task_id",
        "event_type", "provider", "grouping_fields", "effective_at"}

    def test_the_recording_request_publishes_no_new_field(self):
        contract = json.loads(
            (Path(__file__).resolve().parents[4] / "openapi" / "v1.json")
            .read_text(encoding="utf-8"))
        published = contract["components"]["schemas"]["RecordUsageRequest"]
        assert set(published["properties"]) == self.RECORDING_FIELDS

    def test_a_verification_flag_sent_anyway_changes_nothing(self):
        self._priced_configuration()
        customer = self._call("post", "/api/v1/platform/customers",
                              {"external_id": "c1"})
        bodies = []
        for position, extra in enumerate(({}, {"verify": True,
                                               "verification": True,
                                               "environment": "ephemeral"})):
            bodies.append(self._call("post", "/api/v1/metering/usage", {
                "customer_id": customer["id"],
                "idempotency_key": f"k{position}",
                "event_type": "never.declared", "provider": PROVIDER,
                "measurements": THE_SAMPLE, **extra}))
        plain, flagged = bodies
        for body in bodies:
            assert body["costing_status"] == "known"
        assert plain["provider_cost_micros"] == flagged["provider_cost_micros"]
        assert plain["billed_cost_micros"] == flagged["billed_cost_micros"]
