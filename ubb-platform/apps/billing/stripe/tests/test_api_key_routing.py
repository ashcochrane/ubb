"""F4.4: per-tenant Stripe key routing.

- api_key_for_tenant: live -> platform key; sandbox -> STRIPE_TEST_SECRET_KEY,
  refusing anything that is not an sk_test_ key.
- stripe_call: api_key is REQUIRED keyword-only (a missed site is a TypeError)
  and is forwarded to the wrapped Stripe function.
- End-to-end: a sandbox flow hands the TEST key to (mocked) Stripe; the live
  flow hands the platform key.
"""
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase, override_settings

from apps.billing.stripe.services.stripe_service import api_key_for_tenant, stripe_call
from apps.billing.topups.models import TopUpAttempt
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox
from core.exceptions import StripeFatalError


class ApiKeyForTenantTest(TestCase):
    def setUp(self):
        self.live = Tenant.objects.create(name="L", products=["metering"])
        self.sandbox = get_or_create_sandbox(self.live)

    def test_live_tenant_gets_platform_key(self):
        from django.conf import settings
        self.assertEqual(api_key_for_tenant(self.live), settings.STRIPE_SECRET_KEY)

    def test_sandbox_without_test_key_raises(self):
        with override_settings(STRIPE_TEST_SECRET_KEY=""):
            with pytest.raises(StripeFatalError, match="STRIPE_TEST_SECRET_KEY"):
                api_key_for_tenant(self.sandbox)

    def test_sandbox_refuses_non_sk_test_key(self):
        with override_settings(STRIPE_TEST_SECRET_KEY="sk_live_oops"):
            with pytest.raises(StripeFatalError, match="sk_test_"):
                api_key_for_tenant(self.sandbox)

    def test_sandbox_gets_test_key(self):
        with override_settings(STRIPE_TEST_SECRET_KEY="sk_test_sandbox"):
            self.assertEqual(api_key_for_tenant(self.sandbox), "sk_test_sandbox")


class StripeCallApiKeyContractTest(TestCase):
    def test_api_key_is_required_keyword(self):
        with pytest.raises(TypeError):
            stripe_call(MagicMock())  # no api_key -> TypeError, never a live call

    def test_empty_api_key_is_fatal(self):
        with pytest.raises(StripeFatalError):
            stripe_call(MagicMock(), api_key="")

    def test_api_key_is_forwarded_to_the_stripe_fn(self):
        fn = MagicMock(return_value="ok")
        result = stripe_call(fn, api_key="sk_test_k", customer="cus_1")
        self.assertEqual(result, "ok")
        fn.assert_called_once_with(api_key="sk_test_k", customer="cus_1")


class FlowKeyThreadingTest(TestCase):
    """The checkout flow (a representative stripe_call site) hands Stripe the
    key for the tenant in scope."""

    def _charge_ready(self, tenant):
        tenant.stripe_connected_account_id = "acct_shared"
        tenant.charges_enabled = True
        tenant.save(update_fields=[
            "stripe_connected_account_id", "charges_enabled", "updated_at"])

    def _fixtures(self, tenant, ext):
        customer = Customer.objects.create(
            tenant=tenant, external_id=ext, stripe_customer_id=f"cus_{ext}")
        attempt = TopUpAttempt.objects.create(
            customer=customer, amount_micros=1_000_000, trigger="manual",
            status="pending")
        return customer, attempt

    def test_live_flow_passes_platform_key(self):
        from django.conf import settings
        from apps.billing.connectors.stripe.stripe_api import create_checkout_session

        live = Tenant.objects.create(name="L", products=["metering", "billing"])
        self._charge_ready(live)
        customer, attempt = self._fixtures(live, "alice")
        with patch("apps.billing.connectors.stripe.stripe_api.stripe.checkout.Session.create",
                   return_value=MagicMock(id="cs_1", url="https://stripe/cs_1")) as create:
            create_checkout_session(
                customer, 1_000_000, attempt, success_url="https://x/s", cancel_url="https://x/c")
        self.assertEqual(create.call_args.kwargs["api_key"], settings.STRIPE_SECRET_KEY)

    @override_settings(STRIPE_TEST_SECRET_KEY="sk_test_sandbox")
    def test_sandbox_flow_passes_the_test_key(self):
        from apps.billing.connectors.stripe.stripe_api import create_checkout_session

        live = Tenant.objects.create(name="L", products=["metering", "billing"])
        sandbox = get_or_create_sandbox(live)
        self._charge_ready(sandbox)
        customer, attempt = self._fixtures(sandbox, "alice")
        with patch("apps.billing.connectors.stripe.stripe_api.stripe.checkout.Session.create",
                   return_value=MagicMock(id="cs_1", url="https://stripe/cs_1")) as create:
            create_checkout_session(
                customer, 1_000_000, attempt, success_url="https://x/s", cancel_url="https://x/c")
        self.assertEqual(create.call_args.kwargs["api_key"], "sk_test_sandbox")

    @override_settings(STRIPE_TEST_SECRET_KEY="")
    def test_sandbox_flow_without_test_key_fails_loudly_not_live(self):
        from apps.billing.connectors.stripe.stripe_api import create_checkout_session

        live = Tenant.objects.create(name="L", products=["metering", "billing"])
        sandbox = get_or_create_sandbox(live)
        self._charge_ready(sandbox)
        customer, attempt = self._fixtures(sandbox, "alice")
        with patch("apps.billing.connectors.stripe.stripe_api.stripe.checkout.Session.create") as create:
            with pytest.raises(StripeFatalError):
                create_checkout_session(
                    customer, 1_000_000, attempt,
                    success_url="https://x/s", cancel_url="https://x/c")
        create.assert_not_called()  # never falls back to the live key
