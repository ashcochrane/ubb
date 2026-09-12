from django.apps import AppConfig


class ReferralsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.referrals"
    label = "referrals"

    def ready(self):
        from apps.platform.events.registry import handler_registry
        from apps.platform.events.schemas import UsageRecorded
        from apps.referrals.handlers import handle_usage_recorded_referrals

        handler_registry.register(
            UsageRecorded.EVENT_TYPE,
            "referrals.reward_accumulator",
            handle_usage_recorded_referrals,
            requires_product="referrals",
        )
