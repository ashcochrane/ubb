# When recording work that has already happened, one event at a time.
from ubb_integration import backfill_chat_completion

acknowledgement = backfill_chat_completion(
    customer_id=customer_id,
    idempotency_key=idempotency_key,
    task_id=task.task_id,
    response=response,
    recorded_at=recorded_at,
)
