"""Carry the two overloaded terminal Task events onto their four successors,
on the two tables that store them (#140 §4.3, ratified in full by #154 §5.3).

ADR-0006 §5 names an event for the state ENTERED. `killed` and `expired` are
two different claims about a unit of work — *UBB stopped this on a spend
signal* against *nobody ever told UBB how it ended* — and one name could not
say which, so an operator subscribed to spend incidents was paged because a
worker crashed. #222 renamed thirteen event names and said outright why this
pair was excluded: *"The two Task events become TWO events each in slice 5
(#140 §4.3) … so a 1:1 rename now would encode a target state nobody has
agreed."* That target state is agreed and built, and this carries the rows.

**Why both tables move**, on the two reasons `0007` established one file over.
`TenantWebhookConfig.event_types` is a stored `JSONField` and
`is_valid_event_selector` only runs at config-create time, so an unmigrated row
*"would go on existing, pass every validation it will ever face again, and
match nothing"* — the #75 defect that hid an event from subscribers while the
delivery path emitted it. And the outbox is a work queue with a dedup index
keyed on the name, so a pending row under a name nothing registers drains to no
handler.

**⚠ THE TWO TABLES TAKE TWO DIFFERENT RULES, because they are answering two
different questions.** `0007` could use one map for both; a one-to-two map
cannot.

**(a) Subscriptions FAN OUT — one name becomes both successors.** A subscriber
who asked for the retired name wanted to hear about work terminating, and after
the split one name delivers half of that. So the retired entry is replaced by
both successors IN PLACE, keeping the list's order and its untouched entries: a
subscription is a public contract, and reordering or dropping part of one would
be a second, silent change to it. A successor already in the list is not added
twice — `_migrate_selectors` says what that de-duplication costs in each
direction, which is not the same thing forwards and backwards.

**(b) Outbox rows ROUTE — each row to exactly ONE successor.** A pending row is
one past event about one unit of work; sending it to both would double-deliver
a stop that happened once. So each row is routed by evidence it already
carries, its own recorded reason:

    a reaper's reason (every spelling — see REAPER_REASONS)  ->  *.expired
    every other reason — the ceilings, the customer-wide     ->  *.killed
      stop, the parent cascade
    absent or unrecognised                                   ->  *.killed

**⚠ THE DEFAULT IS STATED, NOT ACCIDENTAL, and it is why the two statements run
in this order.** `expired` is the strictly narrower claim — *nobody ever told
UBB how this ended* — and it is assertable only from a reaper's reason.
Asserting the narrow claim without evidence is the worse error of the two: it
would tell a subscriber a worker went quiet when UBB had in fact stopped the
work on a ceiling. So the reaper rows are moved first, on evidence, and
everything still bearing the retired name afterwards — including a row whose
payload records no reason at all — falls to `*.killed`, the claim the retired
event is documented as making.

**⚠ THE RECORDED BODY IS LEFT EXACTLY AS IT WAS RECORDED.** The payload's cause
field is named `reason_code` from the split onward and these rows spell it
`reason`; that is not repaired here. An outbox row is the record of a past
event, and this repository's posture on stored data is `customer_floor`'s: a
value keeps the spelling it was written with and readers carry both (#412).
Only the NAME is rewritten, because only the name has a failure mode — it is
what a subscription is matched against and what the handler registry dispatches
on, and neither can find a name nothing registers. A body key has no such
failure: it is delivered verbatim either way.

**⚠ AND THE NAME IS REWRITTEN ON EVERY ROW BEARING IT, NOT ONLY A PENDING ONE**,
which sits in tension with the sentence above and is `0007`'s choice rather than
a new one. The argument for moving rows is about the PENDING ones — a queued row
under a name nothing registers drains to no handler — so a delivered row is
rewritten to a name it was never delivered under. Two reasons that is still
right: the outbox's dedup index and the handler registry both key on the name,
so a table holding two names for one event makes every later lookup ask which,
and `WebhookDeliveryAttempt` is the record of what a subscriber actually
received and is untouched here. The queue is a work list; the delivery attempts
are the history.

**The reverse is provided and is a LOSSY COLLAPSE — stated rather than
pretended.** Both successors map back to the one retired name. For outbox rows
that round-trips exactly, because the payload's reason survives untouched and a
re-forward routes the row by the same evidence. For subscriptions it does not:
a subscription written AFTER the split naming only ONE successor reverses to
the retired name and re-forwards to BOTH, so the subscriber gains an event it
never asked for. That is the one case, and it exists only in a rollback of the
slice itself — for which #155 §10.1 has already ruled there is no meaningful
revert. It is recorded because a reverse that silently widens a public contract
should be read before it is run, not discovered afterwards.

**⚠ ON WHETHER THE DATA HAD TO BE CARRIED AT ALL.** #155 §5.3 says *"during the
re-model, migrations need not carry data."* It is carried anyway, on three
grounds: ADR-0007 §1 records that exemption as SPENT and not available again;
`0007` — the nearest neighbour, and later than #155 — carried its data and
argued why; and the reasons it gave are live on a developer machine rather than
hypothetical.
"""
from django.db import migrations

