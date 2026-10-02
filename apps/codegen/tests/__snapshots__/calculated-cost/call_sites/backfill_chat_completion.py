# When recording work that has already happened, one event at a time.
# task_id is the task_id of the handle the event belongs to.
from ubb_integration import backfill_chat_completion

acknowledgement = backfill_chat_completion(
    customer_id=customer_id,
    idempotency_key=idempotency_key,
    task_id=task_id,
    response=response,
    searches=searches,
    recorded_at=recorded_at,
)
