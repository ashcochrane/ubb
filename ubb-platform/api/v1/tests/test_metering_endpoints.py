import json
from unittest.mock import patch

from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.platform.event_types.tests._helpers import (
    DECLARED, declares_a_caller_supplied_cost, declares_a_quantity)
from apps.platform.grouping_fields.models import GroupingField
from apps.platform.work.services import TaskService
from apps.billing.wallets.models import Wallet
from apps.metering.pricing.models import (
    TenantDefaultMarkup, TenantMarkup)
from apps.metering.pricing.services import markup_cache
from apps.metering.pricing.services.markup_cache import MarkupCache
from apps.metering.pricing.tests._helpers import (
    cost_rate_in_default_book, declares_a_markup)


def usage_payload(customer, correlation, **fields):
    """A recording-call body, without the caller naming the retired key.

    The recording request still requires a second caller-supplied correlation
    value beside `idempotency_key`. That word is RETIRED — slice 5 deletes it,
    once the key that replaces it is finalised (`gates/migration-ledger.yaml`,
    `backend::request_id`) — and its ledger entry caps how many files may still
    contain it. **That cap is a ceiling on SPREAD, not only a count of what is
    left to fix**, so a new test module naming the key puts the count over its
    entry and the sweep fails. This module is already one of the counted ones,
    so the word stays here and a caller elsewhere says what it means.

    Exactly `cost_rate_in_default_book`'s shape, one retired word along
    (`apps/metering/pricing/tests/_helpers.py`). Both callers pass one string
    and never learn which key it lands under, so slice 5 re-spells it here and
    nowhere else.
    """
    return {"customer_id": str(customer.id), "request_id": correlation,
            "idempotency_key": correlation, **fields}


def declared_grouping_values(values):
    """The recording body's declared grouping bag, for a caller that may not
    spell its key.

    `usage_payload`'s problem one key along, and the same answer: the wire name
    of this bag is retired vocabulary under a spread ceiling (slice 7's, at 16
    files), and this module is already one of the counted ones. A caller passes
    the values and never learns which key they land under.
    """
    return {"dimensions": values}


#: EVERY PARAMETER THE RECORDING REQUEST PUBLISHES, and nothing else (#324).
#:
#: Spelled here for `usage_payload`'s reason one word wider: TWO of these keys
#: are retired words under a spread ceiling — the correlation value above and
#: the grouping bag slice 7 owns — and this module is already counted for both.
#: The claim that reads it lives in
#: `test_two_request_fields_each_with_one_meaning.py`, where the two cost
#: fields' story is; only the spelling is here.
#:
#: A WHOLE SET RATHER THAN A KEY AT A TIME. Django Ninja drops a body key no
#: schema publishes instead of refusing it, so a per-key assertion stays green
#: while an undeclared field rides along beside it — which is how a read route
#: in this repository sent two parameters it publishes nowhere and answered
#: `200` on the axis default for years.
#:
#: ⚠ THE CUSTOMER PRICE LEFT THIS SET IN #365, because a price is configured and
#: never sent. It is the one departed key that is REFUSED rather than dropped —
#: by a validator naming it, not by a rule about unknown keys, so everything
#: else outside this set is still discarded exactly as the paragraph above says.
#: `test_a_customer_price_comes_only_from_configuration.py` holds both halves of
#: that asymmetry and the measurement behind it.
THE_WHOLE_RECORDING_REQUEST = frozenset({
    "customer_id", "request_id", "idempotency_key", "metadata",
    "provider_cost_micros", "claimed_provider_cost_micros",
    "measurements", "currency", "task_id", "event_type",
    "provider", "dimensions", "effective_at",
})


class MeteringProductGatingTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant_metering_only = Tenant.objects.create(
            name="Metering Only", products=["metering"]
        )
        self.key_obj_met, self.raw_key_met = TenantApiKey.create_key(
            self.tenant_metering_only, label="test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant_metering_only, external_id="cust_met1"
        )
        wallet = Wallet.objects.create(customer=self.customer)
        wallet.balance_micros = 10_000_000
        wallet.save(update_fields=["balance_micros"])
        # The recording call below states the supplier's own cost, which one
        # Event Type declaration admits and nothing else does (#324).
        declares_a_caller_supplied_cost(self.tenant_metering_only, DECLARED)

    def test_metering_only_tenant_gets_403_on_billing_balance(self):
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/balance",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_met}",
        )
        self.assertEqual(response.status_code, 403)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_tenant_with_metering_can_record_usage(self, mock_process):
        response = self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps(usage_payload(
                self.customer, "met_1", event_type=DECLARED,
                provider_cost_micros=1_500_000,
                metadata={"model": "gpt-4"})),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_met}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body["new_balance_micros"])
        self.assertIn("event_id", body)

    def test_metering_only_tenant_gets_403_on_billing_transactions(self):
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/transactions",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_met}",
        )
        self.assertEqual(response.status_code, 403)

    def test_tenant_with_metering_can_get_usage_history(self):
        response = self.http_client.get(
            f"/api/v1/metering/customers/{self.customer.id}/usage",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_met}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("data", body)
        self.assertIn("has_more", body)


class PricingMarkupsCRUDTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        # Module-level L1 + contextvar are in-process state: reset per test,
        # mirroring apps/metering/pricing/tests/test_markup_cache.py.
        markup_cache._l1.clear()
        markup_cache._ctx_versions.set({})

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def test_get_tenant_markup_no_markup_returns_zeros(self):
        resp = self.http_client.get("/api/v1/metering/pricing/markup", **self._auth())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["markup_percentage_micros"], 0)
        self.assertEqual(body["fixed_uplift_micros"], 0)

    def test_put_tenant_markup_upserts(self):
        # Create
        resp = self.http_client.put(
            "/api/v1/metering/pricing/markup",
            data=json.dumps({"markup_percentage_micros": 20000000, "fixed_uplift_micros": 0}),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["markup_percentage_micros"], 20000000)

        # GET returns set values
        resp = self.http_client.get("/api/v1/metering/pricing/markup", **self._auth())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["markup_percentage_micros"], 20000000)

        # PUT again with different values updates in place — still exactly one row
        resp = self.http_client.put(
            "/api/v1/metering/pricing/markup",
            data=json.dumps({"markup_percentage_micros": 30000000, "fixed_uplift_micros": 500}),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["markup_percentage_micros"], 30000000)
        self.assertEqual(TenantMarkup.objects.filter(tenant=self.tenant, customer__isnull=True).count(), 1)

    def test_put_and_get_customer_markup_override(self):
        resp = self.http_client.put(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/markup",
            data=json.dumps({"markup_percentage_micros": 50000000, "fixed_uplift_micros": 0}),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)

        resp = self.http_client.get(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/markup",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["markup_percentage_micros"], 50000000)

    def test_get_customer_markup_falls_back_to_tenant_default(self):
        # The tenant default is the DECLARED rung (#357), not this record's
        # customer-less row: that row survives and prices nothing.
        declares_a_markup(self.tenant, percentage_micros=15000000)
        resp = self.http_client.get(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/markup",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["markup_percentage_micros"], 15000000)

    def test_customer_markup_zero_shadows_tenant_default(self):
        # Documents WHY delete exists: a 0/0 override is NOT the same as
        # inheriting — it shadows the tenant default and pins the customer at cost.
        declares_a_markup(self.tenant, percentage_micros=15000000)
        self.http_client.put(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/markup",
            data=json.dumps({"markup_percentage_micros": 0, "fixed_uplift_micros": 0}),
            content_type="application/json", **self._auth())
        resp = self.http_client.get(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/markup",
            **self._auth())
        self.assertEqual(resp.json()["markup_percentage_micros"], 0)

    def test_delete_customer_markup_reverts_to_tenant_default(self):
        declares_a_markup(self.tenant, percentage_micros=15000000)
        TenantMarkup.objects.create(
            tenant=self.tenant, customer=self.customer,
            markup_percentage_micros=50000000, fixed_uplift_micros=0)
        resp = self.http_client.delete(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/markup",
            **self._auth())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "deleted")
        # Now resolves to the tenant default (15%), NOT to zero.
        resp = self.http_client.get(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/markup",
            **self._auth())
        self.assertEqual(resp.json()["markup_percentage_micros"], 15000000)

    def test_delete_customer_markup_idempotent_when_no_override(self):
        resp = self.http_client.delete(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/markup",
            **self._auth())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "no_override")

    def test_delete_customer_markup_unknown_customer_404(self):
        resp = self.http_client.delete(
            "/api/v1/metering/pricing/customers/00000000-0000-0000-0000-000000000000/markup",
            **self._auth())
        self.assertEqual(resp.status_code, 404)

    def test_delete_customer_markup_bumps_l1_cache_immediately(self):
        """Regression: deleting a customer override that is LOWER than the
        tenant default must not leave MarkupCache's L1 serving the stale,
        lower markup for the TTL window — that under-estimates cost and
        therefore under-holds (money leak). The endpoint must delete via the
        model layer (TenantMarkup.delete()) so the version bump added in
        8272e5a actually fires; a queryset .filter(...).delete() bypasses it."""
        declares_a_markup(self.tenant, percentage_micros=50_000_000)  # 50%
        TenantMarkup.objects.create(
            tenant=self.tenant, customer=self.customer,
            markup_percentage_micros=10_000_000, fixed_uplift_micros=0)  # customer discount 10%

        # Pre-populate L1 with the override, as the estimation hot path would.
        MarkupCache.begin_request(self.tenant.id)
        cached = MarkupCache.resolve(self.tenant, self.customer)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.markup_micro_percent, 10_000_000)

        resp = self.http_client.delete(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/markup",
            **self._auth())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "deleted")

        # A new request pins whatever version is current in Redis. If delete()
        # bumped it, the stale L1 entry misses on version and resolve() falls
        # through to a live ORM resolve — landing on the tenant default, not
        # the deleted (lower) override.
        MarkupCache.begin_request(self.tenant.id)
        resolved = MarkupCache.resolve(self.tenant, self.customer)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.markup_micro_percent, 50_000_000)


