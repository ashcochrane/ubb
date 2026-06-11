"""Tests that confirm the autouse _stripe_guard fixture is active.

These are *meta* tests: they verify the test harness itself, not application
code.  They intentionally try to exercise paths the guard is meant to block.
"""
import pytest
import stripe
from django.conf import settings


def test_sentinel_key_values():
    """Inside a test the Stripe key must be the sentinel, not a real key."""
    assert stripe.api_key == "sk_test_sentinel"
    assert settings.STRIPE_SECRET_KEY == "sk_test_sentinel"


def test_guard_blocks_network_call():
    """A raw Stripe API call must be intercepted by the guard, not sent to the
    network.  stripe.Customer.list() goes through _APIRequestor.request_raw."""
    with pytest.raises(AssertionError, match="Un-mocked Stripe network call"):
        stripe.Customer.list()
