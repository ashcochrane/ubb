"""A kind of work declares its ceiling, or declares itself uncapped — and the
ceiling takes its canonical name at both scopes (#453, slice 6 §2, #150 §8).

**TWO RENAMES, CARRYING THEIR DATA (ADR-0007 §1).** `RenameField`, never
add-plus-remove: the declaration's `default_provider_cost_limit_micros` and
the unit's `provider_cost_limit_micros` — the two strings #153 §18 called a
naming debt — become `task_cogs_ceiling_micros` at both scopes, on
`pricing_mode`'s precedent (one concept at two scopes; the model supplies the
scope). The `default_` prefix leaves the declaration with the rename: a
declared value is THE ceiling of that kind, and a start may request lower.
Postgres does each as `ALTER TABLE ... RENAME COLUMN` — no rewrite, no
backfill, every row keeps its figure.

**THE PARTIAL INDEX IS DROPPED AND RE-DECLARED AROUND THE UNIT'S RENAME.**
`idx_task_active_limited` is a partial index whose condition names the unit's
ceiling column. Postgres would carry the index through the rename untouched
(a condition references a column by attribute number), but Django's migration
state does not rewrite an index condition on `RenameField`, so the model's
index and the state's index would disagree forever after. Removing it before
the rename and adding it back after keeps the state honest at the cost of one
drop-and-create of a small index; the index carries no data.

**`uncapped` ARRIVES, AND EVERY EXISTING NULL CEILING BECOMES IT.** The stated
reason, as ADR-0007 §1 asks for: before this commit a null ceiling on a
declaration meant *fall through to the tenant default, then to no ceiling at
all* — a silence, not a choice (#150 §8.2). After it, a declaration must
answer: a figure, or `uncapped`. The only honest reading of a row that was
declared under the old rule and carries no figure is that its tenant meant no
ceiling on that kind of work, because that is what the tree did with it and no
rung exists any more for it to inherit from. So `uncapped` is set `true` on
exactly those rows, and nothing else is rewritten.

**STATED, BECAUSE IT LOOSENS A CONTROL:** a tenant that held a risk-row
default AND a null-ceiling kind had that kind capped by the default until
this commit; after it the kind is uncapped and the default — carried onto
the tenant row by `gating/0011` — reaches only work with no declared kind.
That is the ticket's ruling (a declared kind answers for itself) and the
only reading a migration can give a row that stated nothing; a tenant that
meant "use my default" revises the kind of work to say so as a figure. What a
migration must not do is invent one. Nothing is deployed, so the rows this
reaches are on developer machines and in fixtures.

**THE EXCLUSIVE-OR IS A CHECK CONSTRAINT, NOT A SERIALIZER RULE (ADR-0007 §2).**
`ck_task_type_ceiling_or_uncapped` admits a figure with `uncapped = false`, or
no figure with `uncapped = true`, and refuses neither and both — through every
door, which is why it is installed after the backfill: every existing row
satisfies it by the time it is checked. Both columns stay ordinary mutable
columns (ADR-0012's Consequences); neither joins a transition class.

**THE REVERSE** drops the rule and the flag, restores the index under the old
column name, and renames both columns back. The flag's information is lost in
reverse — a declaration that had chosen `uncapped` becomes a null ceiling that
once again falls through — which is exactly the silence this commit removes,
stated so it is read before it is run.
"""

from django.db import migrations, models


def every_null_ceiling_is_a_declaration_of_uncapped(apps, schema_editor):
    TaskType = apps.get_model("work", "TaskType")
    TaskType.objects.filter(task_cogs_ceiling_micros__isnull=True).update(uncapped=True)


def the_flag_is_simply_dropped(apps, schema_editor):
    # Nothing to carry back: the column goes, and a null ceiling means "fall
    # through" again under the old rule. Stated in the module docstring.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("work", "0023_the_version_of_the_book_that_answered_is_pinned_too"),
    ]

    operations = [
        # The declaration's ceiling takes its canonical name.
        migrations.RenameField(
            model_name="tasktype",
            old_name="default_provider_cost_limit_micros",
            new_name="task_cogs_ceiling_micros",
        ),
        # The unit's pin takes the same name at the other scope, with the
        # partial index that names it re-declared around the rename.
        migrations.RemoveIndex(
            model_name="task",
            name="idx_task_active_limited",
        ),
        migrations.RenameField(
            model_name="task",
            old_name="provider_cost_limit_micros",
            new_name="task_cogs_ceiling_micros",
        ),
        migrations.AddIndex(
            model_name="task",
            index=models.Index(
                condition=models.Q(("status", "active"),
                                   ("task_cogs_ceiling_micros__isnull", False)),
                fields=["tenant"], name="idx_task_active_limited"),
        ),
        # Uncapped becomes a declaration: the flag, the backfill, the rule.
        migrations.AddField(
            model_name="tasktype",
            name="uncapped",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(every_null_ceiling_is_a_declaration_of_uncapped,
                             the_flag_is_simply_dropped),
        migrations.AddConstraint(
            model_name="tasktype",
            constraint=models.CheckConstraint(
                condition=(models.Q(("task_cogs_ceiling_micros__isnull", False),
                                    ("uncapped", False))
                           | models.Q(("task_cogs_ceiling_micros__isnull", True),
                                      ("uncapped", True))),
                name="ck_task_type_ceiling_or_uncapped"),
        ),
    ]
