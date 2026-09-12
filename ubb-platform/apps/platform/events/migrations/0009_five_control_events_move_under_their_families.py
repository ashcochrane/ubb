"""Carry the five control events onto the names their families own, on the
two tables that store them (#464, slice 6 §16).

ADR-0006 §5 names an event for the state ENTERED, under the domain owner whose
lifecycle moved: a resource, or the declared control family whose own state
changed. Five names predating that rule named the MECHANISM instead — a stop
that fired, a soft floor that was crossed, the retired family word — and #222
left them alone on purpose, because a rename then *"would encode a target
state nobody has agreed."* Slice 6 agreed it: the customer-wide stop pair is a
state the CUSTOMER entered, the soft-floor pair belongs to the wallet policy
that holds the line, and the pool's threshold event to the customer spend
pool. This migration carries the rows; the same commit renames the classes.

**Why a migration is needed at all**, on `0007`'s two reasons, unchanged.
`TenantWebhookConfig.event_types` is a stored `JSONField` holding names
verbatim and `is_valid_event_selector` only runs at config-create time, so an
unmigrated row would go on existing, pass every validation it will ever face
again, and match nothing — the #75 defect. And the outbox is a work queue and
a dedup index keyed on `event_type`: `deliver_webhook` matches the name against
the migrated subscription, the handler registry dispatches on it, and the pool
service and the patrol both look for an EARLIER row under the name before
emitting another, so an unmigrated history would re-announce what was already
announced.

**The map is 1:1, and the reverse is real because a 1:1 map has one** — the
terminal-event split (`0008`) is the nearest precedent and is NOT the shape:
it fans one name out to two and its reverse is a lossy collapse. Here every
retired name has exactly one successor, so a rollback restores precisely the
rows it finds. The one qualification is stated rather than glossed: a
subscription is rewritten ELEMENT-WISE, in place, order intact, and a successor
the list already held is not added a second time — so the single degenerate
row that held both spellings of one event reverses to one entry, not two.
Delivery matches on membership, so nothing it selected changes either way.

**What is touched and what is not.** The subscriptions and the outbox rows
bearing a retired name, on every row bearing it (the outbox's dedup index and
the registry both key on the name, so a table holding two names for one event
makes every later lookup ask which — `0008` argues this at length). The
delivery attempts — the record of what a subscriber actually received — are
not touched, and a recorded BODY keeps its spelling: only the name has a
failure mode, since only the name is matched and dispatched on.

Carrying the data at all follows `0007` and `0008`: ADR-0007 §1 records #155
§5.3's exemption as spent.
"""
from django.db import migrations

#: Retired name → end-state name, all five, exactly as
#: domain-vocabulary/concepts/webhooks.yaml declares them. A second encoding of
#: names the registry already declares, necessarily so: a migration must not
#: import application code, because it has to keep working when the code has
#: moved on. The repository's rule for a second encoding is #203's — the two
#: copies exist and a contract test holds them to each other
#: (tests/contracts/test_webhook_rename_migration.py, which holds this map
#: beside `0007`'s to the same four rules).
RENAMES = {
    "stop.fired": "customer.stopped",
    "stop.cleared": "customer.stop_cleared",
    "soft_floor.crossed": "wallet_policy.soft_floor_crossed",
    "soft_floor.cleared": "wallet_policy.soft_floor_cleared",
    "budget.threshold_reached": "customer_spend_pool.threshold_reached",
}

REVERSE = {new: old for old, new in RENAMES.items()}


def _migrate_selectors(selectors, mapping):
    """A subscription's stored ``event_types`` under ``mapping``.

    Element-wise, so a mixed list keeps its order and its untouched entries —
    a subscription is a public contract, and reordering or dropping part of
    one would be a second, silent change to it. A name is added at most once:
    a list that already held the successor beside the retired name comes out
    holding it once. ``"*"`` and ``[]`` are selectors rather than names and so
    have nothing to map.
    """
    migrated = []
    for selector in selectors:
        name = mapping.get(selector, selector)
        if name not in migrated:
            migrated.append(name)
    return migrated


def _apply(apps, mapping):
    """Rewrite every stored occurrence of a name in ``mapping``.

    Only rows that actually change are written, on both tables: a data
    migration that rewrote every row would churn the whole outbox to no
    purpose. The subscriptions are selected in Python rather than by a
    containment lookup, because ``event_types`` is a ``JSONField`` — the array
    lookups that would push the filter into Postgres are ``ArrayField``'s, and
    a JSON one that silently matched nothing would make this a no-op nobody
    noticed (`0007`'s reasoning, unchanged).
    """
    OutboxEvent = apps.get_model("events", "OutboxEvent")
    for old, new in mapping.items():
        OutboxEvent.objects.filter(event_type=old).update(event_type=new)

    TenantWebhookConfig = apps.get_model("events", "TenantWebhookConfig")
    for config in TenantWebhookConfig.objects.only(
            "id", "event_types").iterator():
        migrated = _migrate_selectors(config.event_types, mapping)
        if migrated != config.event_types:
            TenantWebhookConfig.objects.filter(pk=config.pk).update(
                event_types=migrated)


def move_under_the_families(apps, schema_editor):
    _apply(apps, RENAMES)


def restore_the_mechanism_names(apps, schema_editor):
    _apply(apps, REVERSE)


class Migration(migrations.Migration):

    # `0008` for the catalogue's history, and the two frozen migrations that
    # rewrite the PAYLOADS of rows still bearing the pair's old names
    # (`work/0026` the stored cause, `gating/0014` the line's word and family)
    # — so on a graph where all three are unapplied this rename runs after
    # them and neither finds its rows already renamed out from under it.
    dependencies = [
        ("events", "0008_the_two_terminal_task_events_become_four"),
        ("work", "0026_a_stop_says_which_bound_was_reached"),
        ("gating", "0014_the_signal_ledger_keys_by_family_and_line"),
    ]

    operations = [
        migrations.RunPython(move_under_the_families,
                             restore_the_mechanism_names),
    ]
