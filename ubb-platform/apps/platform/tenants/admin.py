from django.contrib import admin

from apps.platform.tenants.models import Tenant, TenantApiKey


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "platform_fee_percentage", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(TenantApiKey)
class TenantApiKeyAdmin(admin.ModelAdmin):
    list_display = ("key_prefix", "tenant", "label", "is_active", "last_used_at")
    list_filter = ("is_active",)
    search_fields = ("label", "key_prefix")
