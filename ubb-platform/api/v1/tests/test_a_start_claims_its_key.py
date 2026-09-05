"""Registering a unit of work in one call, and a retry that returns the same
one (#410, slice 5 §3/§4/§16/§17).

`POST /api/v1/tasks` is NEW. There has never been a `POST` on the task surface:
registering work was a side effect of a flag on a billing-gated affordability
call, so a metering-only tenant could not begin any at all. Four claims here,
and they are independent of each other:

* **THE ROUTE IS AT THE ROOT AND UNGATED**, and one call shape registers work
  at either altitude — naming a parent registers contained work through the
  same route.
* **THE KEY IS REQUIRED AND ITS CLAIM IS PERMANENT.** A repeat carrying the
  same declaration answers with the unit of work already registered and
  creates nothing; a repeat carrying a DIFFERENT declaration is refused and
  names the request field that differs.
* **THE MONEY-SHAPED HALF IS CONDITIONED ON A WALLET**, inside the call, never
  on a product flag at the door — and a tenant with no wallet is not refused
  it, it simply does not apply.
* **TODAY'S CREATION PATH IS GONE, NOT REDIRECTED.** The affordability call
  registers nothing, and the flag that drove it is not there to be sent.

⚠ THE WIRE KEY FOR THE GROUPING BAG IS NEVER SPELLED HERE. It is retired
vocabulary under a spread ceiling another slice owns, at sixteen files, and a
seventeenth fails the sweep — so this module says what it means through
`declared_grouping_values`, whose own docstring records the technique, and the
one assertion about that field's NAME reads the name back out of the same
helper rather than restating it.
"""
import json
import uuid

import pytest
from django.test import Client
from django.utils import timezone

from api.v1.tests.test_metering_endpoints import declared_grouping_values
from apps.billing.gating.models import RiskConfig
from apps.billing.gating.services.risk_service import CONCURRENCY_LIMIT
from apps.billing.wallets.models import CustomerBillingProfile, Wallet
from apps.platform.customers.models import Customer
from apps.platform.grouping_fields.models import GroupingFieldValue
from apps.platform.grouping_fields.services import DimensionService
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work.models import Task, TaskType
from core.vocabulary import TASK_STATUS_ACTIVE, TASK_TYPE_KIND_TASK

#: The two kinds of work this module declares, so a start may name one and a
#: repeat may name the other.
A_KIND_OF_WORK = "render"
ANOTHER_KIND_OF_WORK = "transcode"

#: A declared grouping key at the altitude a whole unit of work sits at.
A_GROUPING_KEY = "region"


class StartTestBase:
    """One tenant, one customer, and the call under test.

    `PRODUCTS` is varied by the subclasses below to prove the route does not
    depend on it. It is never empty because `Tenant.clean` refuses a tenant
    that declares no product at all.
    """

    PRODUCTS = ["metering"]
    BILLING_MODE = None

    def setup_method(self):
        options = {"billing_mode": self.BILLING_MODE} if self.BILLING_MODE else {}
        self.tenant = Tenant.objects.create(
            name="T", products=self.PRODUCTS, **options)
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1")
        self.client = Client()
        for key in (A_KIND_OF_WORK, ANOTHER_KIND_OF_WORK):
            TaskType.objects.create(tenant=self.tenant, key=key,
                                    kind=TASK_TYPE_KIND_TASK)
        DimensionService.declare(self.tenant, key=A_GROUPING_KEY,
                                 slot="grouping_field_1", scope="task")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _a_tenant_that_bills(self):
        """Switch this tenant's posture after the fixture is up.

        Two classes need it: one varies the posture to prove the money-shaped
        half is conditioned on it, and one needs a tenant that bills in order
        to have a wallet regime at all.
        """
        self.tenant.products = ["metering", "billing"]
        self.tenant.billing_mode = "prepaid"
        self.tenant.save(update_fields=["products", "billing_mode"])

    def _start(self, **body):
        """The start call, with the caller's key defaulted to a fresh one.

        A test that is about the claim passes its own key; every other test
        gets one it never has to think about, which is what keeps the claim
        out of the tests that are not about it.
        """
        body.setdefault("customer_id", str(self.customer.id))
        body.setdefault("idempotency_key", f"attempt-{uuid.uuid4()}")
        return self.client.post(
            "/api/v1/tasks", data=json.dumps(body),
            content_type="application/json", **self._auth())


