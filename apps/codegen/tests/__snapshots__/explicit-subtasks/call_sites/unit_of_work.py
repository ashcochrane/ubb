# Where the piece of work begins. Everything it does goes inside.
from ubb_integration import unit_of_work

with unit_of_work(
    customer_id=customer_id,
    idempotency_key=idempotency_key,
    environment=environment,
) as task:
    ...
