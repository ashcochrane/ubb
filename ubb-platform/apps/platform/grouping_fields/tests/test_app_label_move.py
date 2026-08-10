"""The app label moved and both models were renamed, at no cost to a row (#259).

Three things happen in one commit and each has its own way of losing data:

1. **The app label moved.** A label is the key `django_migrations` is written
   under, so without a replacement chain every migration in this app reads as
   unapplied on an existing database and Django tries to CREATE tables that are
   already there. `0001_initial` carries a 1:1 `replaces` pointing at its
   old-label counterpart, exactly as `apps/platform/work` does (#196).
2. **The content types still point at the old label.** Nothing in a replaced
   chain executes, so the rows sit under the retired label while `post_migrate`
   adds a second set under the new one — leaving every admin log entry and
   permission attached to the stale pair. `0002` re-labels them in place, and it
   must run BEFORE the model renames: `contenttypes` injects its own
   `RenameContentType` after each `RenameModel`, and that lookup is keyed on the
   *new* app label.
3. **Both tables were renamed.** `RenameModel` plus `AlterModelTable` is a
   rename in the database's own terms — `ALTER TABLE ... RENAME TO` carries the
   rows, the primary key, every foreign key pointing in, the indexes, the
   constraints and the sequences with it. A create-plus-drop does not, and
   ADR-0007 §1 refuses one.

So the SQL is read rather than assumed, in both directions. `collect_sql`
renders what the migration would run without running it, which is the only way
to assert "this renames and does not rebuild" as a fact about the database
instead of a fact about the operations list.

**This module spells the retired app label**, because pinning the replacement
chain means naming what is replaced. That is the same reason
`events/tests/test_webhook_event_rename.py` spells thirteen retired event names,
and it puts this file in the same declared sweep exclusion.
"""
import importlib
from unittest import mock

from django.apps import apps as global_apps
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db import migrations as operations
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder
from django.test import TestCase

from apps.platform.grouping_fields.models import GroupingField, GroupingFieldValue

APP_LABEL = "grouping_fields"
OLD_APP_LABEL = "dimensions"

#: What existed under the old label. Every one must keep a replacement entry or
#: an upgrade re-runs it against tables that already exist.
HISTORICAL_MIGRATIONS = ["0001_initial"]
LAST_HISTORICAL = HISTORICAL_MIGRATIONS[-1]

RELABEL_MIGRATION = "0002_rename_app_label_content_types"
RENAME_MIGRATION = "0003_the_grouping_field_takes_its_name"

RELABEL = importlib.import_module(
    f"apps.platform.grouping_fields.migrations.{RELABEL_MIGRATION}")

#: The renamed tables, spelled out. The move is safe only because these are
#: explicit: an implicit table name would have followed the model rename
#: silently, and Django would have rebuilt rather than renamed.
OLD_TABLES = ("ubb_dimension_def", "ubb_dimension_value")
NEW_TABLES = ("ubb_grouping_field", "ubb_grouping_field_value")

#: Operations that would cost rows, keys or indexes. `AlterModelTable` is a
#: rename; these are not, and none of them belongs in a rename migration.
DESTRUCTIVE = (
    operations.CreateModel, operations.DeleteModel,
    operations.AddField, operations.RemoveField,
    operations.AddConstraint, operations.RemoveConstraint,
    operations.AddIndex, operations.RemoveIndex,
    operations.RunSQL,
)


def _built_as_if_applied(cls, applied_keys):
    """Build `cls` against a database that recorded exactly `applied_keys`.

    Both the loader and the executor read the history once, on construction, so
    patching the recorder for that call is enough to ask what either would
    conclude about a database this repository does not have to hand.
    """
    recorded = {key: mock.Mock() for key in applied_keys}
    with mock.patch.object(
        MigrationRecorder, "applied_migrations", return_value=recorded
    ):
        return cls(connection)


def _loader_with_applied(applied_keys):
    return _built_as_if_applied(MigrationLoader, applied_keys)


def _executor_with_applied(applied_keys):
    return _built_as_if_applied(MigrationExecutor, applied_keys)


