from django.contrib import admin
from apps.gating.models import RiskConfig


@admin.register(RiskConfig)
class RiskConfigAdmin(admin.ModelAdmin):
    list_display = ("tenant", "max_requests_per_minute", "max_concurrent_requests")
    list_filter = ("tenant",)