@pytest.mark.django_db
class TestAStartRegistersAUnitOfWork(StartTestBase):
    """The route exists, at the root, and answers with the thing it made."""

    def test_a_metering_only_tenant_registers_a_unit_of_work(self):
        response = self._start(task_type=A_KIND_OF_WORK)
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == TASK_STATUS_ACTIVE
        assert body["task_type"] == A_KIND_OF_WORK
        assert body["replayed"] is False
        assert Task.objects.get(id=body["task_id"]).tenant_id == self.tenant.id

    def test_a_tenant_that_does_not_meter_registers_a_unit_of_work(self):
        """The start is ungated like the four reads and the close (#426).

        `test_task_lifecycle_endpoints.py` drives those four for a tenant
        that does not meter; nothing drove the START for one until ADR-0011
        claimed all five are ungated and its proof table had no row for it.

        ⚠ THE TENANT HAS TO BE MADE THROUGH `QuerySet.update()`, because
        `Tenant.clean` refuses to store products without metering — the same
        shape `test_task_type_registry.py` uses to prove a gate that cannot
        currently refuse anybody. A billing-only tenant reaches the
        money-shaped half, so this customer has a wallet regime and no wallet
        row, which `test_a_billing_customer_with_no_wallet_row_is_admitted_at_zero`
        below already shows is admitted.
        """
        Tenant.objects.filter(id=self.tenant.id).update(
            products=["billing"], billing_mode="prepaid")

        response = self._start(task_type=A_KIND_OF_WORK)

        assert response.status_code == 200
        assert response.json()["status"] == TASK_STATUS_ACTIVE
        assert Task.objects.filter(tenant=self.tenant).count() == 1

    def test_the_key_is_written_down_where_the_claim_can_be_read(self):
        key = "nightly-batch-1"
        self._start(idempotency_key=key)
        assert Task.objects.get(tenant=self.tenant).idempotency_key == key

    def test_naming_a_parent_registers_contained_work_through_the_same_call(self):
        """ONE start shape, not two. A contained start is a start."""
        parent_id = self._start(task_type=A_KIND_OF_WORK).json()["task_id"]
        response = self._start(parent_task_id=parent_id)
        assert response.status_code == 200
        assert response.json()["parent_task_id"] == parent_id
        assert Task.objects.get(id=response.json()["task_id"]).parent_id == uuid.UUID(parent_id)

    def test_contained_work_claims_a_key_like_anything_else(self):
        """A contained start is a start, so it claims its own key and a
        repeat of it replays exactly as a top-level repeat does."""
        parent_id = self._start().json()["task_id"]
        first = self._start(idempotency_key="contained-1", parent_task_id=parent_id)
        again = self._start(idempotency_key="contained-1", parent_task_id=parent_id)
        assert again.status_code == 200
        assert again.json()["replayed"] is True
        assert again.json()["task_id"] == first.json()["task_id"]

    def test_a_request_without_a_key_is_refused(self):
        response = self.client.post(
            "/api/v1/tasks",
            data=json.dumps({"customer_id": str(self.customer.id)}),
            content_type="application/json", **self._auth())
        assert response.status_code == 422
        assert Task.objects.count() == 0

    def test_an_empty_key_is_refused(self):
        """"" IS NOT A KEY. Admitting it would give every caller that sends
        nothing one shared claim to collide on."""
        assert self._start(idempotency_key="").status_code == 422
        assert Task.objects.count() == 0

    def test_the_label_is_accepted_and_is_not_the_identity(self):
        """`external_task_id` is the caller's own label for the work — not
        required, not unique, and two attempts may share it."""
        one = self._start(external_task_id="report-2026-08")
        two = self._start(external_task_id="report-2026-08")
        assert one.status_code == two.status_code == 200
        assert one.json()["task_id"] != two.json()["task_id"]
        assert Task.objects.filter(
            external_task_id="report-2026-08").count() == 2

    def test_the_callers_own_metadata_and_label_are_carried_onto_the_unit(self):
        started = self._start(metadata={"workflow": "search"},
                              external_task_id="ext-abc").json()
        unit = Task.objects.get(id=started["task_id"])
        assert unit.metadata == {"workflow": "search"}
        assert unit.external_task_id == "ext-abc"
        assert started["external_task_id"] == "ext-abc"

    def test_a_customer_with_no_wallet_snapshots_a_zero_balance(self):
        """The forensic snapshot is what the wallet looked like at the start,
        and for a tenant with no wallet regime at all that is zero — the same
        figure the money-shaped half would have read had it run."""
        started = self._start().json()
        assert Task.objects.get(
            id=started["task_id"]).balance_snapshot_micros == 0

    def test_a_billing_customer_with_no_wallet_row_is_admitted_at_zero(self):
        """A billing tenant's customer who has never been credited has no
        `Wallet` row, and starts work at a zero snapshot.

        ⚠ THIS CASE IS NOT EVIDENCE ON ITS OWN, AND SAYING SO IS THE POINT.
        Admitted-at-zero looks identical whether the money-shaped half RAN and
        read an absent wallet as zero, or was skipped entirely — measured:
        reading the condition as *does a Wallet row exist* leaves this case
        green. The test below is the one that discriminates, and this one
        carries the claim the service-level guard it replaces used to make.
        """
        self._a_tenant_that_bills()
        assert not Wallet.objects.filter(customer=self.customer).exists()

        started = self._start()

        assert started.status_code == 200
        assert Task.objects.get(
            id=started.json()["task_id"]).balance_snapshot_micros == 0

    def test_a_billing_customer_with_no_wallet_row_is_still_subject_to_its_floor(self):
        """⚠ THE ROW'S ABSENCE IS NOT THE QUESTION, SO IT IS NOT AN ANSWER.

        The money-shaped half is conditioned on the tenant's PRODUCT, and this
        is the case that shows why it cannot be conditioned on whether a
        `Wallet` row exists. Put this customer's floor ABOVE zero — the
        wind-down shape a negative magnitude gives, the line at +2M — and its
        absent wallet's zero balance is past it, so the start is refused.

        Read the condition as *does a row exist* and this customer skips the
        checks and is admitted: a real billing customer starting unlimited work
        with nothing behind it, which is the exact hole the comment at
        `_TENANT_HAS_A_WALLET` describes. This case goes red under that
        reading; the one above does not.
        """
        self._a_tenant_that_bills()
        CustomerBillingProfile.objects.create(
            customer=self.customer, min_balance_micros=-2_000_000)
        assert not Wallet.objects.filter(customer=self.customer).exists()

        refused = self._start()

        assert refused.status_code == 409
        assert refused.json()["reason"] == "insufficient_funds"
        assert Task.objects.count() == 0

    def test_a_foreign_customer_is_404(self):
        other = Tenant.objects.create(name="Other", products=["metering"])
        theirs = Customer.objects.create(tenant=other, external_id="c2")
        assert self._start(customer_id=str(theirs.id)).status_code == 404