class AppLabelTest(TestCase):
    def test_models_live_under_the_new_label(self):
        self.assertEqual(GroupingField._meta.app_label, APP_LABEL)
        self.assertEqual(GroupingFieldValue._meta.app_label, APP_LABEL)

    def test_each_table_tracks_its_own_model_name(self):
        # ADR-0006 §9, and the thing the rename migration has to land on. G9 in
        # test_model_naming.py derives the same names mechanically; these are
        # spelled out because the migration targets them literally.
        self.assertEqual(GroupingField._meta.db_table, NEW_TABLES[0])
        self.assertEqual(GroupingFieldValue._meta.db_table, NEW_TABLES[1])


class ReplacementChainTest(TestCase):
    def setUp(self):
        self.disk = {
            name: migration
            for (app, name), migration in
            _loader_with_applied([]).disk_migrations.items()
            if app == APP_LABEL
        }

    def test_every_historical_migration_replaces_its_own_predecessor(self):
        for name in HISTORICAL_MIGRATIONS:
            with self.subTest(migration=name):
                self.assertIn(name, self.disk)
                self.assertEqual(
                    list(self.disk[name].replaces), [(OLD_APP_LABEL, name)]
                )

    def test_the_chain_is_complete(self):
        # A migration authored under the old label but left out of the list
        # above would re-run on every existing database.
        replacing = {n for n, m in self.disk.items() if m.replaces}
        self.assertEqual(replacing, set(HISTORICAL_MIGRATIONS))

    def test_neither_new_migration_replaces_anything(self):
        # Both have to run on the databases that need them, so both must stay
        # outside the chain — a `replaces` here would skip them on exactly
        # those.
        for name in (RELABEL_MIGRATION, RENAME_MIGRATION):
            with self.subTest(migration=name):
                self.assertFalse(self.disk[name].replaces)

    def test_the_relabel_runs_before_the_model_renames(self):
        """`contenttypes` looks the row up under the NEW label.

        `inject_rename_contenttypes_operations` inserts a `RenameContentType`
        after each `RenameModel`, and it queries `(app_label=grouping_fields,
        model=<old model>)`. On an upgraded database that row is still under the
        retired label until 0002 has run, and the lookup fails silently — so the
        model rename would leave the content type stranded.
        """
        self.assertIn(
            (APP_LABEL, RELABEL_MIGRATION),
            self.disk[RENAME_MIGRATION].dependencies,
        )


class UpgradePathTest(TestCase):
    """A database migrated before the move — old label recorded, tables full."""

    def setUp(self):
        disk = _loader_with_applied([]).disk_migrations
        # Everything a pre-move database would have recorded: every other app's
        # history as-is, and this app's under the label it used to carry.
        self.pre_move_history = [key for key in disk if key[0] != APP_LABEL]
        self.pre_move_history += [
            (OLD_APP_LABEL, name) for name in HISTORICAL_MIGRATIONS
        ]

    def test_the_historical_chain_resolves_as_already_applied(self):
        # This is the mechanism the tables depend on: the loader reads the old
        # label's history and concludes the new label is already applied.
        loader = _loader_with_applied(self.pre_move_history)

        for name in HISTORICAL_MIGRATIONS:
            with self.subTest(migration=name):
                self.assertIn((APP_LABEL, name), loader.applied_migrations)

    def test_an_upgrade_runs_only_the_relabel_and_the_rename(self):
        # Nothing re-creates a table: the whole historical chain is already
        # applied, so the only work left is the two migrations this commit adds.
        executor = _executor_with_applied(self.pre_move_history)

        plan = executor.migration_plan([(APP_LABEL, RENAME_MIGRATION)])

        self.assertEqual(
            [(m.app_label, m.name) for m, _backwards in plan],
            [(APP_LABEL, RELABEL_MIGRATION), (APP_LABEL, RENAME_MIGRATION)],
        )


class FreshInstallTest(TestCase):
    """The negative control: on an empty database everything must still run."""

    def test_nothing_is_mistaken_for_applied(self):
        loader = _loader_with_applied([])

        for name in HISTORICAL_MIGRATIONS:
            with self.subTest(migration=name):
                self.assertNotIn((APP_LABEL, name), loader.applied_migrations)

    def test_a_fresh_database_still_builds_the_schema(self):
        # Without this, "only two migrations ran" would also pass on a database
        # that has no tables at all.
        executor = _executor_with_applied([])

        plan = executor.migration_plan([(APP_LABEL, RENAME_MIGRATION)])
        planned = [m.name for m, _backwards in plan if m.app_label == APP_LABEL]

        self.assertEqual(
            planned,
            HISTORICAL_MIGRATIONS + [RELABEL_MIGRATION, RENAME_MIGRATION],
        )


