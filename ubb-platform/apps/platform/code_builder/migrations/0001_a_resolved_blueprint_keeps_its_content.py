"""A resolved Blueprint keeps its content, and the content never moves (#576).

One table and one rule. Resolving an Integration Blueprint from published
configuration stores the resolved content under the content's own hash, so the
`configuration_fingerprint` a generated file is stamped with names something
that exists rather than something recomputed later from whatever
configuration is there by then.

**THE RULE IS THE ENFORCEMENT HALF OF A DECLARATION THE MODEL MAKES.**
`BlueprintSnapshot.transition_classes` declares the tenant, the fingerprint
and the content FROZEN — ADR-0007 §2's *none after insert* — and that ADR is
explicit that a model-level guard alone is not enforcement. So the refusal is
a trigger, and it fires for every door: `save()`, `QuerySet.update()`, a data
migration, `psql`.

**Why `BEFORE UPDATE`, and why DELETE is left alone.** A snapshot has no
lifecycle: it is inserted once and never changed, and a `BEFORE UPDATE ... FOR
EACH ROW` trigger refuses a change before the write and never enters on an
INSERT. Deleting one is a different act and a permitted one — it is a
prunable fixture, and it leaves by cascade when a sandbox is reset or a tenant
is removed. A rule on DELETE cannot tell a prune from that cascade, and would
fail the whole reset.

**The `WHEN` clause names the three columns**, so a write that changes none of
them — the `updated_at` a full `save()` refreshes — is not refused for a
change it did not make.

**The refusal is raised as SQLSTATE 23000**, `integrity_constraint_violation`,
the class Django maps to `IntegrityError`, and the message names the transition
class and the table.

**THE REVERSE IS EXACT**: drop the rule, drop the table. Nothing else was
touched.
"""

import django.db.models.deletion
import uuid
from django.db import migrations, models

TRIGGER = "trg_blueprint_snapshot_declared_transitions"
FUNCTION = "ubb_blueprint_snapshot_declared_transitions"

INSTALL = f"""
CREATE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- tenant_id, configuration_fingerprint and content are declared FROZEN:
    -- the fingerprint is the hash of the content, and a generated file was
    -- stamped with it. A snapshot is replaced by resolving again, which
    -- stores a new one beside it.
    IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
       OR NEW.configuration_fingerprint IS DISTINCT FROM OLD.configuration_fingerprint
       OR NEW.content IS DISTINCT FROM OLD.content THEN
        RAISE EXCEPTION
            'tenant_id, configuration_fingerprint and content are declared '
            'frozen (ADR-0007 §2): a blueprint snapshot is the content its '
            'fingerprint is the hash of, and it never changes; resolve the '
            'blueprint again instead'
            USING ERRCODE = '23000';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER {TRIGGER}
BEFORE UPDATE ON ubb_blueprint_snapshot
FOR EACH ROW
WHEN (OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
      OR OLD.configuration_fingerprint IS DISTINCT FROM NEW.configuration_fingerprint
      OR OLD.content IS DISTINCT FROM NEW.content)
EXECUTE FUNCTION {FUNCTION}();
"""

UNINSTALL = f"""
DROP TRIGGER {TRIGGER} ON ubb_blueprint_snapshot;
DROP FUNCTION {FUNCTION}();
"""


def install(apps, schema_editor):
    schema_editor.execute(INSTALL, params=None)


def uninstall(apps, schema_editor):
    schema_editor.execute(UNINSTALL, params=None)


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('tenants', '0027_admission_control_comes_to_the_kernel'),
    ]

    operations = [
        migrations.CreateModel(
            name='BlueprintSnapshot',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('configuration_fingerprint', models.CharField(max_length=71)),
                ('content', models.JSONField()),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='blueprint_snapshots', to='tenants.tenant')),
            ],
            options={
                'db_table': 'ubb_blueprint_snapshot',
                'constraints': [models.UniqueConstraint(fields=('tenant', 'configuration_fingerprint'), name='uq_blueprint_snapshot_fingerprint'), models.CheckConstraint(condition=models.Q(('configuration_fingerprint__regex', '^sha256:[0-9a-f]{64}$')), name='ck_blueprint_snapshot_fingerprint_shape')],
            },
        ),
        migrations.RunPython(install, uninstall),
    ]
