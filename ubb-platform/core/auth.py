from django.utils import timezone
from ninja.errors import HttpError
from ninja.security import HttpBearer

from apps.platform.tenants.models import TenantApiKey


class ApiKeyAuth(HttpBearer):
    def authenticate(self, request, token):
        key_obj = TenantApiKey.verify_key(token)
        if key_obj is None:
            return None
        request.tenant = key_obj.tenant
        TenantApiKey.objects.filter(pk=key_obj.pk).update(last_used_at=timezone.now())
        return key_obj


class ProductAccess:
    """Dependency that checks tenant has access to a specific product."""

    def __init__(self, required_product):
        self.required_product = required_product

    def __call__(self, request):
        if self.required_product not in request.tenant.products:
            raise HttpError(
                403,
                f"Tenant does not have access to {self.required_product}",
            )