@pytest.mark.django_db
class TestABillingTenantRegistersOneToo(StartTestBase):
    """The other half of the posture claim, on a funded customer."""

    PRODUCTS = ["metering", "billing"]
    BILLING_MODE = "prepaid"

    def setup_method(self):
        super().setup_method()
        Wallet.objects.create(customer=self.customer,
                              balance_micros=100_000_000)

    def test_a_billing_tenant_registers_a_unit_of_work(self):
        response = self._start(task_type=A_KIND_OF_WORK)
        assert response.status_code == 200
        assert response.json()["replayed"] is False

    def test_the_wallet_balance_is_snapshotted_onto_the_unit(self):
        """The money-shaped half RAN — which is what makes the metering-only
        case beside it a statement rather than a coincidence."""
        started = self._start().json()
        assert Task.objects.get(
            id=started["task_id"]).balance_snapshot_micros == 100_000_000

    def test_a_start_that_declares_no_ceiling_anywhere_is_uncapped(self):
        """Absent a request, a declared default and a tenant default, the unit
        is uncapped and no stop signal ever fires."""
        started = self._start().json()
        assert started["provider_cost_limit_micros"] is None
        assert Task.objects.get(
            id=started["task_id"]).provider_cost_limit_micros is None

    def test_a_ceiling_is_snapshotted_though_this_tenant_prices_nothing(self):
        """A LIMITED START IS ADMITTED WITH NO COST RULES DECLARED (#321), and
        that is deliberate rather than an oversight.

        A start used to be refused unless the tenant had promised full cost
        coverage, because a COGS ceiling racing a total that silently counted
        uncovered events as zero is a ceiling that never fires. #320 took the
        premise away — an event whose quantities match no cost rule is RECORDED
        with its cost unresolved and the unit counts what it could not add — so
        the ceiling now races a floor rather than a zero, and onboarding is not
        a wall: a tenant part-way through declaring its costs starts limited
        work like anyone else. This tenant has declared no cost rules at all.
        """
        started = self._start(provider_cost_limit_micros=10_000_000).json()
        assert started["provider_cost_limit_micros"] == 10_000_000
        assert Task.objects.get(
            id=started["task_id"]).provider_cost_limit_micros == 10_000_000


