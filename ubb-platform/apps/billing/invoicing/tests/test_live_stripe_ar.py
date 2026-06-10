"""GATED live Stripe-test-mode AR payload-shape check (SKIPPED by default).

This is the only test in the Wave-5a AR suite that talks to a REAL Stripe.
It is opt-in: it does nothing unless UBB_STRIPE_LIVE_TEST is set, plus the two
Stripe test-mode credentials below. Its purpose is to assert that the REAL
Basil (2025-03-31) invoice payload exposes the exact field paths our reconcile
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
    (an acct_ in test mode). Verifies the REAL Basil (2025-03-31) invoice payload
    field paths our handlers read."""
    import stripe

    stripe.api_key = os.environ["STRIPE_TEST_SECRET_KEY"]
    acct = os.environ["STRIPE_TEST_CONNECTED_ACCOUNT"]
    from api.v1.webhooks import _invoice_subscription_id

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
    # (a subscription invoice's linkage path is exercised by creating a real sub
    # in test mode — optional extension.)
