"""A start claims a caller-supplied key, and the claim never lapses (#410).

One column and one uniqueness rule arrive together, and the rule is the half
that matters: `UNIQUE(tenant, customer, idempotency_key)` is what makes a
retry after a lost response return the unit of work the caller already started
instead of beginning a second one — and a second one is a second ceiling, a
second set of totals and, once a delivery creates a charge, a second charge.
It is the POSTING'S OWN SCOPE (`uq_usage_event_idempotency_v2`) on the same
argument: both are a caller reporting that something happened for a NAMED
customer, and two of a tenant's customers may each run a `nightly-batch`.

**PURE ADDITION, AND NO ROW IS REWRITTEN.** The column is nullable and every
existing unit of work takes NULL, which is the only honest value: each was
registered through a path that could not carry a key, and there is no
caller-supplied string to invent for them that would not be a fabricated
declaration. The uniqueness rule is PARTIAL for exactly that reason — it is
the shape a top-up's key already has (`WalletTransaction.idempotency_key`) —
so the historic rows are outside it rather than colliding inside it at a
shared `""`.

**WHAT MAKES THE KEY REQUIRED IS NOT THIS COLUMN.** The one route that
registers a unit of work refuses a request that omits it. That is a rule about
what a caller may ask for, and it lives where a caller can be told about it;
this file's job is only to make the claim, once made, impossible to route
around.

**THE REVERSE IS EXACT**: drop the rule, drop the column. Nothing reads either
before this commit and nothing outside the start gate writes them after it.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0014_customer_suspension_reason'),
        ('tenants', '0024_remove_tenant_require_cost_card_coverage'),
        ('work', '0018_the_close_declares_how_the_work_ended'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='idempotency_key',
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
        migrations.AddConstraint(
            model_name='task',
            constraint=models.UniqueConstraint(condition=models.Q(('idempotency_key__isnull', False)), fields=('tenant', 'customer', 'idempotency_key'), name='uq_task_idempotency_key'),
        ),
    ]