#: Retired name -> its two successors, exactly as
#: domain-vocabulary/concepts/webhooks.yaml declares them. The order within
#: each pair is (spend stop, expiry) and is not significant — both are added.
#:
#: A second encoding of names the registry already declares, necessarily so: a
#: migration must not import application code, because it has to keep working
#: when the code has moved on. The repository's rule for a second encoding is
#: #203's — the two copies exist and a contract test holds them to each other
#: (tests/contracts/test_webhook_split_migration.py).
SPLIT = {
    "task.limit_exceeded": ("task.killed", "task.expired"),
    "subtask.limit_exceeded": ("subtask.killed", "subtask.expired"),
}

#: The reverse: every successor collapses onto the one name it came from. Each
#: value is a one-element tuple so the two directions run through one function
#: and the reverse cannot drift from the forward.
COLLAPSE = {
    successor: (retired,)
    for retired, successors in SPLIT.items()
    for successor in successors
}

#: The recorded reasons that are EVIDENCE OF AN EXPIRY, and the only ones.
#: Spelled rather than imported for the reason above; the values themselves are
#: `apps.platform.work.reasons.SILENCE_WINDOW` and `.STALE_MAX_AGE`, and a test
#: holds this set to those constants rather than to these strings.
#:
#: ⚠ `stale` IS THE THIRD MEMBER AND IT IS NOT A TYPO. The silence window's stop
#: was spelled `stale` until #412 sourced it from the registry, and rows written
#: before that commit are exactly the rows this migration is here for — so a
#: set naming only today's two constants would route every pre-#412 expiry to
#: `*.killed` and tell a subscriber UBB had stopped work it had merely stopped
#: hearing from. `reasons.SILENCE_WINDOW` carries a comment saying so.
REAPER_REASONS = ("silence_window", "stale_max_age", "stale")

#: The key an outbox row records its cause under. These rows all predate the
#: split — the filter is the retired NAME, and only the pre-split code wrote
#: one — so they all spell the cause the pre-split way.
RECORDED_CAUSE_KEY = "reason"


def _migrate_selectors(selectors, mapping):
    """A subscription's stored ``event_types`` under ``mapping``.

    Order is preserved and untouched entries are kept verbatim. A name in
    ``mapping`` is replaced, in place, by every successor it names.

    ⚠ A NAME IS ADDED AT MOST ONCE, AND WHAT THAT COSTS DIFFERS BY DIRECTION —
    the same de-duplication reads as a safeguard forwards and as the loss
    backwards, which is why one sentence about it would be wrong half the time.

    FORWARDS (``SPLIT``, one name to two) it removes nothing a subscription
    meant: the only entry it can drop is one the list already held TWICE, which
    selects nothing the single entry does not, since delivery matches on
    membership.

    BACKWARDS (``COLLAPSE``, two names to one) it is where the list actually
    SHRINKS, and by design: a subscription holding both successors reverses to
    one entry, because both name the same retired event. That is the lossy
    reverse this module's docstring names, made concrete — and it is why a
    subscription written after the split naming only ONE successor does not
    round-trip.

    `"*"` and `[]` are selectors rather than names and so have nothing to map.
    """
    migrated = []
    for selector in selectors:
        for name in mapping.get(selector, (selector,)):
            if name not in migrated:
                migrated.append(name)
    return migrated


def _rewrite_subscriptions(apps, mapping):
    """Apply ``mapping`` to every stored subscription that it changes.

    Only rows that actually change are written — a data migration that rewrote
    every row would churn the whole table to no purpose. The rows are selected
    in Python rather than by a containment lookup, because ``event_types`` is a
    ``JSONField``: the array lookups that would push the filter into Postgres
    are ``ArrayField``'s, and a JSON one that silently matched nothing would
    make this a no-op nobody noticed (`0007`'s reasoning, unchanged).
    """
    TenantWebhookConfig = apps.get_model("events", "TenantWebhookConfig")
    for config in TenantWebhookConfig.objects.only(
            "id", "event_types").iterator():
        migrated = _migrate_selectors(config.event_types, mapping)
        if migrated != config.event_types:
            TenantWebhookConfig.objects.filter(pk=config.pk).update(
                event_types=migrated)


def split_the_terminal_events(apps, schema_editor):
    """Forward: fan the subscriptions out, route the outbox rows."""
    OutboxEvent = apps.get_model("events", "OutboxEvent")
    for retired, (killed, expired) in SPLIT.items():
        # The evidenced claim first, on the rows that carry the evidence...
        OutboxEvent.objects.filter(
            event_type=retired,
            **{f"payload__{RECORDED_CAUSE_KEY}__in": REAPER_REASONS},
        ).update(event_type=expired)
        # ...and then the default, which is everything the first statement did
        # not take: another reason, an unrecognised one, or none recorded.
        OutboxEvent.objects.filter(event_type=retired).update(
            event_type=killed)

    _rewrite_subscriptions(apps, SPLIT)


def collapse_the_terminal_events(apps, schema_editor):
    """Reverse: both successors back onto the one retired name, lossily.

    The outbox side is exact — the payload's recorded reason is untouched, so a
    re-forward routes each row to the successor it came from. The subscription
    side is the lossy half, and the case is named in this module's docstring.
    """
    OutboxEvent = apps.get_model("events", "OutboxEvent")
    for retired, successors in SPLIT.items():
        OutboxEvent.objects.filter(event_type__in=successors).update(
            event_type=retired)

    _rewrite_subscriptions(apps, COLLAPSE)


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0007_rename_thirteen_webhook_event_types"),
    ]

    operations = [
        migrations.RunPython(split_the_terminal_events,
                             collapse_the_terminal_events),
    ]
