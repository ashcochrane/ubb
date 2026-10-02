# After each call to your supplier. idempotency_key identifies this one
# call, and is the same if you retry it. task_id is the task_id of the
# handle the event belongs to: the work's own, or a Subtask's.
from ubb_integration import record_web_search

record_web_search(
    customer_id=customer_id,
    idempotency_key=idempotency_key,
    task_id=task_id,
    searches=searches,
    reported_cost=reported_cost,
)
