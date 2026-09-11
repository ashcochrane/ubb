"""The stored stop cause is migrated once — key and values (#457, slice 6 §8,
ADR-0007 §1).

A unit of work carried its stop cause under a key spelled for a kill
(`kill_reason`) that had carried expiries too since slice 5, under values that
named the mechanism's effect rather than the bound that was reached: two
ceiling words that differed only by altitude, one customer-wide word for two
controls, this app's own spelling for the absolute deadline's stop, and the
pre-registry spelling of the silence window's. The registry's `reason_code`
now names all seven bounds (`apps/platform/work/reasons.py` holds them by
reference), and this migration moves every stored row onto them so that no
reader ever needs a map from a retired spelling:

  * the unit's metadata key becomes `reason_code` on every row holding it;
  * the retired values under it are rewritten — the two ceiling words to
    `task_cogs_ceiling`, the pre-registry silence spelling to
    `silence_window`, the absolute deadline's module value to
    `absolute_deadline`;
  * the same values are rewritten on outbox payloads, under both keys a
    payload has spelled the cause with (`reason_code` on the four terminal
    events since the split, `reason` on the rows that predate it and on the
    customer stop pair);
  * the customer-wide word is SPLIT: `hard_floor` where the owner's tenant is
    prepaid and `customer_spend_pool` where it is postpaid;
  * the two monetary suspension words become the same two stop words, on the
    customer's suspension column and on the `customer.suspended` payloads
    that carried them — because the thing that suspended the customer is the
    stop that opened the episode, and it is one word (§9).

**⚠ THE SPLIT IS ROUTED BY THE OWNER'S TENANT BILLING MODE, WHICH IS THE ONLY
FACT A HISTORICAL ROW CAN ANSWER WITH.** The lane that produced a customer-wide
stop was chosen by mode — the postpaid lane debits the pool, every other mode
debits a wallet (`LiveCounter.debit` mirrors the drawdown branch for anything
that is not postpaid) — so the row's tenant says which control opened the
episode, and nothing else on the row does. The producers fork the same way
until the signal ledger carries its own line (`reasons.customer_stop_reason`,
ticket 7 of the slice), and this module spells the fork rather than importing
it because a migration must keep working when the code has moved on.

**⚠ THIS DEPARTS FROM #412's PRECEDENT, AND SAYS WHY.** #412 changed one string
on an open set mid-slice and chose to add the new spelling beside the old on
every reader rather than migrate — `customer_floor`'s posture, and the terminal
event split (`events/0008`) left its payload bodies as recorded on the same
argument. This slice retires the whole stored vocabulary at once, and
ADR-0007 §1's rule is that a rename carries its data. After this runs no
stored row holds a retired spelling, so there is no read-side legacy map: the
published verdicts list drops `customer_floor` (no producer, no stored row)
and the pre-registry silence spelling, and every reader compares by constant
identity. `events/0008`'s own routing constant (`REAPER_REASONS`) is frozen
history and is not edited — it names the spellings as they stood when that
migration ran, which this one has since rewritten. Nothing is deployed; the
rows this touches exist on developer machines and in fixtures only.

**Two data stores are deliberately NOT touched.** `Posting.stop_context` is
immutable with its row and the metering glossary's rule for it stands — a
reader keys on scope and intent, never on a literal — so the retired report
buckets those entries by scope. The signal ledger's `reason` column is ticket
7's, which gives the ledger its own line and unique key.

**The reverse is provided and is LOSSY in three named places**, stated rather
than pretended: the pre-registry silence spelling does not come back (it was
one word's older spelling and the current word is what the reverted code
reads); contained work that expired with its parent goes back to the silence
window, so the two rows of one expired tree disagree again; and a suspension
recorded as a stop word goes back to the suspension word the reverted code
clears on. The ceiling word goes back to its altitude's spelling off the row
(`parent_id` on a unit, `subtask_id` on a payload), and the two customer-wide
words collapse back onto the one, which round-trips exactly because the
forward is a function of the tenant's mode.
"""
from django.db import migrations

#: The key the cause was stored under, and the key it is stored under now.
RETIRED_CAUSE_KEY = "kill_reason"
CAUSE_KEY = "reason_code"

#: The keys an outbox payload has spelled a cause under: the terminal events'
#: since the split (`events/0008`), and the older bare `reason` on the rows
#: that predate it and on the customer stop pair and the suspension event.
PAYLOAD_CAUSE_KEYS = (CAUSE_KEY, "reason")

#: A second encoding of names the registry declares, necessarily so: a
#: migration must not import application code. `apps/platform/work/tests/
#: test_the_stored_stop_cause_is_migrated_once.py` holds every value below to
#: the constants.
CEILING = "task_cogs_ceiling"
HARD_FLOOR = "hard_floor"
CUSTOMER_SPEND_POOL = "customer_spend_pool"
ABSOLUTE_DEADLINE = "absolute_deadline"
SILENCE_WINDOW = "silence_window"
PARENT_EXPIRED = "parent_expired"