class RenameIsARenameTest(TestCase):
    """The migration moves the tables; it does not rebuild them."""

    def setUp(self):
        self.loader = _loader_with_applied([])
        self.migration = self.loader.get_migration(APP_LABEL, RENAME_MIGRATION)

    def _sql(self, *, backwards):
        """What this migration would run, without running it.

        The same entry point `manage.py sqlmigrate` uses, so this reads the
        real renderer rather than a second opinion about it.
        """
        return "\n".join(
            self.loader.collect_sql([(self.migration, backwards)]))

    def test_it_carries_no_operation_that_would_cost_a_row(self):
        offenders = sorted(type(op).__name__ for op in self.migration.operations
                           if isinstance(op, DESTRUCTIVE))
        self.assertEqual(offenders, [], "a rename migration may not drop or "
                                        "create a table, column or constraint")

    def test_both_models_are_renamed_rather_than_replaced(self):
        renamed = {(op.old_name, op.new_name)
                   for op in self.migration.operations
                   if isinstance(op, operations.RenameModel)}
        self.assertEqual(
            renamed,
            {("DimensionDef", "GroupingField"),
             ("DimensionValue", "GroupingFieldValue")},
        )

    def test_every_operation_can_be_reversed(self):
        for op in self.migration.operations:
            with self.subTest(operation=type(op).__name__):
                self.assertTrue(op.reversible)

    def test_the_sql_renames_both_tables_in_place(self):
        sql = self._sql(backwards=False)

        for old, new in zip(OLD_TABLES, NEW_TABLES):
            with self.subTest(table=old):
                self.assertIn(f'ALTER TABLE "{old}" RENAME TO "{new}"', sql)

    def test_the_sql_neither_creates_nor_drops_a_table(self):
        # The vacuity guard sits inside this one: an empty `sql` would satisfy
        # both absences, so the rename above is what proves the render is real.
        sql = self._sql(backwards=False)

        self.assertNotIn("CREATE TABLE", sql)
        self.assertNotIn("DROP TABLE", sql)
        self.assertNotIn("DROP CONSTRAINT", sql)
        self.assertNotIn("DROP INDEX", sql)

    def test_the_reverse_puts_both_tables_back(self):
        sql = self._sql(backwards=True)

        for old, new in zip(OLD_TABLES, NEW_TABLES):
            with self.subTest(table=new):
                self.assertIn(f'ALTER TABLE "{new}" RENAME TO "{old}"', sql)


class ContentTypeRelabelTest(TestCase):
    """0002's only executable statement, run against a real database."""

    def _relabel(self):
        RELABEL.forwards(global_apps, None)

    def test_a_row_under_the_retired_label_moves(self):
        ContentType.objects.create(app_label=OLD_APP_LABEL, model="widget")

        self._relabel()

        self.assertFalse(
            ContentType.objects.filter(app_label=OLD_APP_LABEL).exists())
        self.assertTrue(
            ContentType.objects.filter(app_label=APP_LABEL,
                                       model="widget").exists())

    def test_a_row_whose_destination_is_taken_stays_put(self):
        """Re-labelling onto an existing pair would break uniqueness.

        The row left behind keeps whatever admin log entries and permissions
        point at it, now orphaned — which is why the migration logs rather than
        skipping in silence.
        """
        ContentType.objects.create(app_label=OLD_APP_LABEL, model="widget")
        ContentType.objects.create(app_label=APP_LABEL, model="widget")

        self._relabel()

        self.assertTrue(
            ContentType.objects.filter(app_label=OLD_APP_LABEL,
                                       model="widget").exists())

    def test_the_reverse_puts_the_row_back(self):
        ContentType.objects.create(app_label=APP_LABEL, model="widget")

        RELABEL.backwards(global_apps, None)

        self.assertTrue(
            ContentType.objects.filter(app_label=OLD_APP_LABEL,
                                       model="widget").exists())
