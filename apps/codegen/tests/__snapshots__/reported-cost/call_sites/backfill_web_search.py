# When recording work that has already happened, one event at a time.
from ubb_integration import backfill_web_search

acknowledgement = backfill_web_search(
    customer_id=customer_id,
    idempotency_key=idempotency_key,
    task_id=task.task_id,
    searches=searches,
    reported_cost=reported_cost,
    recorded_at=recorded_at,
)
