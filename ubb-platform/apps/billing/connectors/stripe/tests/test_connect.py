import pytest
from django.utils import timezone
from unittest.mock import patch, MagicMock
from apps.platform.tenants.models import Tenant, ConnectOAuthState
from apps.billing.connectors.stripe import connect


@pytest.mark.django_db
def test_build_authorize_url_creates_state(settings):
    settings.STRIPE_CONNECT_CLIENT_ID = "ca_test"
    t = Tenant.objects.create(name="T", products=["metering"])
    url = connect.build_authorize_url(t, return_url="https://x/done")
    assert url.startswith("https://connect.stripe.com/oauth/authorize")
    assert "client_id=ca_test" in url and "scope=read_write" in url
    st = ConnectOAuthState.objects.get(tenant=t)
    assert st.state in url and not st.used and st.expires_at > timezone.now()


@pytest.mark.django_db
def test_build_authorize_url_requires_client_id(settings):
    settings.STRIPE_CONNECT_CLIENT_ID = ""
    t = Tenant.objects.create(name="T", products=["metering"])
    with pytest.raises(connect.ConnectError):
        connect.build_authorize_url(t, return_url="https://x/done")


@pytest.mark.django_db
def test_complete_oauth_persists_account_and_is_single_use(settings):
    settings.STRIPE_CONNECT_CLIENT_ID = "ca_test"
    t = Tenant.objects.create(name="T", products=["metering"])
    connect.build_authorize_url(t, return_url="https://x/done")
    state = ConnectOAuthState.objects.get(tenant=t).state
    with patch("apps.billing.connectors.stripe.connect.stripe.OAuth.token",
               return_value=MagicMock(stripe_user_id="acct_123")), \
         patch("apps.billing.connectors.stripe.connect.stripe.Account.retrieve",
               return_value=MagicMock(charges_enabled=True)):
        tenant = connect.complete_oauth(code="ac_1", state=state)
        tenant.refresh_from_db()
        assert tenant.stripe_connected_account_id == "acct_123"
        assert tenant.charges_enabled is True
        assert ConnectOAuthState.objects.get(state=state).used is True
        with pytest.raises(connect.ConnectError):   # replay/used -> error
            connect.complete_oauth(code="ac_1", state=state)


@pytest.mark.django_db
def test_complete_oauth_with_an_unset_live_key_is_a_connect_error_before_transport(settings):
    """Stage C1a (F-2): the token exchange and the account fetch go through the
    wrapper, which refuses an empty live key BEFORE any request is built —
    answered as ConnectError (the callback's "never a 500"), the state left
    unused. Before C1a the raw SDK calls sent the request with an empty key."""
    settings.STRIPE_CONNECT_CLIENT_ID = "ca_test"
    settings.STRIPE_SECRET_KEY = ""
    t = Tenant.objects.create(name="T", products=["metering"])
    connect.build_authorize_url(t, return_url="https://x/done")
    state = ConnectOAuthState.objects.get(tenant=t).state
    transport = MagicMock(name="request_raw")
    with patch("stripe._api_requestor._APIRequestor.request_raw", transport), \
         patch("apps.billing.connectors.stripe.connect.stripe.OAuth.token") as token:
        with pytest.raises(connect.ConnectError):
            connect.complete_oauth(code="ac_1", state=state)
    token.assert_not_called()
    transport.assert_not_called()
    t.refresh_from_db()
    assert t.stripe_connected_account_id == ""
    assert ConnectOAuthState.objects.get(state=state).used is False


@pytest.mark.django_db
def test_the_account_fetch_after_the_exchange_is_refused_by_the_wrapper_without_a_key(settings):
    """F-2, the second Connect site (Account.retrieve after the token exchange):
    the REAL wrapper refuses an empty live key before any request is built.
    The token exchange is answered by a stub for this one call so the flow
    reaches the account fetch; the fetch itself runs through the genuine
    ``stripe_call`` with the empty key, is refused, and degrades to
    ``charges_enabled=False`` with the account id persisted — never transport."""
    from apps.billing.stripe.services import stripe_service
    settings.STRIPE_CONNECT_CLIENT_ID = "ca_test"
    settings.STRIPE_SECRET_KEY = ""
    t = Tenant.objects.create(name="T", products=["metering"])
    connect.build_authorize_url(t, return_url="https://x/done")
    state = ConnectOAuthState.objects.get(tenant=t).state
    seen = []

    def wrapper_with_a_stubbed_exchange(fn, *, api_key, **kwargs):
        seen.append((getattr(fn, "__qualname__", ""), api_key))
        if getattr(fn, "__qualname__", "") == "OAuth.token":
            return MagicMock(stripe_user_id="acct_after_exchange")
        return stripe_service.stripe_call(fn, api_key=api_key, **kwargs)

    transport = MagicMock(name="request_raw")
    with patch("stripe._api_requestor._APIRequestor.request_raw", transport), \
         patch("apps.billing.connectors.stripe.connect.stripe_call",
               side_effect=wrapper_with_a_stubbed_exchange):
        tenant = connect.complete_oauth(code="ac_1", state=state)
    transport.assert_not_called()
    assert [name for name, _ in seen] == ["OAuth.token", "Account.retrieve"]
    assert all(key == "" for _, key in seen)
    tenant.refresh_from_db()
    assert tenant.stripe_connected_account_id == "acct_after_exchange"
    assert tenant.charges_enabled is False


@pytest.mark.django_db
def test_an_oauth_refusal_from_stripe_is_a_connect_error_not_a_500(settings):
    """A used or expired authorization code is Stripe's own OAuthError; the
    wrapper maps it to a fatal and the flow answers ConnectError."""
    import stripe
    settings.STRIPE_CONNECT_CLIENT_ID = "ca_test"
    t = Tenant.objects.create(name="T", products=["metering"])
    connect.build_authorize_url(t, return_url="https://x/done")
    state = ConnectOAuthState.objects.get(tenant=t).state
    with patch("apps.billing.connectors.stripe.connect.stripe.OAuth.token",
               side_effect=stripe.oauth_error.InvalidGrantError(
                   "invalid_grant", "Authorization code already used")):
        with pytest.raises(connect.ConnectError):
            connect.complete_oauth(code="ac_used", state=state)
    t.refresh_from_db()
    assert t.stripe_connected_account_id == ""
