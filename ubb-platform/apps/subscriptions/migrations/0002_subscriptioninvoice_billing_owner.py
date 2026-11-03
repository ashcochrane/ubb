# Hand-written for R10 Stage C2 (PLAN §7 item 27), 2026-11-04.
"""R10 Stage C2 (PLAN §7 item 27, Option B): every subscription invoice records
its HISTORICAL BILLING OWNER — the owner UBB's declared topology resolved for it
when it first entered UBB — so a later topology change can never move which
owner an unresolved payment failure counts against.

One additive, REQUIRED column: ``billing_owner`` → ``customers.Customer``,
``on_delete=RESTRICT``, NOT NULL, with no default and no data step. UBB is
pre-launch with no production operational history to preserve, and the owner of
an invoice that already exists cannot honestly be reconstructed from today's
topology — so none is invented: on an empty table the column is simply added,
and a database that still holds subscription invoice rows refuses this
migration rather than receive a fabricated owner. (Django's autodetector will
not write a non-null column without a default, so the operation is
hand-written; the model state it leaves is exactly the model's.)

``RESTRICT`` rather than the ruled ``PROTECT``: both refuse deleting an owner
from under its invoices, but ``PROTECT`` also refuses a delete that removes
those invoices in the same operation — so a sandbox reset (which deletes the
tenant's customers, cascading their invoices) failed and left the sandbox
inactive. ``RESTRICT`` admits exactly that case. The column's FROZEN rule is in
``0002_the_database_rules`` beside this one, the repo's one home for a table's
triggers."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0001_initial'),
        ('subscriptions', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptioninvoice',
            name='billing_owner',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.RESTRICT,
                related_name='owned_subscription_invoices',
                to='customers.customer'),
        ),
    ]
