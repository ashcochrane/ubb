"""F2.2 — swap tags GIN index from jsonb_path_ops to default jsonb_ops.

Why swap
--------
The current index (idx_usage_event_tags) was created with jsonb_path_ops in
migration 0017.  The jsonb_path_ops opclass hashes full JSON paths so it can
only serve the containment operator (@>).  The key-exists operator (?) — which
Django's tags__has_key lookups compile to — requires the default jsonb_ops
opclass.  With the old index, every has_key query falls back to a seq/btree
scan.  There are four production call sites that use has_key (queries.py,
metering_endpoints.py ×3) and only one that uses containment; both operators
are served by jsonb_ops, so jsonb_ops is strictly better for this workload.

Why swap, not add
-----------------
Adding a second GIN index on tags would double the GIN write overhead on the
record_usage insert hot path.  Swapping keeps the index count flat.

Forward migration
-----------------
  1. CREATE INDEX CONCURRENTLY … idx_usage_event_tags_ops  (jsonb_ops — the new one)
  2. DROP INDEX CONCURRENTLY … idx_usage_event_tags  (jsonb_path_ops — the old one)

Create-before-drop so @> containment coverage never lapses.

Backward migration
------------------
  1. CREATE INDEX CONCURRENTLY … idx_usage_event_tags  (jsonb_path_ops — restore old)
  2. DROP INDEX CONCURRENTLY … idx_usage_event_tags_ops  (drop new)

atomic = False
--------------
CREATE/DROP INDEX CONCURRENTLY cannot run inside a transaction.  Django wraps
each migration in a transaction by default; setting atomic = False disables
that wrapper so the CONCURRENTLY statements execute outside any transaction.

Failure runbook
---------------
If a CONCURRENTLY build is interrupted (e.g. SIGKILL, OOM), Postgres marks the
index INVALID.  An INVALID index satisfies the IF NOT EXISTS guard, so a plain
re-run will silently succeed on the CREATE step but leave the dead index.
Recovery:
  1. psql: DROP INDEX CONCURRENTLY IF EXISTS idx_usage_event_tags_ops;
  2. Then re-run: manage.py migrate usage 0022
"""
from django.db import connection, migrations


def swap_to_jsonb_ops(apps, schema_editor):
    if connection.vendor != "postgresql":
        return
    # Step 1: create the new jsonb_ops index (serves both ? and @>)
    schema_editor.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_usage_event_tags_ops "
        "ON ubb_usage_event USING GIN (tags);"
    )
    # Step 2: drop the old jsonb_path_ops index (only served @>)
    schema_editor.execute(
        "DROP INDEX CONCURRENTLY IF EXISTS idx_usage_event_tags;"
    )


def swap_back_to_jsonb_path_ops(apps, schema_editor):
    if connection.vendor != "postgresql":
        return
    # Step 1: restore the old jsonb_path_ops index
    schema_editor.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_usage_event_tags "
        "ON ubb_usage_event USING GIN (tags jsonb_path_ops);"
    )
    # Step 2: drop the new jsonb_ops index
    schema_editor.execute(
        "DROP INDEX CONCURRENTLY IF EXISTS idx_usage_event_tags_ops;"
    )


class Migration(migrations.Migration):
    # CONCURRENTLY cannot run inside a transaction.
    atomic = False

    dependencies = [
        ("usage", "0021_usageevent_service_id_agent_id"),
    ]

    operations = [
        migrations.RunPython(swap_to_jsonb_ops, swap_back_to_jsonb_path_ops),
    ]
