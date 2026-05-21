"""Verify dual auth: both Clerk JWT (dashboard) and API key (machine) are
accepted on all tenant-facing APIs."""
import json
import pytest
from unittest.mock import patch
from django.test import Client
from apps.platform.tenants.models import Tenant, TenantApiKey, TenantUser


@pytest.mark.django_db
class TestDualAuthOnPlatformAPI:
    def setup_method(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(name="DualAuth Test", products=["metering"])
        _, self.api_key = TenantApiKey.create_key(tenant=self.tenant, label="test")
        self.tenant_user = TenantUser.objects.create(
            tenant=self.tenant,
            clerk_user_id="user_dual_test",
            email="dual@test.com",
            role="owner",
        )

    def test_api_key_auth_works_on_platform_create(self):
        resp = self.http_client.post(
            "/api/v1/platform/customers",
            data=json.dumps({"external_id": "apikey_test"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.api_key}",
        )
        assert resp.status_code == 201

    @patch("core.clerk_auth.verify_clerk_token")
    def test_clerk_jwt_works_on_platform_create(self, mock_verify):
        mock_verify.return_value = {"sub": "user_dual_test"}
        resp = self.http_client.post(
            "/api/v1/platform/customers",
            data=json.dumps({"external_id": "clerk_test"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer fake.jwt.token",
        )
        assert resp.status_code == 201

    def test_no_auth_returns_401(self):
        resp = self.http_client.post(
            "/api/v1/platform/customers",
            data=json.dumps({"external_id": "noauth"}),
            content_type="application/json",
        )
        assert resp.status_code == 401


@pytest.mark.django_db
class TestClerkJWTAcceptedOnProductAPIs:
    def setup_method(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
        )
        TenantUser.objects.create(
            tenant=self.tenant,
            clerk_user_id="user_dashboard",
            email="dashboard@test.com",
        )

    @patch("core.clerk_auth.verify_clerk_token")
    def test_clerk_jwt_accepted_on_metering_api(self, mock_verify):
        mock_verify.return_value = {"sub": "user_dashboard"}
        resp = self.http_client.get(
            "/api/v1/metering/pricing/cards",
            HTTP_AUTHORIZATION="Bearer fake.jwt.token",
        )
        assert resp.status_code == 200

    @patch("core.clerk_auth.verify_clerk_token")
    def test_clerk_jwt_accepted_on_billing_api(self, mock_verify):
        mock_verify.return_value = {"sub": "user_dashboard"}
        resp = self.http_client.get(
            "/api/v1/billing/customers/00000000-0000-0000-0000-000000000000/balance",
            HTTP_AUTHORIZATION="Bearer fake.jwt.token",
        )
        # Auth succeeded — endpoint returns 404 for missing customer, not 401
        assert resp.status_code == 404

    def test_no_auth_returns_401_on_metering(self):
        resp = self.http_client.get("/api/v1/metering/pricing/cards")
        assert resp.status_code == 401
