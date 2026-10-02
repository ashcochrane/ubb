# After each call to your supplier. idempotency_key identifies this one
# call, and is the same if you retry it.
from ubb_integration import record_draft_only

record_draft_only(
    customer_id=customer_id,
    idempotency_key=idempotency_key,
    task_id=task.task_id,
)
