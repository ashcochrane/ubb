# When recording work that has already happened, one event at a time.
from ubb_integration import backfill_usage

acknowledgement = backfill_usage(
    customer_id=customer_id,
    idempotency_key=idempotency_key,
    task_id=task.task_id,
    recorded_at=recorded_at,
)
