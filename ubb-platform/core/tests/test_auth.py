from django.test import TestCase, RequestFactory
from apps.tenants.models import Tenant, TenantApiKey
from core.auth import ApiKeyAuth


class ApiKeyAuthTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.tenant = Tenant.objects.create(name="Test")
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.auth = ApiKeyAuth()

    def test_valid_key_authenticates(self):
        request = self.factory.get("/")
        result = self.auth.authenticate(request, self.raw_key)
        self.assertIsNotNone(result)
        self.assertEqual(request.tenant.id, self.tenant.id)

    def test_invalid_key_returns_none(self):
        request = self.factory.get("/")
        result = self.auth.authenticate(request, "bad_key_here")
        self.assertIsNone(result)

    def test_revoked_key_returns_none(self):
        self.key_obj.is_active = False
        self.key_obj.save()
        request = self.factory.get("/")
        result = self.auth.authenticate(request, self.raw_key)
        self.assertIsNone(result)

    def test_inactive_tenant_returns_none(self):
        self.tenant.is_active = False
        self.tenant.save()
        request = self.factory.get("/")
        result = self.auth.authenticate(request, self.raw_key)
        self.assertIsNone(result)
