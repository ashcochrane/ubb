# When recording work that has already happened, one event at a time.
from ubb_integration import backfill_reply_sent

acknowledgement = backfill_reply_sent(
    customer_id=customer_id,
    idempotency_key=idempotency_key,
    task_id=task.task_id,
    replies=replies,
    recorded_at=recorded_at,
)
