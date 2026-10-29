"""THE TWENTY-ONE DATABASE RULES ARE CARRIED, WHOLE, BY THE FRESH INITIAL SET (#190).

The cutover squashed 287 migrations into one generated `0001_initial` per app plus
a hand-written `0002_the_database_rules` in each of the six apps that own a
trigger (ADR-0026). The schema regenerates from the models; the rules do not —
they live outside Django's migration state — so they are carried by hand, and
this module is what holds the hand to the four things the owner and consultant
ruled (2026-10-29, points 1 and 5):

- **every rule is installed, and nothing else is.** The suite's database is built
  by migrating an EMPTY database (pytest-django creates it afresh every run; there
  is no `--reuse-db`), so the exact set asserted here is proof, on every run, that
  the fresh set installs all twenty-one without relying on a database that
  already held them;
- **each body is the carried text**, byte for byte, as installed;
- **each rules migration depends on the schema leaf of every app owning a table
  its SQL reads** — never an assumed `0001` — and every table and column a rule
  reads is created by an ANCESTOR of its rules migration, so the install cannot
  succeed by migration-ordering luck. The mapping is stated below (`READS`) and
  held to the SQL in both directions;
- **each rules migration's reverse removes exactly its rules, and re-applying it
  restores identical definitions.**

That the definitions are the ones the old chain left — `pg_get_functiondef` and
`pg_get_triggerdef` compared between an old-chain database and a fresh one — is
cutover evidence recorded in the pull request rather than a test: the old chain
no longer exists to migrate. What a rule REFUSES is pinned where it always was,
by each rule's own module, through `save()`, `QuerySet.update()` and raw SQL.
"""
import re
from importlib import import_module

from django.apps import apps as django_apps
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.operations.special import RunSQL
from django.test import SimpleTestCase, TestCase

RULES_MIGRATION = "0002_the_database_rules"

#: The six apps that own a database rule, and the package each lives in.
RULE_OWNERS = {
    "pricing": "apps.metering.pricing",
    "usage": "apps.metering.usage",
    "work": "apps.platform.work",
    "event_types": "apps.platform.event_types",
    "tenants": "apps.platform.tenants",
    "code_builder": "apps.platform.code_builder",
}

