"""The audit catalogue comes from the registry, by reference (R10-W4).

Rulings 5 and 6 (2026-10-27): the ledger's actions are the registry's
`audit_action`, and the kind of record an action changed is the registry's
closed `audit_resource_type`. `record()` refuses anything else, and every
production writer names both by reference to the generated constants rather
than spelling them.

The cutover (#190, ADR-0026) deleted the one action the registry withheld,
`system.preproduction_model_cutover`, with its exclusion: no opening row is
ever written (ruling 6354381879), so the name is now simply unregistered and
`record()` refuses it like any other.
"""
import ast
import json
import sys
from pathlib import Path

from django.conf import settings
from django.db import connection, migrations
from django.db.migrations.loader import MigrationLoader
from django.test import Client, TestCase

from api.v1.tests._helpers import a_tenant
from apps.platform.audit.actions import AUDIT_ACTIONS, AUDIT_RESOURCE_TYPES
from apps.platform.audit.ledger import record
from apps.platform.audit.marker import records_audit
from apps.platform.audit.models import AuditRecord
from core.vocabulary import (
    ACTOR_KIND_KNOWN_VALUES, AUDIT_ACTION_API_KEY_CREATED, AUDIT_ACTION_VALUES,
    AUDIT_RESOURCE_TYPE_API_KEY, AUDIT_RESOURCE_TYPE_VALUES)

#: The opening entry #154 §4.2 once planned. Spelled here because no generated
#: constant names it any more: the registry no longer declares it (#190).
THE_RETIRED_OPENING_ENTRY = "system.preproduction_model_cutover"
PLATFORM = Path(settings.BASE_DIR)


class TheLedgerRecordsOnlyWhatTheRegistryDeclaresTest(TestCase):

    def setUp(self):
        self.tenant, _ = a_tenant("Audited")

    def test_the_recordable_set_is_the_registrys(self):
        self.assertEqual(AUDIT_ACTIONS, AUDIT_ACTION_VALUES)
        self.assertEqual(AUDIT_RESOURCE_TYPES, AUDIT_RESOURCE_TYPE_VALUES)
        self.assertNotIn(THE_RETIRED_OPENING_ENTRY, AUDIT_ACTION_VALUES)

    def test_no_opening_entry_can_be_written(self):
        """The audit reset's half that survives the deletion (#190 option (i)):
        the cutover writes no opening row, and nothing can write one later —
        the name is refused as unregistered at both the ledger and the route
        marker, and the ledger holds no such row."""
        with self.assertRaisesRegex(ValueError, "unregistered"):
            record(action=THE_RETIRED_OPENING_ENTRY, tenant_id=self.tenant.id,
                   resource_type=AUDIT_RESOURCE_TYPE_API_KEY)
        with self.assertRaisesRegex(ValueError, "unregistered"):
            records_audit(THE_RETIRED_OPENING_ENTRY)
        self.assertFalse(AuditRecord.objects.filter(
            action=THE_RETIRED_OPENING_ENTRY).exists())

    def test_an_undeclared_resource_type_is_refused(self):
        for wrong in ("tenant_config", "credit_grant", ""):
            with self.subTest(resource_type=wrong):
                with self.assertRaisesRegex(ValueError, "audit resource type"):
                    record(action=AUDIT_ACTION_API_KEY_CREATED,
                           tenant_id=self.tenant.id, resource_type=wrong)
        self.assertFalse(AuditRecord.objects.exists())

    def test_every_declared_resource_type_is_admitted(self):
        for resource_type in sorted(AUDIT_RESOURCE_TYPE_VALUES):
            with self.subTest(resource_type=resource_type):
                record(action=AUDIT_ACTION_API_KEY_CREATED,
                       tenant_id=self.tenant.id, resource_type=resource_type)
        self.assertEqual(AuditRecord.objects.count(),
                         len(AUDIT_RESOURCE_TYPE_VALUES))


def migrations_that_could_write_an_audit_record(graph_migrations, table):
    """Every operation in the given migrations that could leave a row in the
    audit ledger: any data step in Python (it can do anything), and any SQL
    that names the ledger's table. One sentence per finding."""
    faults = []
    for migration in graph_migrations:
        name = f"{migration.app_label}/{migration.name}"
        for operation in migration.operations:
            if isinstance(operation, migrations.RunPython):
                faults.append(f"{name} runs a Python data step")
            elif isinstance(operation, migrations.RunSQL):
                statements = (operation.sql if isinstance(operation.sql, (list, tuple))
                              else [operation.sql])
                if any(table in str(statement) for statement in statements):
                    faults.append(f"{name} names {table} in its SQL")
    return faults


