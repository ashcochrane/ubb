"""Carry the thirteen renamed event names on the two tables that store them (#222).

ADR-0006 §5 names an event for the state entered, under the domain owner whose
lifecycle moved. Thirteen names predating that convention are renamed in code by
#222; this migration carries the rows that already spell them.

**Why a migration is needed at all.** `TenantWebhookConfig.event_types` is a
stored `JSONField` holding the names verbatim, and `is_valid_event_selector`
only runs at config-create time. An unmigrated row would therefore go on
existing, pass every validation it will ever face again, and match nothing — the
#75 defect `events/catalog.py` records in its own docstring, which hid
`customer.deleted` from subscribers while the delivery path emitted it.

**Why `OutboxEvent` moves too**, which #222 §7 does not name. The outbox is a
work queue and a dedup index keyed on `event_type`, not the audit record — the
audit ledger is `apps/platform/audit/` and the record of what a subscriber
actually received is `WebhookDeliveryAttempt`, and neither is touched here.
Three live reads key on the name:

- `deliver_webhook` matches `event.event_type` against the migrated
  subscription, so a still-pending row under the old name would silently match
  nothing — the same defect as above, one table over.
- the handler registry dispatches by event type, so a pending row under a name
  nothing registers drains to no handler.
- `MarginService` deduplicates a cost spike by looking for an earlier
  `provider.cost_spike` row, so an unmigrated history would re-emit one per
  customer and period.

Rewriting the queue is what keeps those three correct; the delivery attempts
that record what was actually POSTed are left exactly as they were.

Reversible, and deliberately so. The map is 1:1 and no retired name is published
any more, so a rollback restores precisely the rows it finds — where a `noop`
reverse would strand every subscriber on a name the reverted code no longer
emits.

The seven remaining G8 debts are NOT here. The two Task events become TWO events
each in slice 5 (#140 §4.3) and the five control events are rewritten under
#150's four families in slice 6, so a 1:1 rename now would encode a target state
nobody has agreed.
"""
from django.db import migrations

#: Retired name → end-state name, all thirteen, exactly as
#: domain-vocabulary/concepts/webhooks.yaml declares them. A product may not own
#: a namespace (`billing`), a measure may not own one (`margin`), the subject
#: belongs in the namespace rather than inside the transition token
#: (`usage.invoice_pushed`), and one concept has one spelling (`auto_topup`).
RENAMES = {
    "billing.balance_low": "wallet.balance_low",
    "billing.balance_critical": "wallet.balance_critical",
    "billing.balance_overage": "wallet.balance_overage",
    "billing.customer_suspended": "customer.suspended",
    "billing.topup_requested": "top_up.requested",
    "billing.withdrawal_requested": "withdrawal.requested",
    "billing.credit_grant_expiring": "credit_grant.expiring",
    "billing.credit_grant_expired": "credit_grant.expired",
    "margin.customer_unprofitable": "customer.unprofitable",
    "margin.provider_cost_spike": "provider.cost_spike",
    "usage.invoice_pushed": "usage_invoice.pushed",
    "usage.invoice_push_failed_permanent": "usage_invoice.push_failed_permanent",
    "auto_topup.requires_action": "auto_top_up.requires_action",
}

REVERSE = {new: old for old, new in RENAMES.items()}


def _apply(apps, mapping):
    """Rewrite every stored occurrence of a name in ``mapping``.

    Subscriptions are rewritten element-wise so a mixed list keeps its order and
    its untouched entries — a subscription is a public contract, and reordering
    or dropping part of one would be a second, silent change to it. `"*"` and
    `[]` are selectors rather than names and so have nothing to map.

    Only rows that actually change are written, on both tables: a data migration
    that rewrote every row would churn the whole outbox to no purpose. The
    subscriptions are selected in Python rather than by a containment lookup,
    because `event_types` is a `JSONField` — the array lookups that would push
    the filter into Postgres are `ArrayField`'s, and a JSON one that silently
    matched nothing would make this a no-op nobody noticed.
    """
    OutboxEvent = apps.get_model("events", "OutboxEvent")
    for old, new in mapping.items():
        OutboxEvent.objects.filter(event_type=old).update(event_type=new)

    TenantWebhookConfig = apps.get_model("events", "TenantWebhookConfig")
    for config in TenantWebhookConfig.objects.only(
            "id", "event_types").iterator():
        migrated = [mapping.get(name, name) for name in config.event_types]
        if migrated != config.event_types:
            TenantWebhookConfig.objects.filter(pk=config.pk).update(
                event_types=migrated)


def rename_subscriptions(apps, schema_editor):
    _apply(apps, RENAMES)


def restore_subscriptions(apps, schema_editor):
    _apply(apps, REVERSE)


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0006_remove_unproduced_skipped_status"),
    ]

    operations = [
        migrations.RunPython(rename_subscriptions, restore_subscriptions),
    ]
