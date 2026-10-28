"""A money mode needs its payment rail activated first (G27, ADR-0008 §6).

`prepaid` and `postpaid` are the modes in which UBB moves a tenant's customer
money, and ADR-0008 §6 makes entering one its own act: the rail is activated
for an environment by a named approver on recorded evidence, and only then may
a tenant use it — "enforced centrally, never as an advisory console
convention". These are G27's tests.

**Every test here builds its own activations, or none.** None of them uses the
fixture capability (`apps/platform/tenants/tests/_rails.py`): a refusal proved
under a helper that might have activated the rail proves nothing (the owner's
§0.4 E).

The owner's rulings are the shape:

- ruling 1 — the environment follows the tenant: a sandbox needs the `test`
  activation and every other tenant the `live` one, and a sandbox that cannot
  have its parent's mode is refused rather than downgraded;
- ruling 3 — ONE domain rule (`refuse_a_money_mode_without_its_rail`, reached
  from `Tenant.clean()`) serves every door that saves, and the database
  (`trg_tenant_money_mode_needs_its_rail`) holds the writes that never call it;
  the API answers by name, never with a raw database error.
"""
import json
from unittest.mock import patch

from django import forms
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.db import IntegrityError, connection, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.billing.topups.models import TopUpAttempt
from apps.billing.wallets.models import Wallet
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import (
    MONEY_MODES,
    PaymentRailActivation,
    PaymentRailClosed,
    Tenant,
    TenantApiKey,
)
from core.vocabulary import (
    CUSTOMER_BILLING_MODE_EXTERNAL,
    CUSTOMER_BILLING_MODE_POSTPAID,
    CUSTOMER_BILLING_MODE_PREPAID,
    PAYMENT_RAIL_ENVIRONMENT_LIVE,
    PAYMENT_RAIL_ENVIRONMENT_TEST,
    PAYMENT_RAIL_STRIPE,
    TENANT_POSTURE_FULL_BILLING,
)

REFUSED = "payment_rail_not_activated"
BILLING = ["metering", "billing"]


def _activate(environment, *, enabled=True):
    """An activation recorded here, by hand — never by the fixture helper."""
    return PaymentRailActivation.objects.create(
        rail=PAYMENT_RAIL_STRIPE, environment=environment,
        activated_at=timezone.now(), approved_by="the approver in this test",
        evidence="the evidence in this test", enabled=enabled)


class _TenantsTestCase(TestCase):

    def setUp(self):
        self.http = Client()

    def _external(self, name="Elsewhere"):
        tenant = Tenant.objects.create(name=name, products=BILLING)
        _, raw_key = TenantApiKey.create_key(tenant, label="k")
        return tenant, raw_key

    def _patch(self, raw_key, body):
        return self.http.patch(
            "/api/v1/tenant/config", data=json.dumps(body),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}")

    def _post(self, raw_key, path, body=None):
        return self.http.post(
            path, data=json.dumps(body or {}), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}")

    def _a_money_tenant(self, mode=CUSTOMER_BILLING_MODE_PREPAID):
        """A live tenant in a money mode, entered through the route."""
        tenant, raw_key = self._external()
        answered = self._patch(raw_key, {"billing_mode": mode})
        self.assertEqual(answered.status_code, 200, answered.content)
        tenant.refresh_from_db()
        return tenant, raw_key

    def assertRefusedByName(self, answered, environment):
        self.assertEqual(answered.status_code, 409, answered.content)
        body = answered.json()
        self.assertEqual(body["code"], REFUSED)
        self.assertIn(f"'{environment}' environment", body["detail"])

    def _sandboxes_of(self, tenant):
        return Tenant.objects.filter(parent_tenant=tenant, is_sandbox=True)


