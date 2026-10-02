# After each call to your supplier. idempotency_key identifies this one
# call, and is the same if you retry it.
from ubb_integration import record_chat_completion

record_chat_completion(
    customer_id=customer_id,
    idempotency_key=idempotency_key,
    task_id=task.task_id,
    response=response,
)
