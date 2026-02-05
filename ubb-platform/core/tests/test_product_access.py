from django.test import TestCase, RequestFactory
from ninja.errors import HttpError

from apps.platform.tenants.models import Tenant
from core.auth import ProductAccess


class ProductAccessTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _make_request(self, tenant):
        request = self.factory.get("/fake")
        request.tenant = tenant
        return request

    def test_raises_403_when_tenant_lacks_product(self):
        tenant = Tenant.objects.create(name="No Products", products=[])
        request = self._make_request(tenant)
        checker = ProductAccess("metering")
        with self.assertRaises(HttpError) as ctx:
            checker(request)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("metering", str(ctx.exception))

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

    def test_raises_403_when_tenant_has_different_product(self):
        tenant = Tenant.objects.create(
            name="Billing Only", products=["billing"]
        )
        request = self._make_request(tenant)
        checker = ProductAccess("metering")
        with self.assertRaises(HttpError) as ctx:
            checker(request)
        self.assertEqual(ctx.exception.status_code, 403)
