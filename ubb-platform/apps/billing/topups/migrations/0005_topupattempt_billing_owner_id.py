# Task 7 (billing-surface-correctness): pin the billing owner on
# TopUpAttempt, exactly like Task.billing_owner_id / UsageEvent's — see the
# model field's comment. No live data exists for this table, but a real
# backfill is written anyway (rather than the crude `F("customer_id")` copy
# UsageEvent's precedent migration used, back when pooled seats didn't yet
# exist as a concept): each row's owner is actually resolved from its
# customer's parent/topology, matching what resolve_billing_owner() computes
# at runtime, so a real deploy with existing rows would backfill correctly.

from django.db import migrations, models


def _backfill_owner(apps, schema_editor):
    Customer = apps.get_model("customers", "Customer")
    TopUpAttempt = apps.get_model("topups", "TopUpAttempt")

    # Parent lookups only need id + billing_topology; cheap even at scale.
    pooled_parent_ids = set(
        Customer.objects.filter(billing_topology="pooled").values_list("id", flat=True)
    )
    seats = Customer.objects.filter(
        account_type="seat", parent_id__isnull=False,
    ).values_list("id", "parent_id")
    owner_by_seat_id = {
        seat_id: parent_id for seat_id, parent_id in seats
        if parent_id in pooled_parent_ids
    }

    for attempt in TopUpAttempt.objects.filter(billing_owner_id__isnull=True):
        attempt.billing_owner_id = owner_by_seat_id.get(attempt.customer_id, attempt.customer_id)
        attempt.save(update_fields=["billing_owner_id"])


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0014_customer_suspension_reason'),
        ('topups', '0004_topupattempt_idempotency_key_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='topupattempt',
            name='billing_owner_id',
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.RunPython(_backfill_owner, migrations.RunPython.noop),
    ]
