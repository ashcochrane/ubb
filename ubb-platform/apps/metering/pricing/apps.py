from django.apps import AppConfig


class PricingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.metering.pricing'
    label = 'pricing'

    def ready(self):
        from apps.metering.pricing.services.resolution_run import (
            replay_the_held_event)
        from apps.platform.event_types.hooks import register_replay_consumer

        # The kernel owns the remediation of a held name and never imports a
        # product (ADR-001 rule 2; the platform-hooks channel of rule 3): every
        # map and every register hands its Replay to this consumer, which
        # re-costs and re-prices the event the name arrived on from that
        # event's own moment (#473 row 1, #568) — synchronously, inside the
        # remediation's own transaction, so the decision and what it entitles
        # land together or not at all.
        register_replay_consumer(replay_the_held_event)