@pytest.mark.django_db
class TestTheKeyIsClaimedPermanently(StartTestBase):
    """A repeat carrying the same declaration replays and creates nothing."""

    PRODUCTS = ["metering", "billing"]
    BILLING_MODE = "prepaid"

    def setup_method(self):
        super().setup_method()
        self.wallet = Wallet.objects.create(customer=self.customer,
                                            balance_micros=100_000_000)

    def test_a_repeat_returns_the_original_and_says_so(self):
        first = self._start(idempotency_key="k1", task_type=A_KIND_OF_WORK,
                            provider_cost_limit_micros=5_000_000)
        again = self._start(idempotency_key="k1", task_type=A_KIND_OF_WORK,
                            provider_cost_limit_micros=5_000_000)
        assert again.status_code == 200
        assert again.json()["replayed"] is True
        assert again.json()["task_id"] == first.json()["task_id"]

    def test_a_repeat_creates_no_second_row_no_second_ceiling_no_second_totals(self):
        self._start(idempotency_key="k1", provider_cost_limit_micros=5_000_000)
        unit = Task.objects.get(tenant=self.tenant)
        unit.total_provider_cost_micros = 7
        unit.event_count = 1
        unit.save(update_fields=["total_provider_cost_micros", "event_count"])

        self._start(idempotency_key="k1", provider_cost_limit_micros=5_000_000)

        assert Task.objects.count() == 1
        unit.refresh_from_db()
        assert unit.provider_cost_limit_micros == 5_000_000
        assert unit.total_provider_cost_micros == 7
        assert unit.event_count == 1

    def test_a_repeat_adds_nothing_to_the_wallet_the_first_call_did_not(self):
        """THE MONEY-CRITICAL HALF, AND IT IS INVISIBLE IN THE RESPONSE.

        ⚠ SAY WHAT THIS DOES AND DOES NOT YET PROVE. Under the rules in force
        on this commit a start takes NO prepaid reservation, because the
        agreed price a reservation would be taken against does not exist yet —
        it arrives with the whole-unit pricing regime. So both halves of the
        assertion below are zero, and the claim it makes today is the weaker
        one: *a repeat adds nothing to the wallet that the first call did
        not*. It is written now, at the address the strong claim will live at,
        because the day a start reserves is the day a silent second
        reservation becomes a double charge — and a test added on that day is
        a test nobody wrote on the day it was needed.

        What IS load-bearing today is the ORDER the gate runs in: the claim is
        read before anything money-shaped, so a repeat never reaches the
        wallet at all. Delete that ordering and this case still passes;
        `test_a_repeat_records_no_new_grouping_value` below is the one that
        goes red, because a grouping value is the one thing a start spends
        that this commit can actually spend.
        """
        before = list(self.wallet.transactions.values_list("id", flat=True))
        self._start(idempotency_key="k1")
        self._start(idempotency_key="k1")
        self.wallet.refresh_from_db()
        assert self.wallet.balance_micros == 100_000_000
        assert list(
            self.wallet.transactions.values_list("id", flat=True)) == before

    def test_a_differing_label_is_still_a_replay_and_the_original_stands(self):
        first = self._start(idempotency_key="k1", external_task_id="first-label")
        again = self._start(idempotency_key="k1", external_task_id="second-label")
        assert again.status_code == 200
        assert again.json()["replayed"] is True
        assert again.json()["task_id"] == first.json()["task_id"]
        assert Task.objects.get(
            tenant=self.tenant).external_task_id == "first-label"

    def test_a_differing_metadata_bag_is_still_a_replay(self):
        self._start(idempotency_key="k1", metadata={"attempt": 1})
        again = self._start(idempotency_key="k1", metadata={"attempt": 2})
        assert again.status_code == 200
        assert again.json()["replayed"] is True
        assert Task.objects.get(tenant=self.tenant).metadata == {"attempt": 1}

    def test_a_retry_replays_even_after_the_kind_of_work_is_retired(self):
        """⚠ THE COMPARISON RE-DERIVES NO POLICY, AND THIS IS WHAT THAT BUYS.

        A start naming a retired kind of work is refused `422` — so if the
        replay comparison re-asked that question, retiring a kind of work would
        turn every in-flight retry of work ALREADY RUNNING into a refusal. The
        retry would then have no way to learn what it started, which is the one
        case a permanently-claimed key exists to answer. The same holds for a
        tenant lowering a declared ceiling under a retry.
        """
        first = self._start(idempotency_key="k1", task_type=A_KIND_OF_WORK)
        assert first.status_code == 200
        TaskType.objects.filter(tenant=self.tenant, key=A_KIND_OF_WORK).update(
            retired_at=timezone.now())
        # A NEW start naming it is refused — the premise, so this cannot pass
        # by the retirement having had no effect at all.
        assert self._start(task_type=A_KIND_OF_WORK).status_code == 422

        again = self._start(idempotency_key="k1", task_type=A_KIND_OF_WORK)
        assert again.status_code == 200
        assert again.json()["replayed"] is True
        assert again.json()["task_id"] == first.json()["task_id"]

    def test_a_retry_that_omits_a_ceiling_the_first_call_named_replays(self):
        """THE CEILING IS COMPARED ONLY WHERE THE CALLER NAMES ONE, and that
        asymmetry is a decision rather than an oversight.

        A caller-supplied ceiling is a request for a LOWER one than the kind of
        work carries, so naming it states a ceiling and omitting it states only
        *whatever this kind of work says* — which is not a claim that can
        contradict anything. A literal reading of "any pinned field differs"
        would refuse this retry; that would fail an honest client which does
        not echo optional fields, and it could hand back nothing wrong if it
        replayed, because the ORIGINAL's ceiling stands and the response says
        what it is.
        """
        first = self._start(idempotency_key="k1",
                            provider_cost_limit_micros=5_000_000)
        again = self._start(idempotency_key="k1")

        assert again.status_code == 200
        assert again.json()["replayed"] is True
        assert again.json()["task_id"] == first.json()["task_id"]
        assert again.json()["provider_cost_limit_micros"] == 5_000_000

    def test_the_claim_survives_the_work_ending(self):
        """NO RELEASE ON TERMINAL AND NO EXPIRY WINDOW. Releasing at terminal
        was rejected on exactly this case: the first attempt delivers, its
        response is lost, and a released key starts a second unit of work that
        is charged a second time."""
        first = self._start(idempotency_key="k1")
        unit = Task.objects.get(tenant=self.tenant)
        unit.status = "completed"
        unit.save(update_fields=["status"])

        again = self._start(idempotency_key="k1")
        assert again.json()["replayed"] is True
        assert again.json()["task_id"] == first.json()["task_id"]
        assert Task.objects.count() == 1


