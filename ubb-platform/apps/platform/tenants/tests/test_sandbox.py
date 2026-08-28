"""Sandbox-via-sibling-tenant (F4.4): schema, provisioning, key routing, reset.

The sandbox is a SIBLING Tenant row, so every tenant-scoped mechanism applies
to it for free; these tests pin the parts that are sandbox-specific.
"""
import hashlib
import secrets

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.events.webhook_models import TenantWebhookConfig
from apps.platform.event_types.tests._helpers import declares_a_quantity
from apps.platform.plans.models import Plan
from apps.platform.plans.tests._helpers import a_plan
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox
from apps.platform.tenants.tasks import reset_sandbox_tenant_sync


def _craft_key(tenant, prefix):
    """ORM-craft a TenantApiKey bypassing create_key (defense-in-depth tests)."""
    raw = prefix + secrets.token_urlsafe(32)
    return raw, TenantApiKey.objects.create(
        tenant=tenant,
        key_hash=hashlib.sha256(raw.encode()).hexdigest(),
        key_prefix=raw[:16],
        label="crafted",
    )


class SandboxProvisioningTest(TestCase):
    def setUp(self):
        self.live = Tenant.objects.create(
            name="Live Co",
            products=["metering", "billing"],
            billing_mode="prepaid",
            default_currency="eur",
            stripe_connected_account_id="acct_live_1",
            stripe_customer_id="cus_platform_1",
            charges_enabled=True,
        )

    def test_creates_sibling_with_copied_config_and_no_stripe_fields(self):
        sandbox = get_or_create_sandbox(self.live)
        self.assertTrue(sandbox.is_sandbox)
        self.assertEqual(sandbox.parent_tenant_id, self.live.id)
        self.assertEqual(sandbox.name, "Live Co (sandbox)")
        self.assertCountEqual(sandbox.products, ["metering", "billing"])
        self.assertEqual(sandbox.billing_mode, "prepaid")
        self.assertEqual(sandbox.default_currency, "eur")
        # The strict cost-coverage flag was copied here until #321 deleted it.
        # What a tenant tests is what they get, so the parity that matters is
        # behavioural and is asserted as behaviour, in
        # `api/v1/tests/test_onboarding_is_not_a_wall.py`: a sandbox and its
        # live parent admit the same limited start.
        # NEVER copied: Stripe linkage
        self.assertEqual(sandbox.stripe_connected_account_id, "")
        self.assertEqual(sandbox.stripe_customer_id, "")
        self.assertFalse(sandbox.charges_enabled)

    def test_idempotent_returns_same_row(self):
        first = get_or_create_sandbox(self.live)
        second = get_or_create_sandbox(self.live)
        self.assertEqual(first.id, second.id)
        self.assertEqual(
            Tenant.objects.filter(parent_tenant=self.live, is_sandbox=True).count(), 1)

    def test_refuses_sandbox_of_sandbox(self):
        sandbox = get_or_create_sandbox(self.live)
        with self.assertRaises(ValueError):
            get_or_create_sandbox(sandbox)

    def test_unique_constraint_one_sandbox_per_parent(self):
        get_or_create_sandbox(self.live)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Tenant.objects.create(
                name="dup", is_sandbox=True, parent_tenant=self.live)

    def test_check_constraint_sandbox_requires_parent(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Tenant.objects.create(name="orphan sandbox", is_sandbox=True)

    def test_check_constraint_live_cannot_have_parent(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Tenant.objects.create(
                name="live child", is_sandbox=False, parent_tenant=self.live)

    def test_race_loser_refetches_winner(self):
        # Simulate the lost race: the sibling appears AFTER the existence
        # check, so create() hits uq_one_sandbox_per_parent and must refetch.
        winner = Tenant.objects.create(
            name="Live Co (sandbox)", is_sandbox=True, parent_tenant=self.live)
        original_filter = Tenant.objects.filter
        calls = {"n": 0}

        def hide_first(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:  # the pre-create existence check misses
                return original_filter(id=None)
            return original_filter(*args, **kwargs)

        from unittest.mock import patch
        with patch.object(Tenant.objects, "filter", side_effect=hide_first):
            got = get_or_create_sandbox(self.live)
        self.assertEqual(got.id, winner.id)

    def test_parent_protected_against_delete_while_sandbox_exists(self):
        from django.db.models import ProtectedError
        get_or_create_sandbox(self.live)
        with self.assertRaises(ProtectedError), transaction.atomic():
            self.live.delete()


class ApiKeyRoutingTest(TestCase):
    def setUp(self):
        self.live = Tenant.objects.create(name="Live Co", products=["metering"])

    def test_test_key_on_live_tenant_routes_to_sandbox_sibling(self):
        key_obj, raw = TenantApiKey.create_key(self.live, label="t", is_test=True)
        self.assertTrue(raw.startswith("ubb_test_"))
        sandbox = Tenant.objects.get(parent_tenant=self.live, is_sandbox=True)
        self.assertEqual(key_obj.tenant_id, sandbox.id)

    def test_test_key_on_sandbox_mints_in_place(self):
        sandbox = get_or_create_sandbox(self.live)
        key_obj, raw = TenantApiKey.create_key(sandbox, label="t", is_test=True)
        self.assertEqual(key_obj.tenant_id, sandbox.id)
        self.assertTrue(raw.startswith("ubb_test_"))

    def test_live_key_on_sandbox_is_refused(self):
        sandbox = get_or_create_sandbox(self.live)
        with self.assertRaises(ValueError):
            TenantApiKey.create_key(sandbox, label="t", is_test=False)

    def test_live_key_on_live_tenant_unchanged(self):
        key_obj, raw = TenantApiKey.create_key(self.live, label="t")
        self.assertTrue(raw.startswith("ubb_live_"))
        self.assertEqual(key_obj.tenant_id, self.live.id)

    def test_verify_key_resolves_mode_matched_keys(self):
        _, raw_live = TenantApiKey.create_key(self.live, label="t")
        _, raw_test = TenantApiKey.create_key(self.live, label="t", is_test=True)
        self.assertEqual(TenantApiKey.verify_key(raw_live).tenant_id, self.live.id)
        sandbox = Tenant.objects.get(parent_tenant=self.live, is_sandbox=True)
        self.assertEqual(TenantApiKey.verify_key(raw_test).tenant_id, sandbox.id)

    def test_verify_key_rejects_live_prefix_on_sandbox_tenant(self):
        sandbox = get_or_create_sandbox(self.live)
        raw, _ = _craft_key(sandbox, "ubb_live_")
        self.assertIsNone(TenantApiKey.verify_key(raw))

    def test_verify_key_rejects_test_prefix_on_live_tenant(self):
        raw, _ = _craft_key(self.live, "ubb_test_")
        self.assertIsNone(TenantApiKey.verify_key(raw))

    def test_isolation_tenant_scoping_both_ways(self):
        sandbox = get_or_create_sandbox(self.live)
        Customer.objects.create(tenant=self.live, external_id="alice")
        Customer.objects.create(tenant=sandbox, external_id="alice")  # same ext id OK
        self.assertEqual(
            Customer.objects.filter(tenant=self.live).get().tenant_id, self.live.id)
        self.assertEqual(
            Customer.objects.filter(tenant=sandbox).get().tenant_id, sandbox.id)
        self.assertFalse(
            Customer.objects.filter(tenant=self.live, id__in=Customer.objects.filter(
                tenant=sandbox).values("id")).exists())


class SandboxResetTest(TestCase):
    def setUp(self):
        self.live = Tenant.objects.create(
            name="Live Co", products=["metering", "billing"], billing_mode="prepaid")
        self.sandbox = get_or_create_sandbox(self.live)
        self.key_obj, self.raw_key = TenantApiKey.create_key(
            self.sandbox, label="t", is_test=True)

    def _seed_domain_rows(self, tenant, ext_prefix=""):
        """Customers (business + pooled seat + soft-deleted seat), wallet money,
        usage, an outbox event — the rows a reset must wipe."""
        from apps.billing.wallets.models import Wallet, WalletTransaction
        from apps.metering.usage.models import Posting, PostingMeasurement
        from core.vocabulary import (
            COSTING_STATUS_UNRESOLVED, UNRESOLVED_REASON_COST_RATE_MISSING)

        biz = Customer.objects.create(
            tenant=tenant, external_id=f"{ext_prefix}biz",
            account_type="business", billing_topology="pooled")
        seat = Customer.objects.create(
            tenant=tenant, external_id=f"{ext_prefix}seat-1",
            account_type="seat", parent=biz)
        ghost = Customer.objects.create(
            tenant=tenant, external_id=f"{ext_prefix}seat-2",
            account_type="seat", parent=biz)
        # Soft-delete WITHOUT the lifecycle hook (direct column write): the
        # reset must still take it out via all_objects before the business.
        Customer.all_objects.filter(id=ghost.id).update(deleted_at=timezone.now())

        wallet = Wallet.objects.create(customer=biz, balance_micros=5_000_000)
        WalletTransaction.objects.create(
            wallet=wallet, transaction_type="TOP_UP", amount_micros=5_000_000,
            balance_after_micros=5_000_000, idempotency_key=f"{ext_prefix}seed")
        settled = Posting.objects.create(
            tenant=tenant, customer=seat,
            idempotency_key=f"{ext_prefix}k1", provider_cost_micros=100,
            billed_cost_micros=120)
        # ⚠ THE MEASUREMENT CHILDREN, AND THEY ARE WHY THIS FIXTURE CHANGED
        # (#354). Until this ticket a reset test could not see the child table
        # at all: every posting here was built through `Posting.objects.create`
        # and so had none, while every posting a real sandbox records through
        # the metering route has one. The child now carries a whole-record rule
        # refusing a `DELETE` before its horizon and while its posting is
        # unresolved — and a reset arrives at exactly that state, because
        # nothing sets the horizon and an uncosted call is the ordinary case in
        # test traffic. Django's collector deletes each child before its
        # posting, so a reset that could not take these could not take any
        # posting either, and the task would leave the sandbox quiesced.
        #
        # Both shapes are seeded because the rule has two conditions and either
        # alone would have refused the wipe.
        waiting = Posting.objects.create(
            tenant=tenant, customer=seat,
            idempotency_key=f"{ext_prefix}k2", provider_cost_micros=None,
            costing_status=COSTING_STATUS_UNRESOLVED,
            unresolved_reason=UNRESOLVED_REASON_COST_RATE_MISSING,
            billed_cost_micros=120)
        for posting in (settled, waiting):
            PostingMeasurement.objects.create(
                posting=posting, measurements={"input_tokens": 1200},
                recorded_at=posting.created_at)
        OutboxEvent.objects.create(
            event_type="usage.recorded", payload={}, tenant_id=str(tenant.id))
        return biz, seat, wallet

    def _seed_config_rows(self, tenant):
        from django.utils import timezone

        from apps.billing.gating.models import BudgetConfig
        from apps.metering.pricing.models import (
            CostBook, PricingBook, PricingBookPublish, Rate,
            TenantDefaultMarkup)
        from core.vocabulary import DECLARATION_STATUS_PUBLISHED

        Rate.objects.create(
            tenant=tenant,
            measurement=declares_a_quantity(tenant, "tokens"),
            rate_per_unit_micros=10)
        # THE TENANT'S DECLARED MARKUP RUNG (#357). Seeded here because the
        # sweep discovers tenant-scoped models GENERICALLY, so a rung missing
        # from `CONFIG_MODEL_LABELS` is wiped by a reset that says it is keeping
        # configuration — and a tenant with no rung prices every later event to
        # `unknown`. Nothing else in this fixture would notice: the row is
        # invisible to the domain-wipe assertions and to the label-resolution
        # check, which asks whether each label RESOLVES and not whether the
        # right models are in the set.
        TenantDefaultMarkup.objects.create(
            tenant=tenant, markup_micro_percent=20_000_000)
        # A RULE INSIDE A BOOK, AND THE PUBLISH RECORD THAT EXPLAINS IT (#358).
        # The rate above holds no book, which is a shape no route can produce
        # any more — every API-created rule lives in one. That mattered: the
        # book was not in the kept set, its rules hold it with `PROTECT`, and a
        # reset keeping the rules while wiping their container is refused
        # outright, so the whole reset failed. The publish record rides on the
        # same fix rather than beside it: it is CASCADEd from the book, so a
        # label of its own would have protected nothing.
        book = PricingBook.objects.create(
            tenant=tenant, key="sandbox", is_default=True)
        book.rates.create(
            tenant=tenant,
            measurement=declares_a_quantity(tenant, "book_tokens"),
            rate_per_unit_micros=20)
        PricingBookPublish.objects.create(
            tenant=tenant, pricing_book=book, effective_at=timezone.now(),
            changes=[], declaration_status=DECLARATION_STATUS_PUBLISHED,
            opened_rule_ids=[], closed_rule_ids=[])
        # ⚠ AND A COST BOOK WITH A RULE IN IT (#368). The container split into
        # two separately shaped entities, so there are two labels to leave out
        # of `CONFIG_MODEL_LABELS` instead of one — and a cost rule holds its
        # cost book with `PROTECT` exactly as a price rule holds its Pricing
        # Book, so a set naming only the price half would keep every rule and
        # wipe half the books they point at, and the database would refuse the
        # WHOLE reset. Nothing else in this fixture would notice: the
        # label-resolution check asks whether each label resolves, never
        # whether the right models are in the set.
        costs = CostBook.objects.create(
            tenant=tenant, key="sandbox-costs", provider_key="openai",
            currency="usd", is_default=True)
        costs.rates.create(
            tenant=tenant,
            measurement=declares_a_quantity(tenant, "supplier_tokens"),
            rate_per_unit_micros=3)
        # A PLAN AND THE BOOK IT PRICES FROM (#362). Seeded through the same
        # doors the plans route uses, for the reason the book above is seeded
        # at all: a Plan holds its Pricing Book with `PROTECT`, so the reset
        # has to take plans BEFORE books when it is wiping configuration, and
        # a generic sweep reaching them the other way round is refused by the
        # database and fails the WHOLE reset. Nothing here saw that before,
        # because no sandbox fixture had ever had a plan.
        a_plan(tenant=tenant, key="sandbox-plan", name="Sandbox plan")
        BudgetConfig.objects.create(tenant=tenant, cap_micros=1_000_000)
        TenantWebhookConfig.objects.create(
            tenant=tenant, url="https://example.com/hook", secret="s")

    def _live_counts(self):
        from apps.billing.wallets.models import Wallet, WalletTransaction
        from apps.metering.usage.models import Posting, PostingMeasurement

        return {
            "customers": Customer.all_objects.filter(tenant=self.live).count(),
            "wallets": Wallet.all_objects.filter(customer__tenant=self.live).count(),
            "txns": WalletTransaction.objects.filter(
                wallet__customer__tenant=self.live).count(),
            "usage": Posting.objects.filter(tenant=self.live).count(),
            # The child table, since the fixture began seeding it (#354). Without
            # this the "live rows untouched" assertion could not see the one
            # table the reset newly has to argue with, which is the state that
            # let the break this ticket found stay invisible.
            "measurements": PostingMeasurement.objects.filter(
                posting__tenant=self.live).count(),
            "outbox": OutboxEvent.objects.filter(tenant_id=self.live.id).count(),
        }

    def test_reset_keep_config_wipes_domain_preserves_config_and_keys(self):
        from apps.billing.gating.models import BudgetConfig
        from apps.billing.wallets.models import Wallet, WalletTransaction
        from apps.metering.pricing.models import (
            CostBook, PricingBook, PricingBookPublish, Rate,
            TenantDefaultMarkup)
        from apps.metering.usage.models import Posting
        from apps.platform.event_types.models import Measurement

        self._seed_domain_rows(self.sandbox, "sb-")
        self._seed_config_rows(self.sandbox)
        self._seed_domain_rows(self.live, "lv-")
        self._seed_config_rows(self.live)
        live_before = self._live_counts()

        result = reset_sandbox_tenant_sync(self.sandbox.id, keep_config=True)
        self.assertEqual(result["status"], "completed")

        # Domain rows gone — including the PROTECT seat hierarchy with its
        # soft-deleted seat (all_objects, seats before the business).
        self.assertEqual(Customer.all_objects.filter(tenant=self.sandbox).count(), 0)
        self.assertEqual(
            Wallet.all_objects.filter(customer__tenant=self.sandbox).count(), 0)
        self.assertEqual(WalletTransaction.objects.filter(
            wallet__customer__tenant=self.sandbox).count(), 0)
        self.assertEqual(Posting.objects.filter(tenant=self.sandbox).count(), 0)

        # Config preserved — all three rules (the one with no book, the one
        # in a Pricing Book and the one in a cost book), and the books
        # themselves: the seeded Pricing Book, the one the plan prices from
        # (#362), and the cost book (#368).
        self.assertEqual(Rate.objects.filter(tenant=self.sandbox).count(), 3)
        self.assertEqual(
            PricingBook.objects.filter(tenant=self.sandbox).count(), 2)
        self.assertEqual(
            CostBook.objects.filter(tenant=self.sandbox).count(), 1)
        # THE PLAN AND ITS BOOK TOGETHER (#362). A kept plan whose book was
        # wiped is not a state this reset may produce — the reference is NOT
        # NULL, so the database refuses it and the whole reset fails — and a
        # plan is what prices every customer created after the reset.
        self.assertEqual(Plan.objects.filter(tenant=self.sandbox).count(), 1)
        self.assertTrue(
            PricingBook.objects.filter(
                plans__tenant=self.sandbox, plans__key="sandbox-plan").exists())
        # And the record that says who changed that book's prices and when
        # (#358). A reset keeping the rules while wiping the publishes leaves
        # exactly the untraceable price this record exists to remove.
        self.assertEqual(
            PricingBookPublish.objects.filter(tenant=self.sandbox).count(), 1)
        # And the declarations those rates name, with them. A kept rate pointing
        # at a wiped quantity is not a state this reset may produce (#326) — it
        # is not merely undesirable, it is refused, and the whole reset fails.
        # Two since #358 and THREE since #368, one per seeded rule — the
        # third is the cost rule that exercises the cost book's own label.
        self.assertEqual(
            Measurement.objects.filter(
                event_type__tenant=self.sandbox).count(), 3)
        # And the tenant's declared markup rung (#357). It is configuration in
        # exactly the sense the rate above is — it decides what a customer is
        # charged — and a reset that wiped it would leave the sandbox pricing
        # every later event to `unknown` with nothing saying why.
        self.assertEqual(
            TenantDefaultMarkup.objects.filter(tenant=self.sandbox).count(), 1)
        self.assertEqual(BudgetConfig.objects.filter(tenant=self.sandbox).count(), 1)
        self.assertEqual(
            TenantWebhookConfig.objects.filter(tenant=self.sandbox).count(), 1)

        # Tenant + API keys always survive; tenant re-activated
        self.sandbox.refresh_from_db()
        self.assertTrue(self.sandbox.is_active)
        self.assertTrue(TenantApiKey.objects.filter(id=self.key_obj.id).exists())
        self.assertIsNotNone(TenantApiKey.verify_key(self.raw_key))

        # The completion event is registered and written on the sandbox
        events = OutboxEvent.objects.filter(tenant_id=self.sandbox.id)
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.get().event_type, "sandbox.reset_completed")
        from apps.platform.events.registry import handler_registry
        self.assertTrue(handler_registry.get_handlers("sandbox.reset_completed"))

        # Live rows byte-for-byte untouched (counts + money)
        self.assertEqual(self._live_counts(), live_before)
        live_wallet = Wallet.objects.get(customer__tenant=self.live)
        self.assertEqual(live_wallet.balance_micros, 5_000_000)

    def test_reset_without_keep_config_wipes_config_too(self):
        from apps.billing.gating.models import BudgetConfig
        from apps.metering.pricing.models import CostBook, PricingBook, Rate

        self._seed_domain_rows(self.sandbox, "sb-")
        self._seed_config_rows(self.sandbox)

        result = reset_sandbox_tenant_sync(self.sandbox.id, keep_config=False)
        # COMPLETED, WHICH IS THE ASSERTION AND NOT THE PREAMBLE (#362). A
        # `PROTECT` the sweep reaches in the wrong order does not wipe less —
        # it raises, every later model is skipped and the sandbox is left
        # INACTIVE. So this line is what says plans are taken before the books
        # they hold, and the counts below are what say the wipe still happened.
        self.assertEqual(result["status"], "completed")
        self.assertEqual(Rate.objects.filter(tenant=self.sandbox).count(), 0)
        self.assertEqual(Plan.objects.filter(tenant=self.sandbox).count(), 0)
        self.assertEqual(
            PricingBook.objects.filter(tenant=self.sandbox).count(), 0)
        self.assertEqual(
            CostBook.objects.filter(tenant=self.sandbox).count(), 0)
        # And the rows the pre-sweep steps deleted are REPORTED as deleted.
        # Both are visited twice — once ahead of the sweep for an ordering
        # reason and once by the sweep, which finds nothing left — so a count
        # that was assigned rather than accumulated would answer 0 for rows it
        # had just removed.
        self.assertEqual(result["deleted"]["pricing.Rate"], 3)
        self.assertEqual(result["deleted"]["plans.Plan"], 1)
        self.assertEqual(BudgetConfig.objects.filter(tenant=self.sandbox).count(), 0)
        self.assertEqual(
            TenantWebhookConfig.objects.filter(tenant=self.sandbox).count(), 0)
        # Tenant + keys still survive a full wipe
        self.assertTrue(TenantApiKey.objects.filter(id=self.key_obj.id).exists())
        self.sandbox.refresh_from_db()
        self.assertTrue(self.sandbox.is_active)

    def test_reset_refuses_live_tenant_id(self):
        self._seed_domain_rows(self.live, "lv-")
        before = self._live_counts()
        result = reset_sandbox_tenant_sync(self.live.id)
        self.assertEqual(result["status"], "refused")
        self.assertEqual(self._live_counts(), before)
        self.live.refresh_from_db()
        self.assertTrue(self.live.is_active)  # never quiesced

    def test_reset_refuses_unknown_id(self):
        import uuid
        result = reset_sandbox_tenant_sync(uuid.uuid4())
        self.assertEqual(result["status"], "refused")

    def test_reset_is_rerunnable(self):
        self._seed_domain_rows(self.sandbox, "sb-")
        first = reset_sandbox_tenant_sync(self.sandbox.id)
        second = reset_sandbox_tenant_sync(self.sandbox.id)
        self.assertEqual(first["status"], "completed")
        self.assertEqual(second["status"], "completed")
        self.assertEqual(Customer.all_objects.filter(tenant=self.sandbox).count(), 0)
        self.sandbox.refresh_from_db()
        self.assertTrue(self.sandbox.is_active)

    def test_reset_failure_leaves_sandbox_inactive(self):
        from unittest.mock import patch

        self._seed_domain_rows(self.sandbox, "sb-")
        # Deterministic failure before any wipe step: registry lookup blows up.
        with patch("apps.platform.tenants.tasks.django_apps.get_model",
                   side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                reset_sandbox_tenant_sync(self.sandbox.id)
        self.sandbox.refresh_from_db()
        self.assertFalse(self.sandbox.is_active)  # half-wiped: stays quiesced
        # And the run is repairable: a rerun completes + reactivates.
        result = reset_sandbox_tenant_sync(self.sandbox.id)
        self.assertEqual(result["status"], "completed")
        self.sandbox.refresh_from_db()
        self.assertTrue(self.sandbox.is_active)

    def test_quiesced_sandbox_rejects_its_key_mid_reset(self):
        Tenant.objects.filter(id=self.sandbox.id).update(is_active=False)
        self.assertIsNone(TenantApiKey.verify_key(self.raw_key))

    def test_config_model_labels_all_resolve(self):
        """A typo'd label would silently wipe config keep_config promised to keep."""
        from django.apps import apps as django_apps
        from apps.platform.tenants.tasks import CONFIG_MODEL_LABELS, _SKIP_LABELS

        for label in list(CONFIG_MODEL_LABELS) + list(_SKIP_LABELS):
            django_apps.get_model(label)  # raises LookupError on a bad label
