"""The two expiry windows each get a middle rung on this tenant (#412).

How long work may go quiet, and how long it may run at all, stop being one
number and one hard-coded duration and become a three-rung ladder: the kind of
work's own declaration, then the tenant's default, then UBB's backstop. This
file adds the tenant rung for the second window and makes the first one able to
say *nothing was declared here*.

**THE SILENCE WINDOW BECOMES NULLABLE, AND NOTHING'S BEHAVIOUR CHANGES.** Every
existing row keeps the value it has — the alter widens what the column may
hold and rewrites nothing — and the backstop beneath it is the same fifteen
minutes the column defaulted to, so a tenant that never touched it is swept
exactly as before whether its row says 900 or says nothing. What NULL buys is
the distinction the ladder needs: *this tenant declared no window* and *this
tenant declared the same number UBB would have used* are different facts, and
only the first may be overridden from below by a backstop that later moves.
Zero keeps the meaning it has always had here — the tenant wants no silence
window — and is deliberately NOT read as a fall-through, because reading it as
one would silently re-arm a sweeper somebody switched off.

**THE ABSOLUTE DEADLINE ARRIVES WITH A CHECK, AND THE CHECK IS THE POINT.**
`ck_tenant_absolute_deadline_positive` admits NULL or a real window and refuses
zero. Dropping the absolute ceiling entirely was considered and rejected: it is
the guard that stops any tenant getting an immortal unit of work, and a tenant
with no reaper of its own would otherwise have stopped work living forever
holding a concurrency slot and a prepaid reservation. Without the rule, "no
rung may switch the ceiling off" would be a property of whichever code path
last read the column; with it, it is a property of the database. There is
deliberately no twin for the silence window beside it, because zero IS a
declaration there.

**PURE ADDITION.** No row is rewritten and no default is backfilled: the new
column takes NULL everywhere, which is the honest record of a tenant that has
declared nothing, and the check is satisfied by every existing row before it is
installed.

**THE REVERSE IS EXACT**: drop the rule, drop the column, narrow the silence
window back to a non-null default. The narrowing is the only asymmetric step
and it is safe in the only direction that can be taken — a row holding NULL
would refuse to go back, and no path writes NULL to it before this commit.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0024_remove_tenant_require_cost_card_coverage'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenant',
            name='task_absolute_deadline_seconds',
            field=models.PositiveIntegerField(blank=True, default=None, null=True),
        ),
        migrations.AlterField(
            model_name='tenant',
            name='task_stale_seconds',
            field=models.PositiveIntegerField(blank=True, default=None, null=True),
        ),
        migrations.AddConstraint(
            model_name='tenant',
            constraint=models.CheckConstraint(condition=models.Q(('task_absolute_deadline_seconds__isnull', True), ('task_absolute_deadline_seconds__gt', 0), _connector='OR'), name='ck_tenant_absolute_deadline_positive'),
        ),
    ]