@pytest.mark.django_db
class TestARepeatThatContradictsIsRefused(StartTestBase):
    """One test per pinned field, because *names the field* is the part that
    decays silently."""

    def _claimed(self, **body):
        body.setdefault("idempotency_key", "k1")
        return self._start(**body)

    def _repeat(self, **body):
        body.setdefault("idempotency_key", "k1")
        response = self._start(**body)
        assert response.status_code == 409, response.json()
        assert response.json()["code"] == "idempotency_key_conflict"
        return response.json()

    def test_a_differing_parent_names_that_field(self):
        self._claimed()
        other = self._start().json()["task_id"]
        assert self._repeat(parent_task_id=other)["field"] == "parent_task_id"

    def test_a_differing_kind_of_work_names_that_field(self):
        self._claimed(task_type=A_KIND_OF_WORK)
        body = self._repeat(task_type=ANOTHER_KIND_OF_WORK)
        assert body["field"] == "task_type"

    def test_a_differing_ceiling_names_that_field(self):
        self._claimed(provider_cost_limit_micros=5_000_000)
        body = self._repeat(provider_cost_limit_micros=4_000_000)
        assert body["field"] == "provider_cost_limit_micros"

    def test_a_differing_grouping_value_names_that_field(self):
        """⚠ THE EXPECTED NAME IS READ BACK OUT OF THE HELPER THAT OWNS THE
        SPELLING, never restated here — this bag's wire key is another slice's
        retired word under a spread ceiling, and a literal in this module
        would be one more file on it."""
        self._claimed(**declared_grouping_values({A_GROUPING_KEY: "eu"}))
        body = self._repeat(**declared_grouping_values({A_GROUPING_KEY: "us"}))
        [wire_key] = declared_grouping_values({})
        assert body["field"] == wire_key

    def test_a_repeat_that_changes_altitude_names_the_parent_not_the_bag(self):
        """⚠ THE CHEAP FIELDS ARE COMPARED BEFORE THE ONE THAT READS THE
        REGISTRY, AND THIS IS THE CASE THAT SHOWS WHY.

        Grouping values are declared at an altitude: a key declared at task
        scope cannot be set at subtask scope. So a repeat that BOTH names a
        parent the claim does not have AND carries the task-scoped values the
        original carried is asking two wrong things at once — and resolving the
        bag first would answer with the scope refusal, a `422` about grouping
        keys, for a caller whose actual mistake is the parent.

        Comparing the parent first makes the answer the actionable one.
        """
        self._claimed(**declared_grouping_values({A_GROUPING_KEY: "eu"}))
        other = self._start(**declared_grouping_values(
            {A_GROUPING_KEY: "eu"})).json()["task_id"]

        body = self._repeat(parent_task_id=other,
                            **declared_grouping_values({A_GROUPING_KEY: "eu"}))

        assert body["field"] == "parent_task_id"

    def test_the_refusal_points_at_the_work_the_key_already_claimed(self):
        claimed = self._claimed().json()["task_id"]
        other = self._start().json()["task_id"]
        assert self._repeat(parent_task_id=other)["task_id"] == claimed

    def test_the_same_key_under_another_customer_registers_a_second_unit(self):
        """THE CUSTOMER IS PINNED BY THE UNIQUENESS SCOPE, WHICH IS WHY IT
        CANNOT BE A CONFLICT. The claim is `(tenant, customer, key)`, so the
        same key under a second customer finds no claim at all — two of a
        tenant's customers may each run a `nightly-batch`.
        """
        second = Customer.objects.create(tenant=self.tenant, external_id="c2")
        first = self._claimed()
        theirs = self._start(idempotency_key="k1",
                             customer_id=str(second.id))
        assert theirs.status_code == 200
        assert theirs.json()["replayed"] is False
        assert theirs.json()["task_id"] != first.json()["task_id"]

    def test_a_refused_repeat_records_no_new_grouping_value(self):
        """A REFUSED START SPENDS NOTHING, AND THE THING IT COULD SPEND IS A
        KEY'S CARDINALITY.

        Admitting a grouping value is permanent and capped, so a repeat that
        resolved by ADMITTING would burn a slot in that cap for work the very
        next line refuses. Two mechanisms keep it from happening and this
        asserts the outcome of both: the comparison resolves without
        recording, and the whole call runs in one transaction whose refusal
        rolls back anything that did.
        """
        self._claimed(**declared_grouping_values({A_GROUPING_KEY: "eu"}))
        recorded = set(GroupingFieldValue.objects.filter(
            tenant=self.tenant, key=A_GROUPING_KEY).values_list(
                "value", flat=True))

        self._repeat(**declared_grouping_values({A_GROUPING_KEY: "us"}))

        assert set(GroupingFieldValue.objects.filter(
            tenant=self.tenant, key=A_GROUPING_KEY).values_list(
                "value", flat=True)) == recorded


