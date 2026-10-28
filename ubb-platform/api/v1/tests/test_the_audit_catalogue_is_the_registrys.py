"""The audit catalogue comes from the registry, by reference (R10-W4).

Rulings 5 and 6 (2026-10-27): the ledger's actions are the registry's
`audit_action` less the one it withholds — `system.preproduction_model_cutover`,
kept declared until W6 retires it and never recordable — and the kind of record
an action changed is the registry's closed `audit_resource_type`. `record()`
refuses anything else, and every production writer names both by reference to
the generated constants rather than spelling them.
"""
import ast
import json
from pathlib import Path

from django.conf import settings
from django.test import Client, TestCase

from apps.platform.audit.actions import AUDIT_ACTIONS, AUDIT_RESOURCE_TYPES
from apps.platform.audit.ledger import record
from apps.platform.audit.marker import records_audit
from apps.platform.audit.models import AuditRecord
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.vocabulary import (
    ACTOR_KIND_KNOWN_VALUES, AUDIT_ACTION_API_KEY_CREATED, AUDIT_ACTION_VALUES,
    AUDIT_ACTION_WITHHELD_VALUES, AUDIT_RESOURCE_TYPE_API_KEY,
    AUDIT_RESOURCE_TYPE_VALUES)

(WITHHELD,) = AUDIT_ACTION_WITHHELD_VALUES
PLATFORM = Path(settings.BASE_DIR)


class TheLedgerRecordsOnlyWhatTheRegistryDeclaresTest(TestCase):

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Audited", products=["metering"])

    def test_the_recordable_set_is_the_registrys_less_what_it_withholds(self):
        self.assertEqual(AUDIT_ACTIONS,
                         AUDIT_ACTION_VALUES - AUDIT_ACTION_WITHHELD_VALUES)
        self.assertEqual(AUDIT_RESOURCE_TYPES, AUDIT_RESOURCE_TYPE_VALUES)
        self.assertIn(WITHHELD, AUDIT_ACTION_VALUES)
        self.assertNotIn(WITHHELD, AUDIT_ACTIONS)

    def test_the_withheld_action_is_refused_by_name_and_writes_nothing(self):
        with self.assertRaisesRegex(ValueError, "withheld"):
            record(action=WITHHELD, tenant_id=self.tenant.id,
                   resource_type=AUDIT_RESOURCE_TYPE_API_KEY)
        with self.assertRaisesRegex(ValueError, "unregistered"):
            records_audit(WITHHELD)
        self.assertFalse(AuditRecord.objects.filter(action=WITHHELD).exists())

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
        tenant = Tenant.objects.create(name="Feed", products=["metering"])
        _, raw_key = TenantApiKey.create_key(tenant, label="k")
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
