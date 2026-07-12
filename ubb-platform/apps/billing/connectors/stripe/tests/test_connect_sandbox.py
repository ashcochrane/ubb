"""F4.4: Connect OAuth in sandbox (Stripe TEST) mode."""
from unittest.mock import MagicMock, patch

import pytest

from apps.billing.connectors.stripe import connect
from apps.platform.tenants.models import ConnectOAuthState, Tenant
from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox


@pytest.fixture
def live_and_sandbox(db):
    live = Tenant.objects.create(name="L", products=["metering"])
    return live, get_or_create_sandbox(live)


@pytest.mark.django_db
def test_build_authorize_url_sandbox_requires_test_client_id(settings, live_and_sandbox):
    settings.STRIPE_CONNECT_CLIENT_ID = "ca_live"
    settings.STRIPE_CONNECT_TEST_CLIENT_ID = ""
    _, sandbox = live_and_sandbox
    with pytest.raises(connect.ConnectError, match="STRIPE_CONNECT_TEST_CLIENT_ID"):
        connect.build_authorize_url(sandbox, return_url="https://x/done")


@pytest.mark.django_db
def test_build_authorize_url_sandbox_uses_test_client_id(settings, live_and_sandbox):
    settings.STRIPE_CONNECT_CLIENT_ID = "ca_live"
    settings.STRIPE_CONNECT_TEST_CLIENT_ID = "ca_test_123"
    live, sandbox = live_and_sandbox
    sandbox_url = connect.build_authorize_url(sandbox, return_url="https://x/done")
    live_url = connect.build_authorize_url(live, return_url="https://x/done")
    assert "client_id=ca_test_123" in sandbox_url
    assert "client_id=ca_live" in live_url


@pytest.mark.django_db
def test_complete_oauth_sandbox_uses_the_test_key(settings, live_and_sandbox):
    settings.STRIPE_CONNECT_TEST_CLIENT_ID = "ca_test_123"
    settings.STRIPE_TEST_SECRET_KEY = "sk_test_sandbox"
    _, sandbox = live_and_sandbox
    connect.build_authorize_url(sandbox, return_url="https://x/done")
    state = ConnectOAuthState.objects.get(tenant=sandbox).state
    with patch("apps.billing.connectors.stripe.connect.stripe.OAuth.token",
               return_value=MagicMock(stripe_user_id="acct_123")) as token, \
         patch("apps.billing.connectors.stripe.connect.stripe.Account.retrieve",
               return_value=MagicMock(charges_enabled=True)) as retrieve:
        tenant = connect.complete_oauth(code="ac_1", state=state)
    assert token.call_args.kwargs["api_key"] == "sk_test_sandbox"
    assert retrieve.call_args.kwargs["api_key"] == "sk_test_sandbox"
    tenant.refresh_from_db()
    assert tenant.id == sandbox.id
    assert tenant.stripe_connected_account_id == "acct_123"
    assert tenant.charges_enabled is True


@pytest.mark.django_db
def test_complete_oauth_live_uses_platform_key(settings, live_and_sandbox):
    settings.STRIPE_CONNECT_CLIENT_ID = "ca_live"
    live, _ = live_and_sandbox
    connect.build_authorize_url(live, return_url="https://x/done")
    state = ConnectOAuthState.objects.get(tenant=live).state
    with patch("apps.billing.connectors.stripe.connect.stripe.OAuth.token",
               return_value=MagicMock(stripe_user_id="acct_123")) as token, \
         patch("apps.billing.connectors.stripe.connect.stripe.Account.retrieve",
               return_value=MagicMock(charges_enabled=True)):
        connect.complete_oauth(code="ac_1", state=state)
    assert token.call_args.kwargs["api_key"] == settings.STRIPE_SECRET_KEY


@pytest.mark.django_db
def test_complete_oauth_sandbox_without_test_key_is_connect_error(settings, live_and_sandbox):
    settings.STRIPE_CONNECT_TEST_CLIENT_ID = "ca_test_123"
    settings.STRIPE_TEST_SECRET_KEY = ""
    _, sandbox = live_and_sandbox
    connect.build_authorize_url(sandbox, return_url="https://x/done")
    state = ConnectOAuthState.objects.get(tenant=sandbox).state
    with patch("apps.billing.connectors.stripe.connect.stripe.OAuth.token") as token:
        with pytest.raises(connect.ConnectError):
            connect.complete_oauth(code="ac_1", state=state)
    token.assert_not_called()  # refused BEFORE any Stripe call