@pytest.mark.django_db
class TestTheMoneyShapedHalfIsConditionedOnAWallet(StartTestBase):
    """Refused at once where there is a wallet to test; not run where there
    is not.

    ⚠ THE TWO CASES SHARE ONE CUSTOMER STATE, which is what makes the second
    one a statement. A customer below its configured floor is refused under a
    tenant that bills and admitted under one that does not — same wallet, same
    floor, same request. Assert only the metering-only half and a check that
    had silently stopped running for EVERYBODY would still be green.
    """

    PRODUCTS = ["metering"]

    def _a_customer_below_its_floor(self):
        """A wallet past the line its own configured floor draws.

        ⚠ THE FLOOR IS A MAGNITUDE AND THE LINE IS ITS NEGATION
        (`apps/billing/gating/crossing.py`), so `min_balance_micros` is how far
        BELOW zero this customer may go, and a positive balance is never past
        anything. Zero here means the line is zero, and the balance is under
        it — which is the shape a real customer reaches by spending.
        """
        CustomerBillingProfile.objects.create(
            customer=self.customer, min_balance_micros=0)
        Wallet.objects.create(customer=self.customer,
                              balance_micros=-1_000_000)

    def test_the_check_does_not_run_for_a_tenant_without_a_wallet(self):
        self._a_customer_below_its_floor()
        assert self._start().status_code == 200

    def test_a_customer_that_cannot_afford_the_work_is_refused_at_once(self):
        self._a_tenant_that_bills()
        self._a_customer_below_its_floor()

        response = self._start()
        assert response.status_code == 409
        assert response.json()["code"] == "task_start_refused"
        assert response.json()["reason"] == "insufficient_funds"
        assert Task.objects.count() == 0

    def test_the_concurrency_cap_refuses_a_start_at_this_route(self):
        """⚠ THE CAP IS THE ONE CONTROL ONLY A START CAN BREACH, AND UNTIL THIS
        CASE EXISTED NOTHING DROVE IT THROUGH THE ROUTE.

        It is asked by its own method rather than by the advisory check, so
        deleting the call from the start gate leaves every service-level test
        of the cap green — the guard would be gone and only work already
        running would prove it had ever been there. This drives the real route
        and asserts the refusal a caller actually receives.
        """
        self._a_tenant_that_bills()
        Wallet.objects.create(customer=self.customer,
                              balance_micros=100_000_000)
        self.tenant.enforcement_mode = "enforcing"
        self.tenant.save(update_fields=["enforcement_mode"])
        RiskConfig.objects.create(tenant=self.tenant, max_concurrent_requests=1)

        assert self._start().status_code == 200

        refused = self._start()
        assert refused.status_code == 409
        assert refused.json()["code"] == "task_start_refused"
        # ⚠ THE SYMBOL, NOT THE STRING. The word is another slice's retired
        # term under a spread ceiling, so a literal here would be a fourth file
        # on it — and naming the producer's own constant is the stronger
        # assertion regardless: a private copy of the string would pass
        # whatever `concurrency_verdict` decided to answer.
        assert refused.json()["reason"] == CONCURRENCY_LIMIT
        assert Task.objects.count() == 1