class TheEnvironmentFollowsTheTenantTest(_TenantsTestCase):
    """The owner's ruling 1, as its four pins and the case beside them."""

    def test_a_live_tenant_with_the_live_activation_is_admitted(self):
        _activate(PAYMENT_RAIL_ENVIRONMENT_LIVE)
        tenant, raw_key = self._external()

        for mode in sorted(MONEY_MODES):
            with self.subTest(mode=mode):
                answered = self._patch(raw_key, {"billing_mode": mode})

                self.assertEqual(answered.status_code, 200, answered.content)
                self.assertEqual(
                    (answered.json()["billing_mode"],
                     answered.json()["tenant_posture"]),
                    (mode, TENANT_POSTURE_FULL_BILLING))

    def test_a_sandbox_with_the_test_activation_is_admitted(self):
        _activate(PAYMENT_RAIL_ENVIRONMENT_LIVE)
        _activate(PAYMENT_RAIL_ENVIRONMENT_TEST)
        tenant, raw_key = self._a_money_tenant(CUSTOMER_BILLING_MODE_POSTPAID)

        answered = self._post(raw_key, "/api/v1/tenant/sandbox")

        self.assertEqual(answered.status_code, 200, answered.content)
        sandbox = self._sandboxes_of(tenant).get()
        self.assertEqual(sandbox.billing_mode, CUSTOMER_BILLING_MODE_POSTPAID)

    def test_a_sandbox_with_only_the_live_activation_is_refused(self):
        _activate(PAYMENT_RAIL_ENVIRONMENT_LIVE)
        tenant, raw_key = self._a_money_tenant()

        doors = {
            "POST /tenant/sandbox": lambda: self._post(
                raw_key, "/api/v1/tenant/sandbox"),
            "POST /tenant/api-keys (a test key provisions the sandbox)":
                lambda: self._post(raw_key, "/api/v1/tenant/api-keys",
                                   {"label": "t", "is_test": True}),
        }
        for door, call in doors.items():
            with self.subTest(door=door):
                self.assertRefusedByName(call(), PAYMENT_RAIL_ENVIRONMENT_TEST)
                self.assertFalse(self._sandboxes_of(tenant).exists())

    def test_a_refused_sandbox_is_never_downgraded_to_external(self):
        """No automatic posture downgrade: refused means no sandbox at all —
        not one quietly provisioned `external` so the call could succeed."""
        _activate(PAYMENT_RAIL_ENVIRONMENT_LIVE)
        tenant, raw_key = self._a_money_tenant()

        self._post(raw_key, "/api/v1/tenant/sandbox")

        self.assertEqual(Tenant.objects.filter(is_sandbox=True).count(), 0)
        tenant.refresh_from_db()
        self.assertEqual(tenant.billing_mode, CUSTOMER_BILLING_MODE_PREPAID)

    def test_a_live_tenant_with_only_the_test_activation_is_refused(self):
        _activate(PAYMENT_RAIL_ENVIRONMENT_TEST)
        tenant, raw_key = self._external()

        answered = self._patch(raw_key, {"billing_mode": CUSTOMER_BILLING_MODE_PREPAID})

        self.assertRefusedByName(answered, PAYMENT_RAIL_ENVIRONMENT_LIVE)


