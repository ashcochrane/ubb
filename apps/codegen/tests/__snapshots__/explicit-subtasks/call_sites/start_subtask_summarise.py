# Only where your code creates this Subtask, inside the work it is part
# of. Pass its task_id when recording to attribute an event to it.
from ubb_integration import start_subtask_summarise

with start_subtask_summarise(
    customer_id=customer_id,
    idempotency_key=idempotency_key,
    parent_task_id=task.task_id,
    phase=phase,
) as subtask:
    ...
