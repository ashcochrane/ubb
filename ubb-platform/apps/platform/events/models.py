from django.db import models

from core.models import BaseModel


OUTBOX_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("processing", "Processing"),
    ("processed", "Processed"),
    ("failed", "Failed"),
    ("skipped", "Skipped"),
]


class OutboxEvent(BaseModel):
    event_type = models.CharField(max_length=100, db_index=True)
    payload = models.JSONField()
    tenant_id = models.UUIDField(db_index=True)

    status = models.CharField(
        max_length=20, choices=OUTBOX_STATUS_CHOICES, default="pending", db_index=True
    )
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=5)
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_error = models.TextField(blank=True, default="")
    processed_at = models.DateTimeField(null=True, blank=True)
    correlation_id = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        db_table = "ubb_outbox_event"
        indexes = [
            models.Index(fields=["status", "next_retry_at"], name="idx_outbox_status_retry"),
            models.Index(fields=["status", "created_at"], name="idx_outbox_status_created"),
            models.Index(
                fields=["tenant_id", "event_type", "created_at"],
                name="idx_outbox_tenant_type_created",
            ),
        ]

    def __str__(self):
        return f"OutboxEvent({self.event_type} [{self.status}])"


class HandlerCheckpoint(BaseModel):
    outbox_event = models.ForeignKey(
        OutboxEvent, on_delete=models.CASCADE, related_name="checkpoints"
    )
    handler_name = models.CharField(max_length=100)

    class Meta:
        db_table = "ubb_handler_checkpoint"
        constraints = [
            models.UniqueConstraint(
                fields=["outbox_event", "handler_name"],
                name="uq_checkpoint_event_handler",
            ),
        ]

    def __str__(self):
        return f"HandlerCheckpoint({self.handler_name} for {self.outbox_event_id})"