class EveryDoorRefusesAMoneyModeWithoutItsRailTest(_TenantsTestCase):
    """With no activation at all, every door that can write a tenant refuses —
    the one domain rule at the doors that save, the database at the rest."""

    def test_the_config_route_refuses_by_name_and_writes_nothing(self):
        tenant, raw_key = self._external()
        tenant.enforcement_mode = "off"
        tenant.save(update_fields=["enforcement_mode"])
        for mode in sorted(MONEY_MODES):
            with self.subTest(mode=mode):
                answered = self._patch(raw_key, {"billing_mode": mode,
                                                 "enforcement_mode": "enforcing"})

                self.assertRefusedByName(answered, PAYMENT_RAIL_ENVIRONMENT_LIVE)
                tenant.refresh_from_db()
                self.assertEqual((tenant.billing_mode, tenant.enforcement_mode),
                                 (CUSTOMER_BILLING_MODE_EXTERNAL, "off"))

    def test_a_disabled_activation_is_no_activation(self):
        _activate(PAYMENT_RAIL_ENVIRONMENT_LIVE, enabled=False)
        tenant, raw_key = self._external()

        answered = self._patch(raw_key, {"billing_mode": CUSTOMER_BILLING_MODE_PREPAID})

        self.assertRefusedByName(answered, PAYMENT_RAIL_ENVIRONMENT_LIVE)
        with self.assertRaisesRegex(IntegrityError, REFUSED):
            with transaction.atomic():
                Tenant.objects.filter(pk=tenant.pk).update(
                    billing_mode=CUSTOMER_BILLING_MODE_PREPAID)

    def test_the_admin_form_refuses_on_the_field(self):
        tenant, _ = self._external()
        admin = get_user_model().objects.create_superuser(
            username="operator", email="operator@example.com", password="pw")
        self.http.force_login(admin)
        url = reverse("admin:tenants_tenant_change", args=[tenant.pk])
        form = self.http.get(url).context["adminform"].form

        answered = self.http.post(url, _posted(form, billing_mode=CUSTOMER_BILLING_MODE_PREPAID))

        self.assertEqual(answered.status_code, 200)  # the form, re-rendered
        errors = answered.context["adminform"].form.errors
        # The ONLY error: a refusal for any other reason would pass here
        # while proving nothing about the rail.
        self.assertEqual(set(errors), {"billing_mode"})
        self.assertIn("payment rail", " ".join(errors["billing_mode"]))
        tenant.refresh_from_db()
        self.assertEqual(tenant.billing_mode, CUSTOMER_BILLING_MODE_EXTERNAL)

    def test_the_admin_form_admits_it_once_the_rail_is_activated(self):
        """The control for the test above: the same post, with the activation."""
        _activate(PAYMENT_RAIL_ENVIRONMENT_LIVE)
        tenant, _ = self._external()
        admin = get_user_model().objects.create_superuser(
            username="operator", email="operator@example.com", password="pw")
        self.http.force_login(admin)
        url = reverse("admin:tenants_tenant_change", args=[tenant.pk])
        form = self.http.get(url).context["adminform"].form

        answered = self.http.post(url, _posted(form, billing_mode=CUSTOMER_BILLING_MODE_PREPAID))

        self.assertEqual(answered.status_code, 302, getattr(answered, "context", None)
                         and answered.context["adminform"].form.errors)
        tenant.refresh_from_db()
        self.assertEqual(tenant.billing_mode, CUSTOMER_BILLING_MODE_PREPAID)

    def test_the_seed_command_refuses_and_fabricates_no_evidence(self):
        for mode in sorted(MONEY_MODES):
            with self.subTest(mode=mode):
                with self.assertRaisesRegex(CommandError, "payment rail"):
                    call_command("seed_dev_data", "--stripe-account", "acct_seed",
                                 "--tenant-name", f"Seed {mode}",
                                 "--billing-mode", mode)

                self.assertFalse(Tenant.objects.filter(name=f"Seed {mode}").exists())
                self.assertFalse(PaymentRailActivation.objects.exists())

    def test_the_seed_command_defaults_to_external(self):
        call_command("seed_dev_data", "--stripe-account", "acct_seed",
                     "--tenant-name", "Seeded")

        self.assertEqual(Tenant.objects.get(name="Seeded").billing_mode,
                         CUSTOMER_BILLING_MODE_EXTERNAL)

    def test_the_database_refuses_the_writes_that_never_call_save(self):
        tenant, _ = self._external()
        live = Tenant(name="Inserted", products=BILLING,
                      billing_mode=CUSTOMER_BILLING_MODE_PREPAID,
                      widget_secret="inserted-without-save")
        doors = {
            "QuerySet.update()": lambda: Tenant.objects.filter(
                pk=tenant.pk).update(billing_mode=CUSTOMER_BILLING_MODE_PREPAID),
            "raw SQL UPDATE": lambda: connection.cursor().execute(
                "UPDATE ubb_tenant SET billing_mode = %s WHERE id = %s",
                [CUSTOMER_BILLING_MODE_POSTPAID, str(tenant.pk)]),
            "bulk_create() (an INSERT that never calls save())":
                lambda: Tenant.objects.bulk_create([live]),
        }
        for door, write in doors.items():
            with self.subTest(door=door):
                with self.assertRaisesRegex(IntegrityError, REFUSED):
                    with transaction.atomic():
                        write()
                tenant.refresh_from_db()
                self.assertEqual(tenant.billing_mode, CUSTOMER_BILLING_MODE_EXTERNAL)
                self.assertFalse(Tenant.objects.filter(name="Inserted").exists())

    def test_the_database_holds_the_environment_too(self):
        """A sandbox row with only the live activation: the domain rule's
        environment, held where `save()` is never called."""
        _activate(PAYMENT_RAIL_ENVIRONMENT_LIVE)
        parent, _ = self._a_money_tenant()
        sandbox = Tenant(name="Sandbox by hand", products=BILLING,
                         billing_mode=CUSTOMER_BILLING_MODE_PREPAID,
                         is_sandbox=True, parent_tenant=parent,
                         widget_secret="inserted-without-save")

        with self.assertRaisesRegex(IntegrityError, REFUSED):
            with transaction.atomic():
                Tenant.objects.bulk_create([sandbox])


