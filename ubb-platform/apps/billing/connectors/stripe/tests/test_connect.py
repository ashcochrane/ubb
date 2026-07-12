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
