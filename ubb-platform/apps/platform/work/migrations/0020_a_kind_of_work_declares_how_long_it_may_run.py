"""How long work may run, and how long it may go quiet, become properties of
the KIND of work (#412).

Two columns and one rule. The declaration already carries this tenant's COGS
ceiling for exactly the argument these two make: one kind of job that
legitimately costs twenty times its sibling should not force you to raise the
cap on both, and one that legitimately runs twenty minutes between usage
reports should not force you to widen the silence window on both either. How
long a sold job may take is the same shape of property as what it may spend,
so it belongs in the same place.

**`silence_window_seconds`** bounds the time since the last usage report on a
unit. Reporting usage is the ONLY thing that proves a unit is alive: there is
no keepalive call, and no read of a unit extends its life. An implicit
keepalive on reads was rejected outright — a console listing, a support query
or an admin inspecting stopped work would silently resurrect it. NULL falls
through to the tenant's own default and then to UBB's backstop; zero declares
that this kind has no silence window at all, which is a real answer for work
that is legitimately quiet for hours.

**`absolute_deadline_seconds`** bounds total wall-clock age regardless of
activity, and `ck_task_type_absolute_deadline_positive` admits NULL or a real
window and refuses zero. Dropping the absolute ceiling entirely was considered
and rejected: it is the guard that stops any tenant getting an immortal unit of
work. Because zero is refused at every rung, a kind of work that declares no
silence window at all still cannot run forever — which is the property the rule
exists to make true of the database rather than of whichever code path last
read the column.

**PURE ADDITION, AND NO ROW IS REWRITTEN.** Both columns are nullable and every
existing declaration takes NULL, which is the honest record of a kind of work
declared before either window could be declared: it inherits, exactly as it did
when the windows were durations spelled at the sweepers. Nothing reads either
column before this commit.

**THE REVERSE IS EXACT**: drop the rule, drop both columns.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0025_the_two_expiry_windows_get_a_tenant_rung'),
        ('work', '0019_a_start_claims_its_key_permanently'),
    ]

    operations = [
        migrations.AddField(
            model_name='tasktype',
            name='absolute_deadline_seconds',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='tasktype',
            name='silence_window_seconds',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name='tasktype',
            constraint=models.CheckConstraint(condition=models.Q(('absolute_deadline_seconds__isnull', True), ('absolute_deadline_seconds__gt', 0), _connector='OR'), name='ck_task_type_absolute_deadline_positive'),
        ),
    ]