#: THE STATED MAPPING (§0.3 point 1): each rule, the app whose rules migration
#: installs it, the table it is ON, and every table and column its SQL reads.
#: Held to the SQL below in both directions — a table the SQL names that is not
#: here fails, and so does a qualified column — and to Django's migration state
#: before the rules migration, which only an ancestor can have built. Columns a
#: body reads UNQUALIFIED inside a sub-select (`pricing_mode` and `id` on the
#: parent unit; the activation's `rail`, `environment` and `enabled`) are listed
#: by hand, because no pattern can attribute them; the state check holds them.
READS = {
    "trg_rate_declared_transitions": ("pricing", "ubb_rate", {
        "ubb_rate": ["valid_from", "valid_to"],
    }),
    "trg_rate_names_a_declaration": ("pricing", "ubb_rate", {
        "ubb_rate": ["measurement_id", "undeclared_measurement_key"],
    }),
    "trg_book_publish_declared_transitions": (
        "pricing", "ubb_pricing_book_publish", {
            "ubb_pricing_book_publish": ["declaration_status"],
        }),
    "trg_resolution_run_is_never_edited": ("pricing", "ubb_resolution_run", {
        "ubb_resolution_run": [],
    }),
    "trg_charge_declared_transitions": ("pricing", "ubb_charge", {
        "ubb_charge": [
            "agreed_price_line_id", "amount_micros", "book_version",
            "charged_at", "compensates_id", "currency", "grouping_field_1",
            "grouping_field_10", "grouping_field_2", "grouping_field_3",
            "grouping_field_4", "grouping_field_5", "grouping_field_6",
            "grouping_field_7", "grouping_field_8", "grouping_field_9",
            "idempotency_key", "resolved_at", "task_id", "tenant_id"],
    }),
    "trg_task_price_declared_transitions": ("pricing", "ubb_task_price", {
        "ubb_task_price": ["valid_from", "valid_to"],
    }),
    "trg_posting_declared_transitions": ("usage", "ubb_posting", {
        "ubb_posting": ["claimed_provider_cost_micros", "costing_status",
                        "provider_cost_micros", "unresolved_reason"],
    }),
    "trg_posting_price_transitions": ("usage", "ubb_posting", {
        "ubb_posting": ["billed_cost_micros", "not_applicable_reason",
                        "pricing_status", "pricing_status_reason"],
    }),
    "trg_posting_receipt_sealing": ("usage", "ubb_posting", {
        "ubb_posting": ["pricing_receipt"],
    }),
    "trg_posting_measurement_pruning": ("usage", "ubb_posting_measurement", {
        "ubb_posting": ["costing_status", "id", "pricing_status", "tenant_id"],
        "ubb_posting_measurement": ["posting_id", "prunable_at"],
        "ubb_tenant": ["id", "is_sandbox"],
    }),
    "trg_posting_kind_frozen": ("usage", "ubb_posting", {
        "ubb_posting": ["kind"],
    }),
    "trg_stop_acknowledgement_is_insert_only": (
        "usage", "ubb_stop_acknowledgement", {
            "ubb_posting": ["id", "tenant_id"],
            "ubb_stop_acknowledgement": ["id", "posting_id"],
            "ubb_tenant": ["id", "is_sandbox"],
        }),
    "trg_posting_measurement_released_once": (
        "usage", "ubb_posting_measurement", {
            "ubb_posting_measurement": ["prunable_at"],
        }),
    "trg_task_type_declared_transitions": ("work", "ubb_task_type", {
        "ubb_task_type": ["pricing_mode"],
    }),
    "trg_task_containment_shares_the_pricing_regime": ("work", "ubb_task", {
        "ubb_task": ["id", "parent_id", "pricing_mode"],
    }),
    "trg_task_declared_transitions": ("work", "ubb_task", {
        "ubb_task": [
            "control_family", "control_id", "outcome_reason", "parent_id",
            "reason_code", "reason_detail", "start_absolute_deadline_seconds",
            "start_silence_window_seconds", "status", "task_type",
            "trigger_source"],
    }),
    "trg_event_type_keeps_its_held_names": ("event_types", "ubb_event_type", {
        "ubb_event_type": ["key", "tenant_id"],
        "ubb_quarantined_key": ["event_type_key", "resolution", "tenant_id",
                                "unrecognised"],
    }),
    "trg_payment_rail_activation_declared_transitions": (
        "tenants", "ubb_payment_rail_activation", {
            "ubb_payment_rail_activation": [
                "activated_at", "approved_by", "environment", "evidence",
                "rail"],
        }),
    "trg_payment_rail_activation_is_kept": (
        "tenants", "ubb_payment_rail_activation", {
            "ubb_payment_rail_activation": [],
        }),
    "trg_tenant_money_mode_needs_its_rail": ("tenants", "ubb_tenant", {
        "ubb_payment_rail_activation": ["enabled", "environment", "rail"],
        "ubb_tenant": ["billing_mode", "is_sandbox"],
    }),
    "trg_blueprint_snapshot_declared_transitions": (
        "code_builder", "ubb_blueprint_snapshot", {
            "ubb_blueprint_snapshot": ["configuration_fingerprint", "content",
                                       "tenant_id"],
        }),
}

#: The one deferred constraint trigger (#473 row 3): its semantics are part of
#: the rule, so they are asserted rather than assumed carried.
DEFERRED = {"trg_event_type_keeps_its_held_names"}

