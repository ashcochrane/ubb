from django.db import models
from django.utils import timezone

from core.models import BaseModel


class TenantWebhookConfig(BaseModel):
    """A tenant's webhook endpoint configuration."""

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="webhook_configs"
    )
    url = models.URLField(max_length=500)
    secret = models.CharField(max_length=255, help_text="HMAC-SHA256 signing secret")
    # Two-secret overlap rotation (#83): the just-superseded secret keeps signing
    # a second `v1=` candidate until `retiring_secret_expires_at`, so a receiver
    # that has not yet cut over to the new secret verifies for the whole window.
    # Only ever ONE retiring secret is kept — rotating again replaces it.
    retiring_secret = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Previous signing secret, still emitted while its overlap "
                  "window is open. Empty once no rotation is in flight.")
    retiring_secret_expires_at = models.DateTimeField(null=True, blank=True)
    event_types = models.JSONField(
        default=list,
        help_text='Event types to deliver: ["*"] = all, [] = none, or specific types like ["usage.recorded"].',
    )
    is_active = models.BooleanField(default=True)

    def signing_secrets(self, now=None):
        """Secrets to sign a delivery with right now, in header order.

        Always the active ``secret``; plus ``retiring_secret`` while its overlap
        window is still open. The delivery path emits one ``v1=`` candidate per
        secret in ``X-UBB-Signature-V2`` — the shipped SDK verifier accepts any
        candidate, so a receiver mid-cutover verifies unchanged (#83). The
        window boundary is exclusive: at the expiry instant the retiring secret
        is already gone.
        """
        secrets = [self.secret]
        if self.retiring_secret and self.retiring_secret_expires_at:
            if self.retiring_secret_expires_at > (now or timezone.now()):
                secrets.append(self.retiring_secret)
        return secrets

    def apply_secret_rotation(self, new_secret, *, overlap, now=None):
        """Stage a two-secret rotation in memory — the caller persists it.

        The current secret becomes the retiring one for ``overlap`` (a
        ``timedelta``); ``new_secret`` becomes active. Rotating again mid-window
        simply overwrites the retiring secret with the just-superseded one, so
        at most two secrets are ever live at once (#83).
        """
        now = now or timezone.now()
        self.retiring_secret = self.secret
        self.retiring_secret_expires_at = now + overlap
        self.secret = new_secret

    class Meta:
        app_label = "events"
        db_table = "ubb_tenant_webhook_config"
        constraints = [
            # Natural identity (#63): one config per (tenant, url). Rows are
            # hard-deleted (no core soft-delete on this model), so the
            # constraint is unconditional — deleting a config frees its url.
            models.UniqueConstraint(
                fields=["tenant", "url"],
                name="uq_webhook_config_tenant_url",
            ),
        ]

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