#: Retired spelling -> current word, wherever the spelling is stored. The two
#: ceiling words collapse onto one (altitude travels as scope); the two
#: monetary suspension words become the two stop words they always meant.
BY_VALUE = {
    "task_limit": CEILING,
    "subtask_limit": CEILING,
    "stale": SILENCE_WINDOW,
    "stale_max_age": ABSOLUTE_DEADLINE,
    "min_balance_exceeded": HARD_FLOOR,
    "budget_exceeded": CUSTOMER_SPEND_POOL,
}

#: The one word two controls shared, split by the owner's tenant billing mode.
CUSTOMER_WIDE = "customer_wide_stop"
POSTPAID = "postpaid"

#: Everything this migration rewrites.
RETIRED = frozenset(BY_VALUE) | {CUSTOMER_WIDE}


def current_word(value, billing_mode):
    """The current word for a stored spelling, or the value itself where it is
    not a retired one."""
    if value == CUSTOMER_WIDE:
        return CUSTOMER_SPEND_POOL if billing_mode == POSTPAID else HARD_FLOOR
    return BY_VALUE.get(value, value)


def retired_word(value, *, is_contained, on_a_suspension):
    """The spelling the reverted code would read, off the row's own facts."""
    if value == CEILING:
        return "subtask_limit" if is_contained else "task_limit"
    if value == ABSOLUTE_DEADLINE:
        return "stale_max_age"
    if value == PARENT_EXPIRED:
        return SILENCE_WINDOW
    if value in (HARD_FLOOR, CUSTOMER_SPEND_POOL):
        if on_a_suspension:
            return ("min_balance_exceeded" if value == HARD_FLOOR
                    else "budget_exceeded")
        return CUSTOMER_WIDE
    return value


def _modes(apps):
    Tenant = apps.get_model("tenants", "Tenant")
    return dict(Tenant.objects.values_list("id", "billing_mode"))


def _move_the_stored_cause(apps, schema_editor):
    """Forward: the key on every unit row holding it, then the values
    everywhere they are stored."""
    Task = apps.get_model("work", "Task")
    OutboxEvent = apps.get_model("events", "OutboxEvent")
    Customer = apps.get_model("customers", "Customer")
    modes = _modes(apps)

    # Only rows that actually change are written — a data migration that
    # rewrote every row would churn a whole table to no purpose. Each filter
    # names exactly the rows the statement after it changes.
    for task in (Task.objects.filter(metadata__has_key=RETIRED_CAUSE_KEY)
                 .only("id", "tenant_id", "metadata").iterator()):
        metadata = dict(task.metadata)
        value = metadata.pop(RETIRED_CAUSE_KEY)
        metadata[CAUSE_KEY] = current_word(value, modes.get(task.tenant_id))
        Task.objects.filter(pk=task.pk).update(metadata=metadata)

    for key in PAYLOAD_CAUSE_KEYS:
        for row in (OutboxEvent.objects
                    .filter(**{f"payload__{key}__in": sorted(RETIRED)})
                    .only("id", "tenant_id", "payload").iterator()):
            payload = {**row.payload,
                       key: current_word(row.payload[key],
                                         modes.get(row.tenant_id))}
            OutboxEvent.objects.filter(pk=row.pk).update(payload=payload)

    for retired, current in BY_VALUE.items():
        Customer.objects.filter(suspension_reason=retired).update(
            suspension_reason=current)


def _put_the_stored_cause_back(apps, schema_editor):
    """Reverse, lossily — the module docstring names the three places."""
    Task = apps.get_model("work", "Task")
    OutboxEvent = apps.get_model("events", "OutboxEvent")
    Customer = apps.get_model("customers", "Customer")

    for task in (Task.objects.filter(metadata__has_key=CAUSE_KEY)
                 .only("id", "parent_id", "metadata").iterator()):
        metadata = dict(task.metadata)
        value = metadata.pop(CAUSE_KEY)
        metadata[RETIRED_CAUSE_KEY] = retired_word(
            value, is_contained=task.parent_id is not None,
            on_a_suspension=False)
        Task.objects.filter(pk=task.pk).update(metadata=metadata)

    current = sorted({*BY_VALUE.values(), PARENT_EXPIRED})
    for key in PAYLOAD_CAUSE_KEYS:
        for row in (OutboxEvent.objects
                    .filter(**{f"payload__{key}__in": current})
                    .only("id", "event_type", "payload").iterator()):
            payload = {**row.payload, key: retired_word(
                row.payload[key],
                is_contained=bool(row.payload.get("subtask_id")),
                on_a_suspension=row.event_type == "customer.suspended")}
            OutboxEvent.objects.filter(pk=row.pk).update(payload=payload)

    for retired, current_word_ in BY_VALUE.items():
        if current_word_ in (HARD_FLOOR, CUSTOMER_SPEND_POOL):
            Customer.objects.filter(suspension_reason=current_word_).update(
                suspension_reason=retired)


class Migration(migrations.Migration):

    dependencies = [
        ("work", "0025_the_index_that_counted_running_work_per_owner_is_dropped"),
        ("events", "0008_the_two_terminal_task_events_become_four"),
        ("customers", "0014_customer_suspension_reason"),
        ("tenants", "0026_the_default_ceilings_for_undeclared_work_come_to_the_kernel"),
    ]

    operations = [
        migrations.RunPython(_move_the_stored_cause,
                             _put_the_stored_cause_back),
    ]