class ATenantAlreadyInAMoneyModeIsLeftAloneTest(_TenantsTestCase):
    """The rule governs ENTERING a money mode. Disabling a rail stops new use
    and touches nobody already using it — there is no dependent-tenant scan
    (the owner's ruling 2), so a re-save asks nothing."""

    def setUp(self):
        super().setUp()
        self.activation = _activate(PAYMENT_RAIL_ENVIRONMENT_LIVE)
        self.tenant, self.raw_key = self._a_money_tenant()
        self.activation.enabled = False
        self.activation.save()

    def test_every_door_still_writes_the_tenants_other_columns(self):
        doors = {
            "save()": lambda: _renamed_by_save(self.tenant),
            "the config route": lambda: self.assertEqual(
                self._patch(self.raw_key, {"enforcement_mode": "enforcing"}).status_code,
                200),
            "QuerySet.update()": lambda: Tenant.objects.filter(
                pk=self.tenant.pk).update(name="Renamed by update"),
        }
        for door, write in doors.items():
            with self.subTest(door=door):
                write()
                self.tenant.refresh_from_db()
                self.assertEqual(self.tenant.billing_mode, CUSTOMER_BILLING_MODE_PREPAID)

    def test_moving_to_the_other_money_mode_is_entering_it(self):
        answered = self._patch(self.raw_key,
                               {"billing_mode": CUSTOMER_BILLING_MODE_POSTPAID})

        self.assertRefusedByName(answered, PAYMENT_RAIL_ENVIRONMENT_LIVE)

    def test_leaving_for_external_is_always_open(self):
        answered = self._patch(self.raw_key,
                               {"billing_mode": CUSTOMER_BILLING_MODE_EXTERNAL})

        self.assertEqual(answered.status_code, 200, answered.content)