TRIGGER = re.compile(r"CREATE (?:CONSTRAINT )?TRIGGER (\w+)")
FUNCTION = re.compile(r"CREATE FUNCTION (\w+)\(\)")
ON_TABLE = re.compile(r"\bON (ubb_\w+)")
BODY = re.compile(r"\$\$(.*)\$\$", re.S)


def rules_migration(app):
    return import_module(f"{RULE_OWNERS[app]}.migrations.{RULES_MIGRATION}")


def carried_rules():
    """`{trigger: (app, function, table, sql)}` out of the six rules migrations."""
    rules = {}
    for app in RULE_OWNERS:
        for operation in rules_migration(app).Migration.operations:
            (sql,) = operation.sql
            trigger = TRIGGER.search(sql).group(1)
            rules[trigger] = (app, FUNCTION.search(sql).group(1),
                              ON_TABLE.search(sql).group(1), sql)
    return rules


def tables_named(sql, tables):
    return {name for name in re.findall(r"\bubb_\w+\b", sql) if name in tables}


def columns_named(sql, table):
    """`{table: {column}}` the SQL names in a way a pattern can attribute: the
    trigger's own row through `OLD.`/`NEW.`, an aliased table through its
    alias, and the column lists a `to_jsonb` diff compares."""
    named = {table: set(re.findall(r"\b(?:OLD|NEW)\.([a-z_][a-z0-9_]*)", sql))}
    for other, alias in re.findall(r"(?:FROM|JOIN)\s+(ubb_\w+)\s+([a-z])\b", sql):
        named.setdefault(other, set()).update(
            re.findall(rf"\b{alias}\.([a-z_][a-z0-9_]*)", sql))
    for listed in re.findall(r"ARRAY\[((?:'[a-z0-9_]+',?\s*)+)\]", sql):
        names = re.findall(r"'([a-z0-9_]+)'", listed)
        if len(names) > 2:  # a column list, not a vocabulary pair
            named[table].update(names)
    return named


def unbuilt_reads(reads, state_models):
    """Every stated (table, column) that the migration state before a rules
    migration does not hold — what an ancestor would have had to create."""
    by_table = {model._meta.db_table: model for model in state_models}
    faults = []
    for table, columns in sorted(reads.items()):
        model = by_table.get(table)
        if model is None:
            faults.append(f"{table} (no ancestor creates the table)")
            continue
        built = {field.column for field in model._meta.concrete_fields}
        faults += [f"{table}.{column}" for column in columns
                   if column not in built]
    return faults


def table_owners():
    return {model._meta.db_table: model._meta.app_label
            for model in django_apps.get_models()}


def schema_leaf(graph, app):
    """The app's last SCHEMA migration in the fresh set — its leaf, or the
    rules migration's parent in the same app where it has one: the node whose
    state holds every column the app's models declare."""
    (leaf,) = graph.leaf_nodes(app)
    if leaf[1] == RULES_MIGRATION:
        (leaf,) = [parent.key for parent in graph.node_map[leaf].parents
                   if parent.key[0] == app]
    return leaf[1]


def wrong_dependencies(app, declared, reads, owners, graph):
    """The dependencies a rules migration must state, against those it does."""
    wanted = {(owners[table], schema_leaf(graph, owners[table]))
              for table in reads}
    wanted.add((app, schema_leaf(graph, app)))
    declared = set(declared)
    return sorted(wanted - declared), sorted(declared - wanted)


# ---------------------------------------------------------------------------
# Installed: exactly the twenty-one, each the carried text
# ---------------------------------------------------------------------------

