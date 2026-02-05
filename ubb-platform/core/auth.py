from django.utils import timezone
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