class AClosedRailStartsNoNewMoneyTest(_TenantsTestCase):
    """The flag's ONE operational meaning (ADR-0008 §6: it "technically prevents
    premature use"; the owner's ruling 2: disabling it "may stop new activation
    or use of the rail"; the owner's review of #619).

    A tenant already in a money mode, on an activated rail, and then the
    operator turns the flag off: the tenant keeps its mode — nothing scans it —
    but every NEW customer-money operation is refused by name, before anything
    reaches Stripe. Turning the flag back on is the control.
    """

    STRIPE_CALL = "apps.billing.connectors.stripe.stripe_api.stripe_call"

    def setUp(self):
        super().setUp()
        self.activation = _activate(PAYMENT_RAIL_ENVIRONMENT_LIVE)
        self.tenant, self.raw_key = self._a_money_tenant()
        Tenant.objects.filter(pk=self.tenant.pk).update(
            stripe_connected_account_id="acct_rail", charges_enabled=True)
        self.tenant.refresh_from_db()
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c-rail", stripe_customer_id="cus_rail")
        Wallet.objects.create(customer=self.customer, balance_micros=0)
        self._close_the_rail()

    def _close_the_rail(self):
        self.activation.enabled = False
        self.activation.save()

    def _top_up(self, key="tp-rail-1"):
        return self._post(self.raw_key,
                          f"/api/v1/billing/customers/{self.customer.id}/top-up",
                          {"amount_micros": 20_000_000, "idempotency_key": key,
                           "success_url": "https://example.com/ok",
                           "cancel_url": "https://example.com/no"})

    def test_the_tenant_keeps_its_mode(self):
        """Nothing scans a dependent tenant: closing the rail moves no mode."""
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.billing_mode, CUSTOMER_BILLING_MODE_PREPAID)

    def test_a_top_up_checkout_is_refused_by_name_before_stripe(self):
        with patch(self.STRIPE_CALL) as stripe_call:
            answered = self._top_up()

        self.assertRefusedByName(answered, PAYMENT_RAIL_ENVIRONMENT_LIVE)
        stripe_call.assert_not_called()

    def test_an_auto_top_up_charge_is_refused_before_stripe(self):
        from apps.billing.connectors.stripe.stripe_api import (
            charge_saved_payment_method)
        attempt = TopUpAttempt.objects.create(
            customer=self.customer, billing_owner_id=self.customer.id,
            amount_micros=20_000_000, trigger="auto_topup", status="pending")

        with patch(self.STRIPE_CALL) as stripe_call:
            with self.assertRaisesRegex(PaymentRailClosed, "'live' environment"):
                charge_saved_payment_method(self.customer, 20_000_000, attempt)

        stripe_call.assert_not_called()

    def test_a_usage_invoice_is_held_recoverably_and_pushes_once_the_rail_reopens(self):
        from apps.billing.invoicing.models import CustomerUsageInvoice
        from apps.billing.invoicing.services.postpaid_service import (
            PostpaidUsageService)
        from apps.billing.invoicing.tasks import _recover_skipped_usage_invoices
        _activate_postpaid = self._patch(
            self.raw_key, {"billing_mode": CUSTOMER_BILLING_MODE_POSTPAID})
        # Postpaid is ENTERED here, so the rail must be open for it; then closed.
        self.assertRefusedByName(_activate_postpaid, PAYMENT_RAIL_ENVIRONMENT_LIVE)
        Tenant.objects.filter(pk=self.tenant.pk).update(
            billing_mode=CUSTOMER_BILLING_MODE_EXTERNAL)
        self.activation.enabled = True
        self.activation.save()
        Tenant.objects.filter(pk=self.tenant.pk).update(
            billing_mode=CUSTOMER_BILLING_MODE_POSTPAID)
        self._close_the_rail()
        self.tenant.refresh_from_db()
        period = (timezone.now().date().replace(day=1),
                  timezone.now().date().replace(day=28))

        with patch.object(PostpaidUsageService, "aggregate_lines",
                          return_value=(5_000_000, [("Usage", 5_000_000)])), \
                patch("apps.billing.invoicing.services.postpaid_service.stripe_call") \
                as stripe_call:
            row = PostpaidUsageService.push_customer_period(
                self.tenant, self.customer, *period)

        self.assertEqual((row.status, row.skip_reason), ("skipped", "payment_rail_closed"))
        stripe_call.assert_not_called()

        _recover_skipped_usage_invoices(CustomerUsageInvoice)
        row.refresh_from_db()
        self.assertEqual(row.status, "skipped")  # still closed: stays held

        self.activation.enabled = True
        self.activation.save()
        _recover_skipped_usage_invoices(CustomerUsageInvoice)
        row.refresh_from_db()
        self.assertEqual((row.status, row.skip_reason), ("pending", None))

    def test_resuming_a_subscription_is_refused_by_name(self):
        with patch("apps.subscriptions.orchestration.service.stripe_call") as stripe_call:
            answered = self._post(
                self.raw_key,
                f"/api/v1/subscriptions/customers/{self.customer.external_id}"
                f"/subscription/resume")

        self.assertRefusedByName(answered, PAYMENT_RAIL_ENVIRONMENT_LIVE)
        stripe_call.assert_not_called()

    def test_starting_a_subscription_is_refused_before_stripe(self):
        from apps.platform.plans.tests._helpers import a_plan
        from apps.subscriptions.orchestration.service import SubscriptionOrchestrator
        plan = a_plan(tenant=self.tenant, key="pro", access_fee_micros=20_000_000)

        with patch("apps.subscriptions.orchestration.service.stripe_call") as stripe_call:
            with self.assertRaises(PaymentRailClosed):
                SubscriptionOrchestrator.subscribe(self.customer, plan, 1)

        stripe_call.assert_not_called()

    def test_reopening_the_rail_lets_new_money_start_again(self):
        """THE CONTROL: the same top-up, the flag back on."""
        self.activation.enabled = True
        self.activation.save()

        with patch(self.STRIPE_CALL) as stripe_call:
            stripe_call.return_value.url = "https://checkout.example/s"
            stripe_call.return_value.id = "cs_rail"
            answered = self._top_up(key="tp-rail-2")

        self.assertEqual(answered.status_code, 200, answered.content)
        self.assertTrue(stripe_call.called)


def _renamed_by_save(tenant):
    tenant.name = "Renamed by save"
    tenant.save()


def _posted(form, **changes):
    """The admin form's own current values, as a browser would post them,
    with `changes` applied — so the post is the form's, not this test's.

    The tenant's two JSON settings are required by the form and an empty
    object reads as empty, so an operator fills each in; this post does too,
    so the only thing that can refuse it is the rule under test.
    """
    changes = {"branding_config": {"filled_in": "by the operator"},
               "metadata": {"filled_in": "by the operator"}, **changes}
    data = {}
    for name, field in form.fields.items():
        value = changes.get(name, form[name].value())
        if isinstance(field, forms.BooleanField):
            if value:
                data[name] = "on"
            continue
        if value is None:
            data[name] = ""
        elif isinstance(value, str):
            data[name] = value
        else:
            data[name] = field.prepare_value(value)
    return data
