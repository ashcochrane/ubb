from django.contrib import admin

from apps.billing.topups.models import AutoTopUpConfig


@admin.register(AutoTopUpConfig)
class AutoTopUpConfigAdmin(admin.ModelAdmin):
    list_display = (
        "customer",
        "is_enabled",
        "trigger_threshold_micros",
        "top_up_amount_micros",
    )
    list_filter = ("is_enabled",)