class TheFreshSetInstallsEveryRuleTest(TestCase):

    def test_the_rules_migrations_carry_exactly_the_stated_rules(self):
        carried = carried_rules()
        self.assertEqual(len(carried), 21)
        self.assertEqual(set(carried), set(READS))
        for trigger, (app, function, table, _sql) in carried.items():
            with self.subTest(rule=trigger):
                self.assertEqual((app, table), READS[trigger][:2])

    def test_each_operation_runs_its_statement_verbatim_and_reverses_itself(self):
        """A list item runs verbatim; a plain string would be split and
        comment-stripped by `sqlparse` — changing the stored body."""
        for app in RULE_OWNERS:
            for operation in rules_migration(app).Migration.operations:
                with self.subTest(app=app):
                    self.assertIsInstance(operation, RunSQL)
                    self.assertIsInstance(operation.sql, list)
                    (sql,) = operation.sql
                    trigger = TRIGGER.search(sql).group(1)
                    function = FUNCTION.search(sql).group(1)
                    table = ON_TABLE.search(sql).group(1)
                    self.assertEqual(operation.reverse_sql, [
                        f"DROP TRIGGER {trigger} ON {table};\n"
                        f"DROP FUNCTION {function}();"])

    def test_the_database_holds_exactly_these_rules(self):
        carried = carried_rules()
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT c.relname, t.tgname, t.tgenabled, t.tgdeferrable,
                       t.tginitdeferred, p.proname
                  FROM pg_trigger t
                  JOIN pg_class c ON c.oid = t.tgrelid
                  JOIN pg_namespace n ON n.oid = c.relnamespace
                  JOIN pg_proc p ON p.oid = t.tgfoid
                 WHERE NOT t.tgisinternal AND n.nspname = 'public'""")
            installed = {row[1]: row for row in cursor.fetchall()}
            cursor.execute("""
                SELECT p.proname FROM pg_proc p
                  JOIN pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname = 'public'""")
            functions = {row[0] for row in cursor.fetchall()}

        self.assertEqual(set(installed), set(carried))
        self.assertEqual(functions, {f for _, f, _, _ in carried.values()})
        for trigger, (_app, function, table, _sql) in carried.items():
            relname, _name, enabled, deferrable, deferred, proname = \
                installed[trigger]
            with self.subTest(rule=trigger):
                self.assertEqual((relname, proname), (table, function))
                self.assertEqual(enabled, "O")
                self.assertEqual((deferrable, deferred),
                                 (trigger in DEFERRED, trigger in DEFERRED))

    def test_each_installed_body_is_the_carried_text(self):
        for trigger, (_app, function, _table, sql) in carried_rules().items():
            with self.subTest(rule=trigger):
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT prosrc FROM pg_proc WHERE proname = %s",
                        [function])
                    (installed,) = cursor.fetchone()
                self.assertEqual(installed, BODY.search(sql).group(1))


# ---------------------------------------------------------------------------
# Dependencies: every read is built by an ancestor, stated exactly
# ---------------------------------------------------------------------------

class TheRulesDependOnWhatTheyReadTest(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.loader = MigrationLoader(None)
        cls.owners = table_owners()

    def test_every_table_a_rule_names_is_in_its_stated_reads(self):
        tables = set(self.owners)
        for trigger, (_app, _f, _table, sql) in carried_rules().items():
            with self.subTest(rule=trigger):
                self.assertEqual(tables_named(sql, tables),
                                 set(READS[trigger][2]))

    def test_every_column_a_rule_names_is_in_its_stated_reads(self):
        for trigger, (_app, _f, table, sql) in carried_rules().items():
            stated = READS[trigger][2]
            for named_table, columns in columns_named(sql, table).items():
                with self.subTest(rule=trigger, table=named_table):
                    self.assertLessEqual(columns, set(stated[named_table]))

    def test_every_read_is_created_by_an_ancestor_of_its_rules_migration(self):
        """The state BEFORE the rules migration holds only what its ancestors
        built, so a read present there cannot be there by ordering luck."""
        for app in RULE_OWNERS:
            state = self.loader.project_state((app, RULES_MIGRATION),
                                              at_end=False)
            models = state.apps.get_models()
            for trigger, (owner, _t, reads) in READS.items():
                if owner != app:
                    continue
                with self.subTest(rule=trigger):
                    self.assertEqual(unbuilt_reads(reads, models), [])

    def test_each_rules_migration_depends_on_exactly_the_leaves_it_reads(self):
        for app in RULE_OWNERS:
            reads = {table for owner, _t, stated in READS.values()
                     if owner == app for table in stated}
            declared = rules_migration(app).Migration.dependencies
            with self.subTest(app=app):
                self.assertEqual(
                    wrong_dependencies(app, declared, reads, self.owners,
                                       self.loader.graph), ([], []))

    def test_the_usage_rules_depend_on_the_tenants_leaf_by_name(self):
        """The one cross-app read, spelled out: two usage rules read
        `ubb_tenant.is_sandbox`, and the usage rules migration names the
        tenants schema leaf itself rather than inheriting it through
        `usage/0001`'s own foreign keys."""
        self.assertIn(("tenants", "0001_initial"),
                      rules_migration("usage").Migration.dependencies)

    # --- negative controls: the checks above fail on what they exist for ----

    def test_negative_control_a_column_no_ancestor_builds_is_reported(self):
        state = self.loader.project_state(("usage", RULES_MIGRATION),
                                          at_end=False)
        faults = unbuilt_reads({"ubb_posting": ["a_column_nobody_built"],
                                "ubb_not_a_table": []},
                               state.apps.get_models())
        self.assertEqual(faults, ["ubb_not_a_table (no ancestor creates the "
                                  "table)", "ubb_posting.a_column_nobody_built"])

    def test_negative_control_a_dependency_left_to_luck_is_reported(self):
        missing, extra = wrong_dependencies(
            "usage", [("usage", "0001_initial")],
            {"ubb_posting", "ubb_tenant"}, self.owners, self.loader.graph)
        self.assertEqual((missing, extra), ([("tenants", "0001_initial")], []))

    def test_negative_control_an_unstated_qualified_column_is_named(self):
        named = columns_named(
            "SELECT p.ghost FROM ubb_posting p WHERE p.id = OLD.posting_id",
            "ubb_posting_measurement")
        self.assertEqual(named, {"ubb_posting_measurement": {"posting_id"},
                                 "ubb_posting": {"ghost", "id"}})


