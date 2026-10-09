"""A recording keeps what its acknowledgement said, and the database keeps it
as it was said (#569; ADR-0019).

One table and one rule. ``ubb_stop_acknowledgement`` holds, for every posting
the recording path writes, the stop facts its acknowledgement returned — stop
or not — beside the named unit's ceiling assessment and which unit or whose
customer-wide line the stop was about. An idempotent replay answers those
fields from this row and from nothing else.

**Why a trigger, and why on both statements.** A record whose whole point is
that a replay can trust it cannot be one a ``QuerySet.update()`` or a ``psql``
session may quietly rewrite: a model ``save()`` guard is not enforcement
(ADR-0007 §2), and this repository has shipped one a production writer
bypassed by design. A ``BEFORE UPDATE OR DELETE ... FOR EACH ROW`` trigger
fires for every door and refuses before the write — the mechanism ``0037``
argues for the posting's columns and ``0041`` uses for the measurement child.

**Inserts pay nothing**: the trigger is not on ``INSERT``, so the recording
path — one insert per recorded result, inside the savepoint it already holds
— never enters it.

**The one admitted ``DELETE`` is a sandbox's discard**, the measurement
record's own carve-out (#354, ``0041``): ``reset_sandbox_tenant`` hard-deletes
a sandbox's customers, Django's collector deletes this child before its
posting, and a discard of a sandbox is not an edit of what an acknowledgement
said. The parent is read through the posting, which is still on disk when
the collector reaches this row. Every other ``DELETE`` is refused — a live
tenant's posting cannot leave either, its measurement child refuses first.

**The refusal is SQLSTATE 23000**, ``integrity_constraint_violation``, which
Django raises as ``IntegrityError``, and its message says *insert-only* so a
test can assert the rule rather than "something refused".

**No backfill.** UBB is not deployed anywhere, so no recorded posting predates
this table, and a recording-path posting without a row here is an invariant
violation the replay raises by name rather than reconstructs.

The reverse drops the trigger, its function and the table: what ``0044``
left.
"""
import uuid

import django.db.models.deletion
from django.db import migrations, models

TRIGGER = "trg_stop_acknowledgement_is_insert_only"
FUNCTION = "ubb_stop_acknowledgement_is_insert_only"

INSTALL = f"""
CREATE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    on_a_sandbox boolean;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION
            'ubb_stop_acknowledgement is insert-only (#569, ADR-0019): what '
            'an acknowledgement said is kept as it was said, and a replay '
            'answers from it; refused an UPDATE of %', OLD.id
            USING ERRCODE = '23000';
    END IF;

    -- A sandbox's postings are discarded wholesale by its reset, and this
    -- record goes with its posting: a discard, not an edit.
    SELECT t.is_sandbox
      INTO on_a_sandbox
      FROM ubb_posting p
      JOIN ubb_tenant t ON t.id = p.tenant_id
     WHERE p.id = OLD.posting_id;
    IF on_a_sandbox THEN
        RETURN OLD;
    END IF;

    RAISE EXCEPTION
        'ubb_stop_acknowledgement is insert-only (#569, ADR-0019): what an '
        'acknowledgement said leaves only with a sandbox''s discarded '
        'postings; refused a DELETE of %', OLD.id
        USING ERRCODE = '23000';
END;
$$;

CREATE TRIGGER {TRIGGER}
BEFORE UPDATE OR DELETE ON ubb_stop_acknowledgement
FOR EACH ROW
EXECUTE FUNCTION {FUNCTION}();
"""

UNINSTALL = f"""
DROP TRIGGER {TRIGGER} ON ubb_stop_acknowledgement;
DROP FUNCTION {FUNCTION}();
"""


def install(apps, schema_editor):
    schema_editor.execute(INSTALL, params=None)


def uninstall(apps, schema_editor):
    schema_editor.execute(UNINSTALL, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ("usage", "0044_a_postings_kind_is_settled_at_birth"),
        # The rule reads `ubb_tenant.is_sandbox`; named rather than assumed.
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="StopAcknowledgement",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("stop", models.BooleanField()),
                ("stop_reason", models.CharField(blank=True, max_length=64, null=True)),
                ("stop_scope", models.CharField(blank=True, max_length=16, null=True)),
                ("trigger_source", models.CharField(blank=True, max_length=64, null=True)),
                ("stop_bound_micros", models.BigIntegerField(blank=True, null=True)),
                ("stop_measured_micros", models.BigIntegerField(blank=True, null=True)),
                ("ceiling_status", models.CharField(blank=True, max_length=32, null=True)),
                ("ceiling_used_percentage", models.BigIntegerField(blank=True, null=True)),
                ("ceiling_remaining_micros", models.BigIntegerField(blank=True, null=True)),
                ("parent_task_id", models.UUIDField(blank=True, null=True)),
                ("stop_task_id", models.UUIDField(blank=True, null=True)),
                ("stop_customer_id", models.UUIDField(blank=True, null=True)),
                ("posting", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="stop_acknowledgement", to="usage.posting")),
            ],
            options={
                "db_table": "ubb_stop_acknowledgement",
            },
        ),
        migrations.RunPython(install, uninstall),
    ]