class TheCutoverOpensTheTrailEmptyTest(TestCase):
    """#190 option (i), ADR-0026 §6: the audit trail opens with NO row — the
    cutover writes none and the fresh initial set cannot. A count after
    migrate alone would be weak (an earlier `TransactionTestCase` flush could
    have emptied a row a migration wrote), so the structural half reads every
    one of UBB's own migrations (Django's contrib apps own no audit table) and
    shows none could write one."""

    def test_no_migration_could_write_an_audit_record(self):
        loader = MigrationLoader(connection, ignore_no_migrations=True)
        graph = [migration for migration in loader.graph.nodes.values()
                 if PLATFORM in Path(sys.modules[type(migration).__module__]
                                     .__file__).resolve().parents]
        assert len(graph) >= 26, "the walk did not read the fresh initial set"
        self.assertEqual(migrations_that_could_write_an_audit_record(
            graph, AuditRecord._meta.db_table), [])

    def test_a_migrated_database_holds_no_audit_record(self):
        self.assertFalse(AuditRecord.objects.exists())

    def test_planted_a_migration_that_could_write_one_is_found(self):
        table = AuditRecord._meta.db_table
        python = type("Migration", (migrations.Migration,), {
            "operations": [migrations.RunPython(lambda apps, schema: None)]})(
                "0003_open_the_trail", "audit")
        sql = type("Migration", (migrations.Migration,), {
            "operations": [migrations.RunSQL(
                [f"INSERT INTO {table} (action) VALUES ('x')"],
                migrations.RunSQL.noop)]})("0004_seed", "audit")
        rules = type("Migration", (migrations.Migration,), {
            "operations": [migrations.RunSQL(["CREATE TRIGGER t ON ubb_posting"],
                                             ["DROP TRIGGER t"])]})(
                "0002_the_database_rules", "usage")
        self.assertEqual(migrations_that_could_write_an_audit_record(
            [python, sql, rules], table),
            ["audit/0003_open_the_trail runs a Python data step",
             f"audit/0004_seed names {table} in its SQL"])


def _audit_literals():
    """Every string literal a production module hands the ledger as an action
    or a resource type: a `records_audit(...)` argument, or the value of an
    `action=` / `resource_type=` keyword whose literal is a declared value."""
    found = []
    for path in sorted(PLATFORM.rglob("*.py")):
        rel = path.relative_to(PLATFORM).as_posix()
        if ("/tests/" in rel or "/migrations/" in rel or rel.startswith(".venv")
                or rel == "core/vocabulary.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            literals = []
            if isinstance(node, ast.keyword) and node.arg in ("action",
                                                               "resource_type"):
                literals = [c for c in ast.walk(node.value)
                            if isinstance(c, ast.Constant)
                            and c.value in (AUDIT_ACTION_VALUES
                                            | AUDIT_RESOURCE_TYPE_VALUES)]
            elif (isinstance(node, ast.Call) and getattr(node.func, "id", None)
                  == "records_audit"):
                literals = [c for c in node.args if isinstance(c, ast.Constant)]
            found += [f"{rel}:{c.lineno} {c.value!r}" for c in literals]
    return found


class EveryWriterNamesTheCatalogueByReferenceTest(TestCase):
    """Ruling 6's "every writer uses the declared values by reference", held
    structurally: a literal action or resource type in a production module is
    a second spelling of a registry value, and this names where."""

    def test_no_production_module_spells_an_action_or_a_resource_type(self):
        self.assertEqual(_audit_literals(), [])

    def test_the_walk_reads_the_writers(self):
        # Vacuity guard: the walk must reach the modules that write the ledger.
        writers = [p for p in PLATFORM.rglob("*_endpoints.py")
                   if "AUDIT_RESOURCE_TYPE_" in p.read_text(encoding="utf-8")]
        self.assertGreaterEqual(len(writers), 8)


class TheFeedPublishesTheCatalogueTest(TestCase):

    def test_a_written_entry_reads_back_in_the_registrys_words(self):
        tenant, raw_key = a_tenant("Feed")
        auth = {"HTTP_AUTHORIZATION": f"Bearer {raw_key}"}
        http = Client()
        minted = http.post("/api/v1/tenant/api-keys", data=json.dumps(
            {"label": "second"}), content_type="application/json", **auth)
        self.assertIn(minted.status_code, (200, 201), minted.content)

        feed = http.get("/api/v1/audit/records", **auth)

        self.assertEqual(feed.status_code, 200, feed.content)
        (entry,) = [row for row in feed.json()["data"]
                    if row["action"] == AUDIT_ACTION_API_KEY_CREATED]
        self.assertEqual(entry["resource_type"], AUDIT_RESOURCE_TYPE_API_KEY)
        self.assertIn(entry["actor_kind"], ACTOR_KIND_KNOWN_VALUES)
