# Auto-topup charging task has been moved to apps.billing.stripe.tasks
# as part of the product isolation cleanup.
# Metering no longer imports from billing.

import logging

from celery import shared_task
from django.db import transaction

logger = logging.getLogger("ubb.metering")

# Poison-payload ceiling: after this many failed settle attempts a raw is
# marked "failed" and its hold (if any) released — an unsettleable billable
# event is an incident, not a log line (loud logger.error, not a silent drop).
MAX_SETTLE_ATTEMPTS = 5


@shared_task(queue="ubb_metering")
def settle_raw_events(batch_size=200):
    """Settle accepted async-ingest raws into exact UsageEvents (Task 6).

    Claim: one short transaction SELECTs (never mutates) up to `batch_size`
    "pending" rows via select_for_update(skip_locked=True), oldest first, and
    collects their ids — so a genuinely concurrent claim from another
    invocation of this task skips whatever this one is holding. Settlement:
    each claimed raw is settled in its OWN transaction (UsageService.settle_raw
    re-locks that specific row and rechecks status, so one poison event's
    rollback — or a second invocation racing this one — can never roll back
    or double-process a sibling). Failure bookkeeping (attempts/failed) lives
    here, mirroring apps.platform.events.tasks.process_single_event's
    retry_count pattern: settle_raw itself only ever raises for a genuinely
    unsettleable ("poison") payload — an IntegrityError (duplicate) is handled
    internally and never propagates.

    Re-enqueues itself when the claim drained a full batch (more may be
    waiting); the 10s beat entry is the straggler sweeper for everything else
    (a lost on_commit dispatch, a crashed worker mid-batch).
    """
    from apps.billing.queries import release_ingest_hold
    from apps.metering.usage.models import RawIngestEvent
    from apps.metering.usage.services.usage_service import UsageService, _parse_effective_at

    with transaction.atomic():
        ids = list(
            RawIngestEvent.objects.select_for_update(skip_locked=True)
            .filter(status="pending")
            .order_by("created_at")
            .values_list("id", flat=True)[:batch_size]
        )

    settled = 0
    for raw_id in ids:
        try:
            raw = RawIngestEvent.objects.select_related("tenant", "customer").get(id=raw_id)
        except RawIngestEvent.DoesNotExist:
            continue  # claimed then deleted out from under us; nothing to do
        try:
            UsageService.settle_raw(raw)
            settled += 1
        except Exception:
            logger.exception("settle_raw.attempt_failed", extra={"data": {
                "raw_id": str(raw_id), "tenant_id": str(raw.tenant_id)}})
            # Failure bookkeeping under the ROW LOCK: the failed settle's
            # rollback released the claim-time lock, so a concurrent
            # invocation can be racing us on this same still-"pending" row.
            # Re-lock, re-check status, and increment attempts atomically
            # (an unlocked read-modify-write here would lose increments);
            # only the worker whose pending -> failed flip wins may release
            # the hold, post-commit — a double release would over-credit the
            # live gate (over-permissive, the worst failure direction).
            poisoned = None  # the locked row, iff THIS worker flipped it
            with transaction.atomic():
                locked = RawIngestEvent.objects.select_for_update().filter(
                    id=raw_id).first()
                if locked is None or locked.status != "pending":
                    continue  # deleted, or a racer already resolved this raw
                locked.attempts += 1
                if locked.attempts >= MAX_SETTLE_ATTEMPTS:
                    locked.status = "failed"
                    locked.save(update_fields=["attempts", "status", "updated_at"])
                    poisoned = locked
                else:
                    locked.save(update_fields=["attempts", "updated_at"])
            if poisoned is not None:
                if poisoned.held:
                    release_ingest_hold(poisoned.billing_owner_id, raw.tenant,
                                        str(poisoned.run_id) if poisoned.run_id else None,
                                        poisoned.estimate_micros,
                                        effective_at=_parse_effective_at(poisoned.payload))
                logger.error("settle_raw.poisoned", extra={"data": {
                    "raw_id": str(raw_id), "tenant_id": str(raw.tenant_id),
                    "attempts": poisoned.attempts}})

    if len(ids) >= batch_size:
        settle_raw_events.delay(batch_size=batch_size)
    return settled
