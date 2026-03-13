import json
from unittest.mock import patch, MagicMock
import pytest
from django.test import RequestFactory
from apps.platform.tenants.models import Tenant, TenantUser
from core.clerk_auth import ClerkJWTAuth


@pytest.mark.django_db
class TestClerkJWTAuth:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        self.tenant_user = TenantUser.objects.create(
            tenant=self.tenant,
            clerk_user_id="user_clerk123",
            email="admin@test.com",
            role="owner",
        )
        self.auth = ClerkJWTAuth()
        self.factory = RequestFactory()

    @patch("core.clerk_auth.verify_clerk_token")
    def test_valid_token_returns_tenant_user(self, mock_verify):
        mock_verify.return_value = {"sub": "user_clerk123"}
        request = self.factory.get("/api/v1/platform/customers")
        result = self.auth.authenticate(request, "valid.jwt.token")
        assert result is not None
        assert request.tenant == self.tenant

    @patch("core.clerk_auth.verify_clerk_token")
    def test_invalid_token_returns_none(self, mock_verify):
        mock_verify.return_value = None
        request = self.factory.get("/api/v1/platform/customers")
        result = self.auth.authenticate(request, "bad.jwt.token")
        assert result is None

    @patch("core.clerk_auth.verify_clerk_token")
    def test_valid_token_unknown_user_returns_none(self, mock_verify):
        mock_verify.return_value = {"sub": "user_unknown"}
        request = self.factory.get("/api/v1/platform/customers")
        result = self.auth.authenticate(request, "valid.jwt.token")
        assert result is None

    @patch("core.clerk_auth.verify_clerk_token")
    def test_sets_tenant_user_on_request(self, mock_verify):
        mock_verify.return_value = {"sub": "user_clerk123"}
        request = self.factory.get("/api/v1/platform/customers")
        self.auth.authenticate(request, "valid.jwt.token")
        assert request.tenant_user == self.tenant_user
