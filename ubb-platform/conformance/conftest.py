"""Seeding for the conformance sweep.

One tenant with every product, one admin API key, one end-customer with a
wallet and a widget JWT — enough real credentials that positive fuzzing
reaches past auth on both security schemes (``ApiKeyAuth`` and
``WidgetJWTAuth``) instead of testing the 401 path 122 times. Fresh per
test function (= per operation), so one operation's mutations can't strand
the rest of the sweep, while examples within an operation deliberately
share state — accumulated writes are extra fuzz coverage.

The root conftest's Stripe guard stays in force: a fuzzed endpoint that
reaches Stripe un-mocked raises, surfacing as a 500 in the report rather
than real network I/O. Those findings are environment artifacts, not app
defects — triage accordingly.
"""
import pytest
from django.core.signals import request_finished, request_started
from django.db import close_old_connections

from apps.billing.wallets.models import Wallet
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.widget_auth import create_widget_token


@pytest.fixture(autouse=True)
def _keep_test_connection_alive():
    """What django.test.client.ClientHandler does, for the werkzeug client.

    The sweep drives the real WSGI handler, whose request_finished signal
    runs close_old_connections — which closes the very connection holding
    pytest-django's test transaction (its autocommit is off, which reads as
    "unusable"), turning every later request into a bogus 500.
    """
    request_started.disconnect(close_old_connections)
    request_finished.disconnect(close_old_connections)
    yield
    request_started.connect(close_old_connections)
    request_finished.connect(close_old_connections)


class ConformancePrincipal:
    """The two bearer credentials, picked per operation by declared scheme."""

    def __init__(self, api_key, widget_token):
        self.api_key = api_key
        self.widget_token = widget_token

    def headers_for(self, case):
        security = case.operation.definition.raw.get("security") or []
        schemes = {name for requirement in security for name in requirement}
        token = (
            self.widget_token if "WidgetJWTAuth" in schemes else self.api_key
        )
        # Host: what django.test.Client sends — setup_test_environment()
        # allows exactly this host, independent of the ALLOWED_HOSTS env.
        return {"Authorization": f"Bearer {token}", "Host": "testserver"}


@pytest.fixture
def conformance_principal(db):
    tenant = Tenant.objects.create(
        name="Conformance",
        stripe_connected_account_id="acct_conformance",
        products=[
            "metering", "billing", "subscriptions", "referrals",
            "metering_async",
        ],
        billing_mode="prepaid",
    )
    _, raw_key = TenantApiKey.create_key(tenant, label="conformance")
    customer = Customer.objects.create(
        tenant=tenant, external_id="conformance-seed")
    Wallet.objects.create(customer=customer)
    widget_token = create_widget_token(
        tenant.widget_secret, str(customer.id), str(tenant.id))
    return ConformancePrincipal(raw_key, widget_token)