class UsageEventDetailEndpointTest(TestCase):
    """GET /usage/{event_id} returns the full pricing receipt (provenance)."""

    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="Rcpt", products=["metering"])
        _, self.key = TenantApiKey.create_key(self.tenant, label="r")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        # The markup rung is class-wide because most cases here want a price at
        # all; the COST behind it is per-case, because two of them are about
        # what an unresolved cost does and a rate in the setup would settle it
        # under them (#356).
        declares_a_markup(self.tenant, percentage_micros=20_000_000)

    def _a_cost_the_margin_can_be_taken_over(self):
        """WHAT A MARGIN NEEDS BEFORE IT CAN BE ONE (#356).

        A rung declaring the percentage is half of it and this is the other:
        without a cost UBB has resolved, the engine waives the charge rather
        than taking a margin over a number it does not have — so a case about
        the METHOD would become a case about an absence.
        """
        cost_rate_in_default_book(
            self.tenant, measurement_key="input_tokens",
            rate_per_unit_micros=1_000, unit_quantity=1_000)

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.key}"}

    def _event(self, tenant=None, customer=None):
        from apps.metering.usage.models import Posting
        t = tenant or self.tenant
        c = customer or self.customer
        return Posting.objects.create(
            tenant=t, customer=c,
            request_id=f"req-{c.external_id}", idempotency_key=f"idem-{c.external_id}",
            provider_cost_micros=300_000, billed_cost_micros=450_000,
            event_type="chat", provider="openai", currency="usd",
            # The quantity in the RECEIPT survives #272 — it is what a rate card
            # was fed, per named quantity, and slice 4 renames it. Only the
            # posting's own nameless inline total died. The name key here is
            # the one #275 moved: a receipt written by today's engine. Receipts
            # written before it keep the retired spelling and are not rewritten.
            pricing_provenance={
                "engine_version": "2.1.0",
                "metrics": [{"measurement_key": "input_tokens",
                             "price_card_id": "abc",
                             "units": 35_000, "micros": 450_000}]})

    def test_get_event_returns_full_receipt(self):
        ev = self._event()
        resp = self.http.get(f"/api/v1/metering/usage/{ev.id}", **self._auth())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["id"], str(ev.id))
        self.assertEqual(body["billed_cost_micros"], 450_000)
        self.assertEqual(body["pricing_provenance"]["engine_version"], "2.1.0")
        self.assertEqual(
            body["pricing_provenance"]["metrics"][0]["price_card_id"], "abc")

    def test_get_unknown_event_returns_404(self):
        resp = self.http.get(
            "/api/v1/metering/usage/00000000-0000-0000-0000-000000000000",
            **self._auth())
        self.assertEqual(resp.status_code, 404)

    def test_get_event_of_other_tenant_returns_404(self):
        other = Tenant.objects.create(name="Other", products=["metering"])
        other_cust = Customer.objects.create(tenant=other, external_id="oc")
        ev = self._event(tenant=other, customer=other_cust)
        resp = self.http.get(f"/api/v1/metering/usage/{ev.id}", **self._auth())
        self.assertEqual(resp.status_code, 404)

    def test_the_response_says_the_measurements_are_available(self):
        """#271 — the status reaches the wire, on a really measured posting.

        Recorded through the real path rather than assembled, so what the
        response reports is the state the recording path actually leaves
        behind.
        """
        from apps.metering.usage.models import Posting
        from apps.metering.usage.services.usage_service import UsageService

        ev = Posting.objects.get(
            id=UsageService.record_usage(
                self.tenant, self.customer, "r-avail", "i-avail",
                measurements={"input_tokens": 1200})["event_id"])

        body = self.http.get(f"/api/v1/metering/usage/{ev.id}",
                             **self._auth()).json()
        self.assertEqual(body["measurements_status"], "available")
        self.assertEqual(body["measurements"], {"input_tokens": 1200})

    def test_a_pruned_payload_does_not_read_as_an_empty_one(self):
        """**The defect this field exists to end**, stated on the response.

        The quantities come back `{}` — that is the reading the whole ticket is
        about — and the status beside them says the detail was removed rather
        than absent. A consumer defaulting on the empty bag alone would render
        this row as "no usage" to an end customer.
        """
        from apps.metering.usage.models import Posting
        from apps.metering.usage.services.usage_service import UsageService
        from apps.metering.usage.tests._helpers import (
            release_and_prune, settle_the_supplier_cost)

        ev = Posting.objects.get(
            id=UsageService.record_usage(
                self.tenant, self.customer, "r-pruned", "i-pruned",
                measurements={"input_tokens": 1200})["event_id"])
        # Two steps, because the database now holds the child's whole-record
        # rule (#354) and this call has no cost rate behind it, so it records
        # `unresolved`: the rule refuses a `DELETE` while the posting is
        # waiting, and again before the record's horizon. Settling is what a
        # recovery does and releasing is what a retention clock would do.
        settle_the_supplier_cost(ev, 240_000)
        release_and_prune(ev)

        body = self.http.get(f"/api/v1/metering/usage/{ev.id}",
                             **self._auth()).json()
        self.assertEqual(body["measurements"], {})
        self.assertEqual(body["measurements_status"], "pruned")

    def test_the_status_is_present_and_declared_even_on_an_assembled_posting(self):
        """It is required, not optional — there is no posting without an
        answer, and an absent key would default exactly like an empty bag.

        The subject is the bare fixture above, which is assembled rather than
        recorded: even that answers, and answers with a declared value.
        """
        from core.vocabulary import MEASUREMENTS_STATUS_VALUES

        body = self.http.get(f"/api/v1/metering/usage/{self._event().id}",
                             **self._auth()).json()
        self.assertIn("measurements_status", body)
        self.assertIn(body["measurements_status"], MEASUREMENTS_STATUS_VALUES)

    # --- How the price was derived (#355) ------------------------------------
    #
    # ⚠ THESE LIVE ON THE ENDPOINT'S OWN CLASS RATHER THAN IN A MODULE OF THEIR
    # OWN, and the reason is a ceiling rather than a preference: a new module
    # reading the stored record back would spell the retired name of the column
    # that holds it, whose ledger entry is at its extent. This file already
    # carries that word and this class already owns the surface, so the
    # assertions go where the behaviour is.

    def test_a_derived_price_names_the_method_that_derived_it(self):
        """AC: the method reaches the published contract, off a real recording.

        Recorded through the route rather than assembled, so what the response
        publishes is what the engine actually wrote — a fixture holding the
        answer would pass the day the engine stopped writing one.
        """
        from apps.metering.usage.models import Posting
        from apps.metering.usage.services.usage_service import UsageService
        from core.vocabulary import (PRICING_METHOD_MARGIN_OVER_COST,
                                     PRICING_STATUS_KNOWN)

        self._a_cost_the_margin_can_be_taken_over()
        ev = Posting.objects.get(
            id=UsageService.record_usage(
                self.tenant, self.customer, "r-method", "i-method",
                measurements={"input_tokens": 1200})["event_id"])

        body = self.http.get(f"/api/v1/metering/usage/{ev.id}",
                             **self._auth()).json()
        self.assertEqual(body["pricing_method"], PRICING_METHOD_MARGIN_OVER_COST)
        self.assertEqual(body["pricing_status"], PRICING_STATUS_KNOWN)
        # The published field is the RECORD's, not a second derivation that
        # could answer differently the day the rules behind it are edited —
        # which is the whole of what the receipt is for.
        self.assertEqual(body["pricing_method"],
                         body["pricing_provenance"]["pricing"]["method"])

    def test_the_recording_ack_names_the_method_too(self):
        """AC: the method reaches the contract on BOTH responses carrying the
        record, and the ack is the one it would be easiest to leave out.

        The rule is mechanical rather than a judgement: the method is a value
        INSIDE the record this response already returns, which is published
        untyped — so leaving the ack out would have left the same closed concept
        crossing to a caller with no schema saying what it may be, which is the
        defect the marker exists to remove. The value here is compared against
        the record on the same body, so the typed field cannot drift from the
        untyped one it was lifted out of.
        """
        from core.vocabulary import (PRICING_METHOD_MARGIN_OVER_COST,
                                     PRICING_STATUS_KNOWN)

        self._a_cost_the_margin_can_be_taken_over()
        resp = self.http.post(
            "/api/v1/metering/usage",
            data=json.dumps(usage_payload(
                self.customer, "r-ack-method",
                measurements={"input_tokens": 1200})),
            content_type="application/json", **self._auth())

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["pricing_method"], PRICING_METHOD_MARGIN_OVER_COST)
        self.assertEqual(body["pricing_status"], PRICING_STATUS_KNOWN)
        self.assertEqual(body["pricing_method"],
                         body["pricing_provenance"]["pricing"]["method"])

    def test_a_price_that_was_not_derived_answers_null_beside_the_status(self):
        """AC: null means the price was NOT DERIVED, read beside the status.

        Null is not a third method and it is not an error. It says no
        derivation happened, and the field a reader consults for WHY is the
        price status on the same body — here, a posting under a job sold for
        one agreed price, which carries no event-level customer price at all.
        The two are published together precisely so neither has to answer the
        other's question.

        Assembled rather than recorded, and deliberately — but the reason has
        narrowed (#356). The resolver now reaches three of the four price
        statuses through the spine, and two of them null the method: a margin
        over a cost UBB never learned is `waived`, and a subject no rung priced
        is `unknown`. The status this case uses is the fourth, `not_applicable`,
        which nothing produces because it is a fact about the tenant's posture
        and the job's pricing regime rather than about resolution — so this is
        still the shape reachable only at the construction boundary, and it is
        the one that carries a reason beside it.

        The record is still built through `build_receipt` — the one place a
        receipt is made, and the place that refuses one whose method and status
        disagree.
        """
        from apps.metering.pricing.receipts import Resolution, build_receipt
        from apps.metering.pricing.tests._helpers import a_usage_event_subject
        from apps.metering.usage.models import Posting
        from core.vocabulary import (
            COSTING_METHOD_CALCULATED, COSTING_STATUS_KNOWN,
            NOT_APPLICABLE_REASON_FIXED_TASK_PRICING,
            PRICING_STATUS_NOT_APPLICABLE)

        receipt = build_receipt(
            subject=a_usage_event_subject(),
            effective_at="2026-08-19T09:00:00+00:00", currency="usd",
            pricing_engine_version="2.1.0",
            costing=Resolution(method=COSTING_METHOD_CALCULATED,
                               status=COSTING_STATUS_KNOWN,
                               amount_micros=300_000,
                               detail={"components": []}),
            pricing=Resolution(method=None,
                               status=PRICING_STATUS_NOT_APPLICABLE,
                               amount_micros=None,
                               detail={"components": []}))
        ev = Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="idem-not-derived",
            provider_cost_micros=300_000, billed_cost_micros=None,
            pricing_status=PRICING_STATUS_NOT_APPLICABLE,
            not_applicable_reason=NOT_APPLICABLE_REASON_FIXED_TASK_PRICING,
            pricing_provenance=receipt)

        body = self.http.get(f"/api/v1/metering/usage/{ev.id}",
                             **self._auth()).json()
        self.assertIsNone(body["pricing_method"])
        self.assertEqual(body["pricing_status"], PRICING_STATUS_NOT_APPLICABLE)
        self.assertEqual(body["not_applicable_reason"],
                         NOT_APPLICABLE_REASON_FIXED_TASK_PRICING)

    def test_a_receipt_in_the_older_shape_names_no_method_rather_than_one(self):
        """The read-path half, and the direction that actually happens.

        Rows on disk predate the sectioned record, and what the older shape
        wrote beside its price is the SOURCE that supplied it — a different
        question from how the amount was derived, since a markup and a rule
        declaring a margin are one method at two sources. Translating that
        field would put a value on the published contract that no writer ever
        recorded, so the response says nothing, which is what the record says.
        """
        body = self.http.get(f"/api/v1/metering/usage/{self._event().id}",
                             **self._auth()).json()
        self.assertIn("pricing_method", body)
        self.assertIsNone(body["pricing_method"])


class MeteringTaskEndpointTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Task Tenant",
            products=["metering"],
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_task_met"
        )
        declares_a_caller_supplied_cost(self.tenant, DECLARED)
        # The tenant charges what the call cost, said out loud. These cases
        # accumulate BILLED totals, and a tenant with no markup rung declared
        # bills nothing at all now — `unknown`, not the supplier's figure (#356).
        declares_a_markup(self.tenant)

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _task(self, tenant=None, customer=None, balance=20_000_000,
              limit=None):
        # One-rule (#37): the tenant-level run-era knobs are gone — limits are
        # passed explicitly at task creation (as billing pre-check does).
        return TaskService.create_task(
            tenant or self.tenant, customer or self.customer,
            balance_snapshot_micros=balance,
            provider_cost_limit_micros=limit,
            billing_owner_id=(customer or self.customer).id,
        )

    def _record(self, **extra):
        data = {
            "customer_id": str(self.customer.id),
            "request_id": "req_1",
            "idempotency_key": "idem_1",
            "event_type": DECLARED,
            "provider_cost_micros": 1_000_000,
        }
        data.update(extra)
        return self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps(data),
            content_type="application/json",
            **self._auth(),
        )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_with_task_id_success(self, mock_process):
        task = self._task()
        resp = self._record(task_id=str(task.id))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["task_id"], str(task.id))
        self.assertEqual(body["task_total_billed_cost_micros"], 1_000_000)
        self.assertEqual(body["task_total_provider_cost_micros"], 1_000_000)
        self.assertFalse(body["stop"])
        self.assertNotIn("hard_stop", body)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_tipping_event_returns_200_and_kills_task(self, mock_process):
        """One-rule (#37): the 429 hard-stop is retired — the tipping event
        answers 200, LANDS, and the stop verdict rides the body while the
        server kills the task."""
        from apps.metering.usage.models import Posting
        from apps.platform.events.models import OutboxEvent

        task = self._task(limit=10_000_000)
        # First event under limit
        resp = self._record(
            task_id=str(task.id),
            request_id="req_hs1",
            idempotency_key="idem_hs1",
            provider_cost_micros=9_000_000,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["stop"])

        # Second event pushes the PROVIDER total past the 10M ceiling — still
        # 200. The kill executes on the recording transaction's on_commit
        # (#112), which the test transaction never reaches on its own.
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._record(
                task_id=str(task.id),
                request_id="req_hs2",
                idempotency_key="idem_hs2",
                provider_cost_micros=2_000_000,
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["stop"])
        self.assertEqual(body["stop_reason"], "task_limit")
        self.assertEqual(body["stop_scope"], "task")
        self.assertEqual(body["task_total_provider_cost_micros"], 11_000_000)

        # The tipping event landed; the task is killed; the signal fired once.
        self.assertEqual(Posting.objects.filter(tenant=self.tenant).count(), 2)
        task.refresh_from_db()
        self.assertEqual(task.status, "killed")
        self.assertEqual(task.metadata.get("kill_reason"), "task_limit")
        self.assertEqual(task.total_provider_cost_micros, 11_000_000)
        self.assertEqual(OutboxEvent.objects.filter(
            event_type="task.limit_exceeded").count(), 1)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_killed_task_returns_200_task_not_active(self, mock_process):
        """One-rule (#37): the 409 run_not_active is retired — an event for a
        killed task answers 200, lands, bills, and counts; the body carries
        the task_not_active verdict."""
        from apps.metering.usage.models import Posting

        task = self._task()
        TaskService.kill_task(task.id)

        resp = self._record(task_id=str(task.id))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["stop"])
        self.assertEqual(body["stop_reason"], "task_not_active")
        self.assertEqual(body["stop_scope"], "task")

        # Landed and counted into both totals.
        self.assertEqual(Posting.objects.filter(tenant=self.tenant).count(), 1)
        task.refresh_from_db()
        self.assertEqual(task.status, "killed")
        self.assertEqual(task.total_billed_cost_micros, 1_000_000)
        self.assertEqual(task.total_provider_cost_micros, 1_000_000)
        self.assertEqual(task.event_count, 1)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_close_task_success(self, mock_process):
        task = self._task()
        # Record some usage first
        self._record(task_id=str(task.id))

        resp = self.http_client.post(
            f"/api/v1/metering/tasks/{task.id}/close",
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["task_id"], str(task.id))
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["total_billed_cost_micros"], 1_000_000)
        self.assertEqual(body["total_provider_cost_micros"], 1_000_000)
        self.assertEqual(body["event_count"], 1)

    def test_close_task_not_found_returns_404(self):
        import uuid
        resp = self.http_client.post(
            f"/api/v1/metering/tasks/{uuid.uuid4()}/close",
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 404)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_cross_tenant_task_id_is_404_and_not_mutated(self, mock_process):
        other_tenant = Tenant.objects.create(name="Victim", products=["metering"])
        other_customer = Customer.objects.create(tenant=other_tenant, external_id="victim_c")
        victim_task = self._task(tenant=other_tenant, customer=other_customer)
        resp = self._record(task_id=str(victim_task.id), request_id="req_idor1", idempotency_key="idem_idor1")
        self.assertEqual(resp.status_code, 404)
        victim_task.refresh_from_db()
        self.assertEqual(victim_task.total_billed_cost_micros, 0)
        self.assertEqual(victim_task.total_provider_cost_micros, 0)
        self.assertEqual(victim_task.event_count, 0)
        self.assertEqual(victim_task.status, "active")

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_cross_customer_same_tenant_task_id_is_404(self, mock_process):
        cust_b = Customer.objects.create(tenant=self.tenant, external_id="cust_b")
        task_b = self._task(customer=cust_b)
        resp = self._record(task_id=str(task_b.id), request_id="req_idor2", idempotency_key="idem_idor2")
        self.assertEqual(resp.status_code, 404)
        task_b.refresh_from_db()
        self.assertEqual(task_b.total_billed_cost_micros, 0)
        self.assertEqual(task_b.total_provider_cost_micros, 0)
        self.assertEqual(task_b.event_count, 0)
        self.assertEqual(task_b.status, "active")

    # ---- what the recording path publishes about completeness (#328) -------
    #
    # Both live HERE rather than beside the rest of #328 because the recording
    # request still requires the retired correlation key, and this module is one
    # of the files already counted for it. The behaviour is metering's; the
    # readers proved elsewhere are subscriptions', platform's and referrals'.

    def test_the_emitted_payload_carries_the_status_the_posting_recorded(self):
        """The one line four products depend on, and nothing else asserted it.

        `usage.recorded` carries the supplier cost, and a null there means
        EITHER "UBB has not learned it" or "there is none" — two facts a
        subscriber must count differently. The status is what separates them,
        and two products now accumulate off it. Delete the line that fills it
        and every other test in this repository stays green while subscriptions
        and referrals silently under-count, which is exactly the shape this
        assertion exists to catch.
        """
        from apps.platform.events.models import OutboxEvent
        from apps.platform.events.schemas import UsageRecorded
        from core.vocabulary import COSTING_STATUS_UNRESOLVED

        resp = self._record(provider_cost_micros=None)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["costing_status"],
                         COSTING_STATUS_UNRESOLVED)
        payload = OutboxEvent.objects.filter(
            event_type=UsageRecorded.EVENT_TYPE).latest("created_at").payload
        self.assertEqual(payload["costing_status"], COSTING_STATUS_UNRESOLVED)

    def test_the_ack_says_what_the_units_running_total_left_out(self):
        """A caller watching its own spend against a COGS limit (#328).

        The unit total on the ack is a FLOOR wherever the count is non-zero:
        the second event's cost never entered it, so a caller comparing the
        total against its limit is comparing a lower bound. Without the count
        beside it there is nothing on the ack that says so.
        """
        task = self._task()
        first = self._record(task_id=str(task.id))
        self.assertEqual(first.status_code, 200)
        second = self._record(task_id=str(task.id), request_id="req_2",
                              idempotency_key="idem_2",
                              provider_cost_micros=None)
        body = second.json()
        self.assertEqual(body["task_total_provider_cost_micros"], 1_000_000)
        self.assertEqual(body["task_total_unresolved_event_count"], 1)


