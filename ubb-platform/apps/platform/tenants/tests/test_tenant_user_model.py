import pytest
from django.db import IntegrityError
from apps.platform.tenants.models import Tenant, TenantUser


@pytest.mark.django_db
class TestTenantUserModel:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="Test Tenant", products=["metering"])

    def test_create_tenant_user(self):
        user = TenantUser.objects.create(
            tenant=self.tenant,
            clerk_user_id="user_abc123",
            email="admin@test.com",
            role="owner",
        )
        assert user.id is not None
        assert user.tenant == self.tenant
        assert user.clerk_user_id == "user_abc123"
        assert user.role == "owner"

    def test_clerk_user_id_unique(self):
        TenantUser.objects.create(
            tenant=self.tenant,
            clerk_user_id="user_abc123",
            email="a@test.com",
            role="owner",
        )
        with pytest.raises(IntegrityError):
            TenantUser.objects.create(
                tenant=self.tenant,
                clerk_user_id="user_abc123",
                email="b@test.com",
                role="member",
            )

    def test_default_role_is_member(self):
        user = TenantUser.objects.create(
            tenant=self.tenant,
            clerk_user_id="user_def456",
            email="member@test.com",
        )
        assert user.role == "member"

    def test_multiple_users_per_tenant(self):
        TenantUser.objects.create(
            tenant=self.tenant,
            clerk_user_id="user_1",
            email="a@test.com",
            role="owner",
        )
        TenantUser.objects.create(
            tenant=self.tenant,
            clerk_user_id="user_2",
            email="b@test.com",
            role="member",
        )
        assert self.tenant.tenant_users.count() == 2
