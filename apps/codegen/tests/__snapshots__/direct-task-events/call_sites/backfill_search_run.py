# When recording work that has already happened, one event at a time.
from ubb_integration import backfill_search_run

acknowledgement = backfill_search_run(
    customer_id=customer_id,
    idempotency_key=idempotency_key,
    task_id=task.task_id,
    searches=searches,
    recorded_at=recorded_at,
)