class MeteringUsageAnalyticsEndpointTest(TestCase):
    def setUp(self):
        from apps.metering.usage.services.usage_service import UsageService

        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Analytics Tenant", products=["metering"],
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c_analytics"
        )
        # Analytics totals a billed figure, so the tenant has to have declared a
        # rung to produce one: no markup rung is `unknown`, not cost (#356).
        declares_a_markup(self.tenant)
        wallet = Wallet.objects.create(customer=self.customer)
        wallet.balance_micros = 100_000_000
        wallet.save()
        for i in range(3):
            UsageService.record_usage(
                tenant=self.tenant,
                customer=self.customer,
                request_id=f"req_analytics_{i}",
                idempotency_key=f"idem_analytics_{i}",
                provider_cost_micros=1_000_000,
            )

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def test_usage_analytics(self):
        response = self.http_client.get(
            "/api/v1/metering/analytics/usage",
            **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_events"], 3)
        self.assertEqual(body["total_billed_cost_micros"], 3_000_000)

    def test_usage_analytics_dimensions(self):
        from apps.metering.usage.services.usage_service import UsageService
        # The class already declares the tenant's rung — a rung of nothing, so
        # every other case here bills what the call cost. This one needs a
        # margin, so it RAISES the rung rather than declaring a second: only
        # one tenant default may exist, and creating a second is refused.
        TenantDefaultMarkup.objects.filter(tenant=self.tenant).update(
            markup_micro_percent=20_000_000)  # 20%
        # dimensions= now resolves through the registry (#128 rework); an
        # identity declaration (key == slot) is the porting move for tests
        # that grouped by a raw column name before the rework.
        GroupingField.objects.create(tenant=self.tenant, key="dim1", slot="grouping_field_1", scope="event")
        other = Customer.objects.create(tenant=self.tenant, external_id="c_other")
        UsageService.record_usage(
            tenant=self.tenant, customer=other,
            request_id="req_dim_1", idempotency_key="idem_dim_1",
            provider_cost_micros=2_000_000, metadata={"model": "gpt-4"},
            dimension_slots={"grouping_field_1": "chat"},
        )
        response = self.http_client.get(
            "/api/v1/metering/analytics/usage?tag_key=model&dimensions=dim1", **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("usage_markup_margin_micros", body)
        self.assertEqual(
            body["usage_markup_margin_micros"],
            body["total_billed_cost_micros"] - body["total_provider_cost_micros"],
        )
        self.assertTrue(body["by_customer"])      # non-empty
        # by_task_type stays empty until Task 10 populates task_type at record time.
        self.assertEqual(body["by_task_type"], [])
        self.assertTrue(body["by_tag"])           # non-empty (tag_key=model)
        # dim1 is a declared grouping field value ("chat"), reachable via the
        # generic dimensions= breakdown mechanism now that by_product is gone.
        dim1_values = {row["grouping_field_value"] for row in body["breakdowns"]["dim1"]}
        self.assertIn("chat", dim1_values)
        tag_values = {row["tag_value"] for row in body["by_tag"]}
        self.assertIn("gpt-4", tag_values)

    def test_metering_only_tenant_gets_403_on_billing_balance(self):
        """Metering-only tenant cannot access billing endpoints."""
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/balance",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    def test_usage_analytics_multi_dimension_breakdown(self):
        from apps.platform.customers.models import Customer
        from apps.metering.usage.models import Posting
        # dimensions= now resolves through the registry (#128 rework); the
        # tag:region escape hatch is gone (the open bag is not groupable), so
        # this ports "region" to a declared grouping field bound to dim4.
        GroupingField.objects.create(tenant=self.tenant, key="dim1", slot="grouping_field_1", scope="event")
        GroupingField.objects.create(tenant=self.tenant, key="dim2", slot="grouping_field_2", scope="event")
        GroupingField.objects.create(tenant=self.tenant, key="region", slot="grouping_field_4", scope="event")
        c = Customer.objects.create(tenant=self.tenant, external_id="acme_multi")
        Posting.objects.create(
            tenant=self.tenant, customer=c, request_id="r_md1", idempotency_key="i_md1",
            provider_cost_micros=300_000, billed_cost_micros=500_000, grouping_field_1="search",
            grouping_field_2="svcA", grouping_field_3="ag1", grouping_field_4="us",
        )
        resp = self.http_client.get(
            f"/api/v1/metering/analytics/usage?customer_id={c.id}"
            "&dimensions=dim1&dimensions=dim2&dimensions=region",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(resp.status_code, 200)
        b = resp.json()["breakdowns"]
        self.assertTrue(
            any(r["grouping_field_value"] == "search" and r["total_provider_cost_micros"] == 300_000
                for r in b["dim1"]),
            f"dim1 rows: {b.get('dim1')}",
        )
        self.assertTrue(
            any(r["grouping_field_value"] == "svcA" and r["total_provider_cost_micros"] == 300_000
                for r in b["dim2"]),
            f"dim2 rows: {b.get('dim2')}",
        )
        self.assertTrue(
            any(r["grouping_field_value"] == "us" and r["total_provider_cost_micros"] == 300_000
                for r in b["region"]),
            f"region rows: {b.get('region')}",
        )

    def test_usage_analytics_rejects_unknown_dimension(self):
        resp = self.http_client.get(
            "/api/v1/metering/analytics/usage?dimensions=ssn",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(resp.status_code, 422)

    def test_usage_analytics_breakdowns_include_provider_cost(self):
        from apps.metering.usage.models import Posting
        GroupingField.objects.create(tenant=self.tenant, key="dim1", slot="grouping_field_1", scope="event")
        c = Customer.objects.create(tenant=self.tenant, external_id="acme")
        Posting.objects.create(
            tenant=self.tenant, customer=c, request_id="r1", idempotency_key="i1",
            provider_cost_micros=300_000, billed_cost_micros=500_000, grouping_field_1="search",
        )
        resp = self.http_client.get(
            f"/api/v1/metering/analytics/usage?customer_id={c.id}&dimensions=dim1",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(
            any(r["customer__external_id"] == "acme" and r["total_provider_cost_micros"] == 300_000
                for r in body["by_customer"]),
            f"by_customer rows: {body['by_customer']}",
        )
        self.assertTrue(
            any(r["grouping_field_value"] == "search" and r["total_provider_cost_micros"] == 300_000
                for r in body["breakdowns"]["dim1"]),
            f"dim1 rows: {body['breakdowns'].get('dim1')}",
        )


class RateCardValidationTest(TestCase):
    """Book-centric surface: a BOOK create validates its kind; opening a rule
    validates the arithmetic shape; a publish soft-versions history."""

    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(name="Rate Tenant", products=["metering"])
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        # Declared first, because a rate names a declared quantity (#326) — and
        # declared even for the case whose point is a REFUSAL, so the refusal
        # asserted there is the one the test is named for rather than whichever
        # check happens to run first.
        for code in ("input_tokens", "tokens"):
            declares_a_quantity(self.tenant, code)

    def _post(self, path, body):
        return self.client.post(path, data=json.dumps(body),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def _cost_book(self):
        r = self._post("/api/v1/metering/pricing/rate-cards",
                       {"card_type": "cost", "key": "openai", "provider_key": "openai"})
        assert r.status_code == 200, r.content
        return r.json()["id"]

    def _open_rule(self, book_id, **change):
        """Declare a rule and publish it — the only way a book gains one (#367).

        Returns the publish response, so a caller wanting the rule reads
        `opened_rule_ids` off it rather than an echo of its own request.
        """
        declared = self._post(
            f"/api/v1/metering/pricing/rate-cards/{book_id}/publishes",
            {"changes": [{"kind": "add", **change}]})
        if declared.status_code != 200:
            return declared
        return self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}"
                          f"/publishes/{declared.json()['id']}/publish", {})

    def test_create_book_rejects_invalid_card_type(self):
        resp = self._post("/api/v1/metering/pricing/rate-cards",
                          {"card_type": "costs", "key": "x"})
        assert resp.status_code == 422

    def test_opening_a_rule_rejects_an_unratified_arithmetic_shape(self):
        # graduated was deleted end to end (ADR-0003) — not a ratified shape,
        # so the declaring body is refused before any draft is written.
        book_id = self._cost_book()
        resp = self._open_rule(book_id, measurement_key="input_tokens",
                               rate_structure="graduated")
        assert resp.status_code == 422

    def test_record_usage_surfaces_uncosted_measurement_keys(self):
        # A quantity with NO matching cost card -> the response lists it as
        # uncosted, and says the posting's cost is unresolved rather than zero.
        c = Customer.objects.create(tenant=self.tenant, external_id="acme2")
        resp = self.client.post("/api/v1/metering/usage",
            data=json.dumps(usage_payload(
                c, "r9", measurements={"undeclared_quantity": 100})),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        assert resp.status_code == 200
        assert "undeclared_quantity" in resp.json().get(
            "uncosted_measurement_keys", [])
        assert resp.json()["costing_status"] == "unresolved"

    def test_publish_keeps_lineage_and_versions_history(self):
        # create a cost book + a rule priced at 2
        book_id = self._cost_book()
        r1 = self._open_rule(book_id, measurement_key="tokens",
                             rate_structure="per_unit",
                             rate_per_unit_micros=2, unit_quantity=1)
        assert r1.status_code == 200, r1.content
        from apps.metering.pricing.models import Rate
        (rid,) = r1.json()["opened_rule_ids"]
        lineage = Rate.objects.get(id=rid).lineage_id
        # reprice the rule via publish -> new version supersedes the old
        pub = self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}/publish",
            {"changes": [{"measurement_key": "tokens", "rate_per_unit_micros": 9}]})
        assert pub.status_code == 200, pub.content
        # Three, not two: opening the rule was itself a publish (#367).
        assert pub.json()["version"] == 3
        # history: both versions, newest first
        h = self.client.get(
            f"/api/v1/metering/pricing/rate-cards/{book_id}/rates?include_history=true",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}").json()["data"]
        assert len(h) == 2
        assert h[0]["rate_per_unit_micros"] == 9 and h[1]["rate_per_unit_micros"] == 2
        assert h[0]["lineage_id"] == str(lineage)  # same lineage
        assert h[1]["lineage_id"] == str(lineage)
        assert h[0]["id"] != rid  # new version row
        # old version has valid_to set; new version valid_to is null
        assert h[1]["valid_to"] is not None and h[0]["valid_to"] is None


class RateCardBatchCreateTest(TestCase):
    """Opening several rules in one book (the batch endpoint is gone)."""

    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(name="Batch Rate Tenant", products=["metering"])
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        # See RateCardValidationTest above: declared first, including for the
        # case whose point is a different refusal entirely.
        for code in ("tokens", "images", "bad"):
            declares_a_quantity(self.tenant, code)

    def _post(self, path, body):
        return self.client.post(path, data=json.dumps(body),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def _cost_book(self):
        r = self._post("/api/v1/metering/pricing/rate-cards",
                       {"card_type": "cost", "key": "openai", "provider_key": "openai"})
        assert r.status_code == 200, r.content
        return r.json()["id"]

    def _open_rule(self, book_id, **change):
        """Declare a rule and publish it — the only way a book gains one (#367).

        Returns the publish response, so a caller wanting the rule reads
        `opened_rule_ids` off it rather than an echo of its own request.
        """
        declared = self._post(
            f"/api/v1/metering/pricing/rate-cards/{book_id}/publishes",
            {"changes": [{"kind": "add", **change}]})
        if declared.status_code != 200:
            return declared
        return self._post(f"/api/v1/metering/pricing/rate-cards/{book_id}"
                          f"/publishes/{declared.json()['id']}/publish", {})

    def test_many_rules_can_be_opened_in_one_book(self):
        from apps.metering.pricing.models import Rate
        book_id = self._cost_book()
        r1 = self._open_rule(book_id, measurement_key="tokens",
                             rate_structure="per_unit",
                             rate_per_unit_micros=2, unit_quantity=1)
        r2 = self._open_rule(book_id, measurement_key="images",
                             rate_structure="fixed_component", fixed_micros=500)
        assert r1.status_code == 200 and r2.status_code == 200
        assert Rate.objects.filter(tenant=self.tenant, rate_card_id=book_id).count() == 2

    def test_an_invalid_rule_creates_nothing(self):
        from apps.metering.pricing.models import Rate
        book_id = self._cost_book()
        before = Rate.objects.filter(tenant=self.tenant).count()
        resp = self._open_rule(book_id, measurement_key="bad",
                               rate_structure="package")  # deleted (ADR-0003)
        assert resp.status_code == 422
        assert Rate.objects.filter(tenant=self.tenant).count() == before  # zero created


class UsageTimeseriesEndpointTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(name="Timeseries Tenant", products=["metering"])
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")

    def test_usage_timeseries_daily_buckets(self):
        import datetime
        from django.utils import timezone
        from apps.platform.customers.models import Customer
        from apps.metering.usage.models import Posting
        c = Customer.objects.create(tenant=self.tenant, external_id="acme")
        for i, day in enumerate([1, 2, 3]):
            e = Posting.objects.create(tenant=self.tenant, customer=c, request_id=f"r{i}",
                idempotency_key=f"i{i}", provider_cost_micros=100_000, billed_cost_micros=150_000)
            Posting.objects.filter(id=e.id).update(
                effective_at=timezone.make_aware(timezone.datetime(2026, 6, day, 12, 0)))
        resp = self.client.get(
            "/api/v1/metering/analytics/usage/timeseries?customer_id=%s&granularity=day&start_date=2026-06-01&end_date=2026-07-01" % c.id,
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        assert resp.status_code == 200
        series = resp.json()["series"]
        assert len(series) == 3
        assert sum(b["provider_cost_micros"] for b in series) == 300_000

    def test_usage_timeseries_invalid_granularity_422(self):
        resp = self.client.get("/api/v1/metering/analytics/usage/timeseries?granularity=year",
                               HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        assert resp.status_code == 422


class DimensionBreakdownReconciliationTest(TestCase):
    """Breakdowns using dimensions=[...] must reconcile to the grand total.

    An event with an empty dim2 must NOT be silently excluded; it must
    appear as a '(unattributed)' row so that the sum of the breakdown equals
    the top-line total_provider_cost_micros.
    """

    def setUp(self):
        from apps.metering.usage.models import Posting

        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Reconcile Tenant", products=["metering"]
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        GroupingField.objects.create(tenant=self.tenant, key="dim2", slot="grouping_field_2", scope="event")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c_reconcile"
        )
        # Event 1: has a service tag -> grouping_field_2 = "svcA"
        Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            request_id="r_rec_1", idempotency_key="i_rec_1",
            provider_cost_micros=100_000, billed_cost_micros=100_000,
            grouping_field_2="svcA",
        )
        # Event 2: NO service tag -> dim2 is empty string (the default)
        Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            request_id="r_rec_2", idempotency_key="i_rec_2",
            provider_cost_micros=100_000, billed_cost_micros=100_000,
            grouping_field_2="",
        )

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def test_empty_dim2_bucketed_as_unattributed(self):
        """The breakdown must contain an '(unattributed)' row for the empty dim2
        event, and the row totals must sum to the overall total_provider_cost_micros."""
        resp = self.http_client.get(
            f"/api/v1/metering/analytics/usage"
            f"?customer_id={self.customer.id}&dimensions=dim2",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        # Grand total is both events combined: 200_000
        grand_total = body["total_provider_cost_micros"]
        self.assertEqual(grand_total, 200_000)

        breakdown = body["breakdowns"]["dim2"]
        dim_map = {row["grouping_field_value"]: row["total_provider_cost_micros"]
                   for row in breakdown}

        # The named-service event must still appear
        self.assertIn("svcA", dim_map)
        self.assertEqual(dim_map["svcA"], 100_000)

        # The empty-service event must appear as "(unattributed)"
        self.assertIn("(unattributed)", dim_map, f"breakdown rows: {breakdown}")
        self.assertEqual(dim_map["(unattributed)"], 100_000)

        # The breakdown must reconcile to the grand total
        breakdown_sum = sum(dim_map.values())
        self.assertEqual(
            breakdown_sum, grand_total,
            f"breakdown sum {breakdown_sum} != grand total {grand_total}; rows: {breakdown}",
        )


class RecordUsageCurrencyTest(TestCase):
    """CUR-1 choke point: record_usage rejects any currency that is not the
    tenant's default_currency (case-insensitive); stored normalized lowercase."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="CurTenant", products=["metering"], default_currency="usd")
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="cur")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="cur_c1")
        declares_a_caller_supplied_cost(self.tenant, DECLARED)

    def _post(self, body):
        return self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps(body),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )

    def _body(self, idem, **extra):
        return {
            "customer_id": str(self.customer.id),
            "request_id": f"req_{idem}",
            "idempotency_key": idem,
            "event_type": DECLARED,
            "provider_cost_micros": 1_000_000,
            **extra,
        }

    def test_mismatched_currency_returns_422(self):
        resp = self._post(self._body("cur_mismatch", currency="eur"))
        self.assertEqual(resp.status_code, 422, resp.content)
        self.assertIn("currency mismatch", resp.json()["detail"])
        from apps.metering.usage.models import Posting
        self.assertEqual(Posting.objects.filter(tenant=self.tenant).count(), 0)

    def test_matching_currency_accepted(self):
        resp = self._post(self._body("cur_match", currency="usd"))
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_currency_compare_is_case_insensitive_and_stored_lowercase(self):
        resp = self._post(self._body("cur_case", currency="USD"))
        self.assertEqual(resp.status_code, 200, resp.content)
        from apps.metering.usage.models import Posting
        event = Posting.objects.get(id=resp.json()["event_id"])
        self.assertEqual(event.currency, "usd")

    def test_omitted_currency_defaults_to_tenant_currency(self):
        eur_tenant = Tenant.objects.create(
            name="EurTenant", products=["metering"], default_currency="eur")
        _, eur_key = TenantApiKey.create_key(eur_tenant, label="cur-eur")
        eur_customer = Customer.objects.create(tenant=eur_tenant, external_id="cur_eur1")
        declares_a_caller_supplied_cost(eur_tenant, DECLARED, currency="eur")
        resp = self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps({
                "customer_id": str(eur_customer.id),
                "request_id": "req_eur",
                "idempotency_key": "idem_eur",
                "event_type": DECLARED,
                "provider_cost_micros": 1_000_000,
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {eur_key}",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        from apps.metering.usage.models import Posting
        event = Posting.objects.get(id=resp.json()["event_id"])
        self.assertEqual(event.currency, "eur")

    def test_batch_item_currency_mismatch_is_per_item_validation_error(self):
        resp = self.http_client.post(
            "/api/v1/metering/usage/batch",
            data=json.dumps({"events": [
                self._body("cur_batch_ok"),
                self._body("cur_batch_bad", currency="eur"),
            ]}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["accepted"], 1)
        self.assertEqual(body["rejected"], 1)
        self.assertTrue(body["results"][0]["accepted"])
        self.assertEqual(body["results"][1]["code"], "validation_error")
        self.assertIn("currency mismatch", body["results"][1]["detail"])
