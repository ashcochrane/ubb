from django.test import TestCase, RequestFactory

from apps.platform.tenants.models import Tenant
from core.auth import ProductAccess
from core.problems import Problem


class ProductAccessTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _make_request(self, tenant):
        request = self.factory.get("/fake")
        request.tenant = tenant
        return request

    def test_raises_feature_not_enabled_when_tenant_lacks_product(self):
        tenant = Tenant.objects.create(name="Metering Only", products=["metering"])
        request = self._make_request(tenant)
        checker = ProductAccess("billing")
        with self.assertRaises(Problem) as ctx:
            checker(request)
        self.assertEqual(ctx.exception.code, "feature_not_enabled")
        self.assertEqual(ctx.exception.status, 403)
        self.assertIn("billing", str(ctx.exception))

    def test_passes_when_tenant_has_the_product(self):
        tenant = Tenant.objects.create(
            name="Has Both", products=["metering", "billing"]
        )
        request = self._make_request(tenant)
        checker = ProductAccess("metering")
        # Should not raise
        checker(request)

    def test_passes_when_tenant_has_only_the_required_product(self):
        tenant = Tenant.objects.create(
            name="Metering Only", products=["metering"]
        )
        request = self._make_request(tenant)
        checker = ProductAccess("metering")
        # Should not raise
        checker(request)

    def test_raises_feature_not_enabled_when_tenant_has_different_product(self):
        tenant = Tenant.objects.create(
            name="Metering Only", products=["metering"]
        )
        request = self._make_request(tenant)
        checker = ProductAccess("billing")
        with self.assertRaises(Problem) as ctx:
            checker(request)
        self.assertEqual(ctx.exception.code, "feature_not_enabled")
