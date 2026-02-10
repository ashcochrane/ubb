from django.db import models

from core.models import BaseModel


class TenantWebhookConfig(BaseModel):
    """A tenant's webhook endpoint configuration."""

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="webhook_configs"
    )
    url = models.URLField(max_length=500)
    secret = models.CharField(max_length=255, help_text="HMAC-SHA256 signing secret")
    event_types = models.JSONField(
        default=list,
        help_text='List of event types to deliver, e.g. ["usage.recorded", "referral.reward_earned"]. Empty list = all events.',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "events"
        db_table = "ubb_tenant_webhook_config"

    def __str__(self):
        return f"WebhookConfig({self.tenant_id}: {self.url})"


class WebhookDeliveryAttempt(BaseModel):
    """Log of each webhook delivery attempt."""

    webhook_config = models.ForeignKey(
        TenantWebhookConfig, on_delete=models.CASCADE, related_name="delivery_attempts"
    )
    outbox_event = models.ForeignKey(
        "events.OutboxEvent", on_delete=models.CASCADE, related_name="webhook_deliveries"
    )
    status_code = models.IntegerField(null=True, blank=True)
    success = models.BooleanField(default=False)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        app_label = "events"
        db_table = "ubb_webhook_delivery_attempt"

    def __str__(self):
        return f"WebhookDelivery({self.webhook_config_id}: {'OK' if self.success else 'FAIL'})"