@pytest.mark.django_db
class TestTodaysCreationPathIsGone(StartTestBase):
    """Retired, not redirected. The clean break is available exactly once."""

    PRODUCTS = ["metering", "billing"]
    BILLING_MODE = "prepaid"

    def setup_method(self):
        super().setup_method()
        Wallet.objects.create(customer=self.customer,
                              balance_micros=100_000_000)

    def _ask_whether_work_may_proceed(self, **extra):
        body = {"customer_id": str(self.customer.id), **extra}
        return self.client.post(
            "/api/v1/billing/pre-check", data=json.dumps(body),
            content_type="application/json", **self._auth())

    def test_the_affordability_call_registers_nothing(self):
        response = self._ask_whether_work_may_proceed()
        assert response.status_code == 200
        assert response.json()["allowed"] is True
        assert Task.objects.count() == 0

    def test_the_flag_that_drove_it_is_gone(self):
        """The retired flag is no longer a field, so sending it declares
        nothing: Django Ninja drops a body key the schema does not name, and
        the call answers the question it was always for."""
        response = self._ask_whether_work_may_proceed(start_task=True)
        assert response.status_code == 200
        assert Task.objects.count() == 0

    def test_the_answer_no_longer_carries_a_registration(self):
        """Four keys left that response with the creation path, and the two
        that mattered were the identifiers of the thing it made."""
        body = self._ask_whether_work_may_proceed().json()
        assert set(body) == {"allowed", "reason", "balance_micros"}
