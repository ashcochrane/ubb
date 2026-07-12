"""F5.3: postpaid Invoice.create carries automatic_tax IFF opted in; a Stripe
tax-config rejection parks failed_permanent after ONE attempt with the alert;
wallet-money sites (checkout / PaymentIntent / receipts) NEVER carry it."""
import datetime
from unittest.mock import MagicMock, patch

import pytest
import stripe

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.metering.usage.models import UsageEvent
from apps.billing.invoicing.services.postpaid_service import PostpaidUsageService

PS, PE = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)


def _setup(**tenant_extra):
    t = Tenant.objects.create(name="T", products=["metering", "billing"],
                              billing_mode="postpaid", stripe_connected_account_id="acct_x",
                              charges_enabled=True, **tenant_extra)
    c = Customer.objects.create(tenant=t, external_id="c1", stripe_customer_id="cus_1")
    UsageEvent.objects.create(tenant=t, customer=c, request_id="r1", idempotency_key="i1",
        provider_cost_micros=600_000, billed_cost_micros=1_000_000)
    return t, c


def _invoice_create_kwargs(mock_sc, rec):
    for ck in mock_sc.call_args_list:
        if ck.kwargs.get("idempotency_key", "") == f"usage-invoice-{rec.id}":
            return ck.kwargs
    raise AssertionError("Invoice.create call not found")


@pytest.mark.django_db
class TestPostpaidAutomaticTax:
    def test_invoice_create_carries_automatic_tax_when_enabled(self):
        t, c = _setup(automatic_tax_enabled=True)
        with patch("apps.billing.invoicing.services.postpaid_service.stripe_call") as mock_sc, \
             patch("apps.platform.events.tasks.process_single_event"):
            mock_sc.return_value = MagicMock(id="obj_1")
            rec = PostpaidUsageService.push_customer_period(t, c, PS, PE)
        assert rec.status == "pushed"
        assert _invoice_create_kwargs(mock_sc, rec)["automatic_tax"] == {"enabled": True}

    def test_invoice_create_omits_automatic_tax_by_default(self):
        t, c = _setup()
        with patch("apps.billing.invoicing.services.postpaid_service.stripe_call") as mock_sc, \
             patch("apps.platform.events.tasks.process_single_event"):
            mock_sc.return_value = MagicMock(id="obj_1")
            rec = PostpaidUsageService.push_customer_period(t, c, PS, PE)
        assert "automatic_tax" not in _invoice_create_kwargs(mock_sc, rec)

    def test_tax_config_error_parks_failed_permanent_after_one_attempt(self):
        """InvalidRequestError (tax misconfig) -> StripeFatalError via the real
        stripe_call -> parked failed_permanent immediately, with the outbox
        alert and the error text on the row."""
        t, c = _setup(automatic_tax_enabled=True)
        empty_list = MagicMock()
        empty_list.auto_paging_iter.return_value = iter([])
        with patch("stripe.Invoice.list", return_value=empty_list), \
             patch("stripe.Invoice.create",
                   side_effect=stripe.error.InvalidRequestError(
                       "automatic_tax[enabled] cannot be `true`: no origin address",
                       None)) as create, \
             patch("apps.platform.events.tasks.process_single_event"):
            rec = PostpaidUsageService.push_customer_period(t, c, PS, PE)
        rec.refresh_from_db()
        assert rec.status == "failed_permanent"
        assert rec.push_attempts == 1
        assert create.call_count == 1  # parked immediately, no retry burn
        assert "automatic_tax" in rec.last_attempt_error
        alert = OutboxEvent.objects.get(
            event_type="usage.invoice_push_failed_permanent")
        assert "automatic_tax" in alert.payload["last_error"]


@pytest.mark.django_db
class TestWalletMoneySitesNeverCarryTax:
    """Top-up checkout / saved-PM PaymentIntent / receipts must never send
    automatic_tax even when the tenant opted in — wallet credit must equal
    the charged amount exactly."""

    def _customer(self):
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  stripe_connected_account_id="acct_x",
                                  charges_enabled=True, automatic_tax_enabled=True)
        return Customer.objects.create(tenant=t, external_id="c1",
                                       stripe_customer_id="cus_1")

    def _attempt(self, customer):
        from apps.billing.topups.models import TopUpAttempt
        return TopUpAttempt.objects.create(
            customer=customer, amount_micros=10_000_000,
            trigger="manual", status="pending")

    def test_checkout_session_never_carries_automatic_tax(self):
        from apps.billing.connectors.stripe.stripe_api import create_checkout_session
        customer = self._customer()
        attempt = self._attempt(customer)
        with patch("apps.billing.connectors.stripe.stripe_api.stripe_call",
                   return_value=MagicMock(id="cs_1", url="https://x")) as mock_sc:
            create_checkout_session(customer, 10_000_000, attempt,
                                    success_url="https://s", cancel_url="https://c")
        for ck in mock_sc.call_args_list:
            assert "automatic_tax" not in ck.kwargs

    def test_payment_intent_never_carries_automatic_tax(self):
        from apps.billing.connectors.stripe.stripe_api import charge_saved_payment_method
        customer = self._customer()
        attempt = self._attempt(customer)

        def fake(fn, **kw):
            # Bound classmethods are fresh objects per attribute access, so
            # match on __qualname__ rather than identity.
            assert "automatic_tax" not in kw
            name = getattr(fn, "__qualname__", "")
            if name == "PaymentMethod.list":
                return MagicMock(data=[MagicMock(id="pm_1")])
            if name == "Customer.retrieve":
                return {"invoice_settings": {"default_payment_method": "pm_1"}}
            return MagicMock(id="pi_1")

        with patch("apps.billing.connectors.stripe.stripe_api.stripe_call",
                   side_effect=fake) as mock_sc:
            intent = charge_saved_payment_method(customer, 10_000_000, attempt)
        assert intent is not None
        pi_calls = [ck for ck in mock_sc.call_args_list
                    if getattr(ck.args[0], "__qualname__", "") == "PaymentIntent.create"]
        assert len(pi_calls) == 1

    def test_receipt_invoice_never_carries_automatic_tax(self):
        from apps.billing.connectors.stripe.receipts import ReceiptService
        customer = self._customer()
        attempt = self._attempt(customer)
        with patch("apps.billing.connectors.stripe.receipts.stripe_call",
                   return_value=MagicMock(id="in_1")) as mock_sc:
            ReceiptService.create_topup_receipt(customer, attempt)
        assert mock_sc.call_count >= 4  # create, item, finalize, pay
        for ck in mock_sc.call_args_list:
            assert "automatic_tax" not in ck.kwargs