# ---------------------------------------------------------------------------
# Reversible: the reverse takes exactly its rules, the forward restores them
# ---------------------------------------------------------------------------

def installed_definitions():
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT t.tgname, pg_get_triggerdef(t.oid),
                   pg_get_functiondef(t.tgfoid)
              FROM pg_trigger t
              JOIN pg_class c ON c.oid = t.tgrelid
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE NOT t.tgisinternal AND n.nspname = 'public'""")
        return {name: (trigger, function)
                for name, trigger, function in cursor.fetchall()}


class TheRulesMigrationsReverseTest(TestCase):
    """`docs/conventions/django-patterns.md`: a reverse that a test RUNS.

    Each rules migration is unapplied and re-applied through Django's own
    `Migration.unapply` / `apply`, inside the transaction this `TestCase` rolls
    back — Postgres runs the DDL transactionally, so no other test sees a table
    without its rule."""

    def test_each_rules_migration_reverses_and_reinstalls_its_rules(self):
        loader = MigrationLoader(connection)
        before = installed_definitions()
        carried = carried_rules()
        for app in RULE_OWNERS:
            mine = {t for t, (owner, *_rest) in carried.items() if owner == app}
            migration = loader.get_migration(app, RULES_MIGRATION)
            state = loader.project_state((app, RULES_MIGRATION), at_end=True)
            with self.subTest(app=app):
                with connection.schema_editor() as editor:
                    state = migration.unapply(state, editor)
                self.assertEqual(set(installed_definitions()),
                                 set(before) - mine)
                with connection.schema_editor() as editor:
                    migration.apply(state, editor)
                self.assertEqual(installed_definitions(), before)
