"""GATED live Stripe-test-mode AR payload-shape check (SKIPPED by default).

This is the only test in the Wave-5a AR suite that talks to a REAL Stripe.
It is opt-in: it does nothing unless UBB_STRIPE_LIVE_TEST is set, plus the two
Stripe test-mode credentials below. Its purpose is to assert that the REAL
Basil (2025-03-31.basil) invoice payload exposes the exact field paths our reconcile
handlers read — guarding against a Stripe API-version drift our mocked capstone
(which constructs synthetic objects) could never catch.
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("UBB_STRIPE_LIVE_TEST"),
    reason="opt-in live Stripe test; set UBB_STRIPE_LIVE_TEST=1 + "
           "STRIPE_TEST_SECRET_KEY + STRIPE_TEST_CONNECTED_ACCOUNT")


def test_live_invoice_payload_shape():
    """HOW TO RUN: set UBB_STRIPE_LIVE_TEST=1, STRIPE_TEST_SECRET_KEY (a Stripe
    TEST-mode secret key for a Connect platform), and STRIPE_TEST_CONNECTED_ACCOUNT
    (an acct_ in test mode). Verifies the REAL Basil (2025-03-31.basil) invoice payload
    field paths our handlers read."""
    import stripe
    from apps.billing.stripe.services.stripe_service import STRIPE_API_VERSION  # applies the global pin
    assert stripe.api_version == STRIPE_API_VERSION
    stripe.api_key = os.environ["STRIPE_TEST_SECRET_KEY"]
    acct = os.environ["STRIPE_TEST_CONNECTED_ACCOUNT"]
    from apps.billing.connectors.stripe.invoice_routing import _invoice_subscription_id

    # Create a customer + a one-off invoice item + invoice on the connected
    # account, finalize it, then RETRIEVE it and assert the field paths our
    # reconcile reads exist + are shaped right.
    cust = stripe.Customer.create(stripe_account=acct, email="live-ar-test@example.com")
    stripe.InvoiceItem.create(
        stripe_account=acct, customer=cust.id, amount=500, currency="usd")
    inv = stripe.Invoice.create(
        stripe_account=acct, customer=cust.id, auto_advance=False)
    inv = stripe.Invoice.finalize_invoice(inv.id, stripe_account=acct)

    # status + hosted links our handlers store
    assert inv.status in ("open", "paid")
    assert inv.hosted_invoice_url and inv.invoice_pdf  # populated at finalization

    # status_transitions.paid_at is the path handle_invoice_paid reads
    assert hasattr(inv, "status_transitions")

    # our Basil-safe subscription extractor returns None for a standalone invoice
    assert _invoice_subscription_id(inv) is None

    # re-RETRIEVE to confirm the same paths survive a fresh fetch
    fetched = stripe.Invoice.retrieve(inv.id, stripe_account=acct)
    assert fetched.status in ("open", "paid")
    assert fetched.hosted_invoice_url and fetched.invoice_pdf
    assert hasattr(fetched, "status_transitions")
    assert _invoice_subscription_id(fetched) is None


def test_live_b1_items_land_on_invoice():
    """HOW TO RUN: set UBB_STRIPE_LIVE_TEST=1, STRIPE_TEST_SECRET_KEY (a Connect
    platform test key), and STRIPE_TEST_CONNECTED_ACCOUNT (an acct_ in test mode).
    These tests SHIP SKIPPED — do not run without real Stripe test credentials.

    B1: pinning InvoiceItems to a draft via invoice=<id> + finalize => the finalized
    invoice actually CONTAINS the lines (proves usage is billed, not stranded as pending).
    """
    import stripe
    from apps.billing.stripe.services.stripe_service import STRIPE_API_VERSION  # applies the global pin
    assert stripe.api_version == STRIPE_API_VERSION
    stripe.api_key = os.environ["STRIPE_TEST_SECRET_KEY"]
    acct = os.environ["STRIPE_TEST_CONNECTED_ACCOUNT"]
    cust = stripe.Customer.create(stripe_account=acct, email="live-b1@example.com")
    inv = stripe.Invoice.create(stripe_account=acct, customer=cust.id, auto_advance=False)
    stripe.InvoiceItem.create(
        stripe_account=acct, customer=cust.id, invoice=inv.id,
        amount=500, currency="usd", description="Usage 2026-06",
    )
    final = stripe.Invoice.finalize_invoice(inv.id, stripe_account=acct)
    lines = (
        list(final.lines.auto_paging_iter())
        if hasattr(final.lines, "auto_paging_iter")
        else final.lines.data
    )
    assert any(l.amount == 500 for l in lines), "usage item did NOT land on the invoice"


def test_live_b2_basil_subscription_link():
    """HOW TO RUN: set UBB_STRIPE_LIVE_TEST=1, STRIPE_TEST_SECRET_KEY (a Connect
    platform test key), and STRIPE_TEST_CONNECTED_ACCOUNT (an acct_ in test mode).
    These tests SHIP SKIPPED — do not run without real Stripe test credentials.

    B2: a real Basil subscription invoice carries the sub link on
    parent.subscription_details.subscription, and _invoice_subscription_id resolves it.
    """
    import stripe
    from apps.billing.stripe.services.stripe_service import STRIPE_API_VERSION  # applies the global pin
    assert stripe.api_version == STRIPE_API_VERSION
    stripe.api_key = os.environ["STRIPE_TEST_SECRET_KEY"]
    acct = os.environ["STRIPE_TEST_CONNECTED_ACCOUNT"]
    from apps.billing.connectors.stripe.invoice_routing import _invoice_subscription_id

    cust = stripe.Customer.create(stripe_account=acct, email="live-b2@example.com")
    price = stripe.Price.create(
        stripe_account=acct,
        currency="usd",
        unit_amount=1000,
        recurring={"interval": "month"},
        product_data={"name": "Live B2 Access"},
    )
    # attach a test card payment method so the subscription activates
    pm = stripe.PaymentMethod.attach(
        "pm_card_visa", customer=cust.id, stripe_account=acct
    )
    stripe.Customer.modify(
        cust.id, stripe_account=acct,
        invoice_settings={"default_payment_method": pm.id},
    )
    sub = stripe.Subscription.create(
        stripe_account=acct, customer=cust.id, items=[{"price": price.id}]
    )
    inv = stripe.Invoice.retrieve(sub.latest_invoice, stripe_account=acct)
    assert _invoice_subscription_id(inv) == sub.id, (
        "Basil sub link did not resolve via .parent"
    )
