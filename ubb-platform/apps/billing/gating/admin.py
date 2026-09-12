from django.contrib import admin
from apps.billing.gating.models import RiskConfig


@admin.register(RiskConfig)
class RiskConfigAdmin(admin.ModelAdmin):
    list_display = ("tenant", "gate_fail_closed")
    list_filter = ("tenant",)
