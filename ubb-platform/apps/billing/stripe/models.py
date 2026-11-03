from django.db import models
from django.utils import timezone

from core.models import BaseModel

WEBHOOK_EVENT_STATUSES = [
    ("processing", "Processing"),
    ("succeeded", "Succeeded"),
    ("failed", "Failed"),
    ("skipped", "Skipped"),
]

# THE TWO STRIPE WEBHOOK RECEIVERS (R10 Stage C1b, F-17). A closed, internal
# set: each Stripe endpoint UBB registers is one receiver, verified with its
# own signing secret, and it owns the event types in its handler map. The
# same Stripe event id can legitimately reach both (Stripe delivers an event
# to every endpoint subscribed to its type), so deduplication is PER
# RECEIVER — one receiver's `skipped` row must never bury the other's
# processing, and one receiver's retryable failure is never answered
# "already processed" by the other's success. Held by the pair unique and
# the CHECK below; a third receiver is a new value here and nowhere else.
WEBHOOK_RECEIVER_BILLING = "billing"
WEBHOOK_RECEIVER_SUBSCRIPTIONS = "subscriptions"
WEBHOOK_RECEIVERS = (WEBHOOK_RECEIVER_BILLING, WEBHOOK_RECEIVER_SUBSCRIPTIONS)
WEBHOOK_RECEIVER_CHOICES = [
    (WEBHOOK_RECEIVER_BILLING, "Billing receiver (/api/v1/webhooks/stripe)"),
    (WEBHOOK_RECEIVER_SUBSCRIPTIONS,
     "Subscriptions receiver (/api/v1/subscriptions/webhooks/stripe)"),
]


class StripeWebhookEvent(BaseModel):
    """
    Tracks Stripe webhook event processing for deduplication and auditing,
    once per (receiver, Stripe event id).

    Original outcome (succeeded/failed/skipped) is never overwritten by duplicates.
    Duplicate deliveries increment duplicate_count and update last_seen_at.
    """
    receiver = models.CharField(
        max_length=20, choices=WEBHOOK_RECEIVER_CHOICES,
        default=WEBHOOK_RECEIVER_BILLING)
    stripe_event_id = models.CharField(max_length=255, db_index=True)
    event_type = models.CharField(max_length=255, db_index=True)
    status = models.CharField(max_length=20, choices=WEBHOOK_EVENT_STATUSES, default="processing")
    failure_reason = models.JSONField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    duplicate_count = models.PositiveIntegerField(default=0)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "ubb_stripe_webhook_event"
        indexes = [
            models.Index(fields=["status", "created_at"], name="idx_webhook_status_created"),
            models.Index(fields=["created_at"], name="idx_webhook_created_at"),
        ]
        constraints = [
            # Exactly-once PER RECEIVER (F-17): the dedup identity is the pair.
            models.UniqueConstraint(
                fields=["receiver", "stripe_event_id"],
                name="uq_stripe_webhook_event_receiver_event",
            ),
            # The closed set above, enforced where the row lands.
            models.CheckConstraint(
                condition=models.Q(receiver__in=sorted(WEBHOOK_RECEIVERS)),
                name="ck_stripe_webhook_event_receiver_known",
            ),
        ]

    def __str__(self):
        return f"WebhookEvent({self.receiver}/{self.stripe_event_id}: {self.status})"
