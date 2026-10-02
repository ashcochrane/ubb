# When recording work that has already happened, one event at a time.
from ubb_integration import backfill_draft_only

acknowledgement = backfill_draft_only(
    customer_id=customer_id,
    idempotency_key=idempotency_key,
    task_id=task.task_id,
    recorded_at=recorded_at,
)
