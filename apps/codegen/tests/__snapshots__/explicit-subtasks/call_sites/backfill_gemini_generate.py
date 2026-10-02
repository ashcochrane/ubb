# When recording work that has already happened, one event at a time.
# task_id is the task_id of the handle the event belongs to.
from ubb_integration import backfill_gemini_generate

acknowledgement = backfill_gemini_generate(
    customer_id=customer_id,
    idempotency_key=idempotency_key,
    task_id=task_id,
    response=response,
    recorded_at=recorded_at,
)
