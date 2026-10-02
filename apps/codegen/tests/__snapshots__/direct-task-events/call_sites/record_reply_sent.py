# After each call to your supplier. idempotency_key identifies this one
# call, and is the same if you retry it. task_id is the task_id of the
# handle the event belongs to: the work's own, or a Subtask's.
from ubb_integration import record_reply_sent

record_reply_sent(
    customer_id=customer_id,
    idempotency_key=idempotency_key,
    task_id=task_id,
    replies=replies,
)
