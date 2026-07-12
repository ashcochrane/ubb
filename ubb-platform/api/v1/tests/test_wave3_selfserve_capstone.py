"""Wave 3 capstone integration test: tenant self-service config + Stripe Connect.

A REAL live-server test driving the ``ubb`` Python SDK over HTTP against a
running Django server. It proves a tenant can fully self-configure its billing
and margin levers AND connect its own Stripe account via OAuth -- with ZERO
operator/DB action, using only the SDK and the (no-auth) browser callback:

  - set/read its margin markup lever (set_markup / get_markup),
  - self-configure billing mode + enabled products (update/get_tenant_config),
  - start Stripe Connect OAuth onboarding -> the "Connect to Stripe" authorize
    URL (start_connect_onboarding), with a single-use ``state`` nonce,
  - complete the OAuth handshake exactly as the browser would: hit the no-auth
    GET /api/v1/connect/callback over HTTP (Stripe's token exchange + account
    retrieve mocked process-wide so the live-server thread sees the mocks),
  - and read the connection back via get_connect_status (account_id, onboarded).

Why live-server (not mocked httpx): mocked unit tests let real wire-level
mismatches ship undetected (a 404 on a renamed route, a response body the SDK
can't deserialize, an OAuth callback that 500s on the redirect). This exercises
the real URL routing, the real Connect OAuth state machine, and the real SDK
response contract end to end.

The process-wide ``unittest.mock.patch`` of the Stripe SDK symbols reaches the
live-server thread because live_server runs in THIS process; the Stripe calls in
``complete_oauth`` run synchronously in that server thread during the callback
request, while the patch context is still open here.
"""
import re

import httpx
import pytest
from unittest.mock import patch, MagicMock

from apps.platform.tenants.models import Tenant, TenantApiKey


@pytest.fixture
def _no_outbox_dispatch():
    """Neutralize the transactional-outbox Celery dispatch for this test.

    Under live_server there is no Celery worker/broker, so a fire-and-forget
    ``process_single_event.delay()`` on commit would raise. Patching the dispatch
    symbol to a no-op removes the broker dependency; because live_server runs in
    this same process, the patch applies to the server thread too. (Defensive
    here -- this capstone does not record usage -- but kept for parity with the
    Wave 2 capstone and to keep the harness identical.)
    """
    with patch("apps.platform.events.tasks.process_single_event.delay"):
        yield


@pytest.mark.django_db(transaction=True)
def test_wave3_selfserve_config_and_connect_via_sdk(live_server, _no_outbox_dispatch, settings):
    # Process-wide -> applies to the live-server thread too (same process).
    settings.STRIPE_CONNECT_CLIENT_ID = "ca_test"

    from ubb.client import UBBClient

    tenant = Tenant.objects.create(name="W3", products=["metering"])
    _, raw_key = TenantApiKey.create_key(tenant)

    c = UBBClient(api_key=raw_key, base_url=live_server.url)
    try:
        # 1. Margin lever: set + read back the tenant markup.
        c.set_markup(markup_percentage_micros=20_000_000)
        assert c.get_markup().markup_percentage_micros == 20_000_000

        # 2. Self-config billing mode + products (zero operator/DB action).
        c.update_tenant_config(billing_mode="prepaid", products=["metering", "billing"])
        cfg = c.get_tenant_config()
        assert cfg["billing_mode"] == "prepaid"
        assert "billing" in cfg["products"]

        # 3. Start Connect onboarding -> the "Connect to Stripe" authorize URL.
        res = c.start_connect_onboarding(return_url="https://tenant.example/done")
        assert res["authorize_url"].startswith(
            "https://connect.stripe.com/oauth/authorize")
        m = re.search(r"state=([^&]+)", res["authorize_url"])
        assert m is not None
        # token_urlsafe yields [A-Za-z0-9_-], so the query value needs no decoding.
        state = m.group(1)

        # 4. Simulate the browser completing OAuth: hit the no-auth callback over
        #    HTTP, with Stripe's token exchange + account retrieve mocked in the
        #    server thread (process-wide patch reaches it).
        with patch("apps.billing.connectors.stripe.connect.stripe.OAuth.token",
                   return_value=MagicMock(stripe_user_id="acct_W3")), \
             patch("apps.billing.connectors.stripe.connect.stripe.Account.retrieve",
                   return_value=MagicMock(charges_enabled=True)):
            cb = httpx.get(
                f"{live_server.url}/api/v1/connect/callback?code=ac_1&state={state}",
                follow_redirects=False,
            )
        assert cb.status_code in (302, 303)
        assert "connected=true" in cb.headers.get("location", "")

        # 5. Status reflects the connection (charges_enabled was set True at
        #    callback time, so this read does NOT re-hit Stripe).
        st = c.get_connect_status()
        assert st["account_id"] == "acct_W3"
        assert st["onboarded"] is True
    finally:
        c.close()
