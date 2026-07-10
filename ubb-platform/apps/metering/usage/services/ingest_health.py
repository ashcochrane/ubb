"""Ingest-pipeline health metrics — the ONE source of truth for both the ops
endpoint (GET /api/v1/metering/ops/ingest-health) and the
monitor_ingest_health alert task (spec §3). Read-only; every query rides
idx_rawingest_claim (status, created_at)."""
from django.utils import timezone


def ingest_health(tenant_id=None):
    from apps.metering.usage.models import RawIngestEvent
    qs = RawIngestEvent.objects.all()
    if tenant_id is not None:
        qs = qs.filter(tenant_id=tenant_id)
    pending = qs.filter(status="pending")
    oldest = (pending.order_by("created_at")
              .values_list("created_at", flat=True).first())
    now = timezone.now()
    return {
        "pending_count": pending.count(),
        "oldest_pending_age_seconds": (
            (now - oldest).total_seconds() if oldest else 0.0),
        "retrying_count": pending.filter(attempts__gt=0).count(),
        "failed_count": qs.filter(status="failed").count(),
        "generated_at": now.isoformat(),
    }
