"""The 'tasks' -> 'work' app-label move must never cost anyone their rows (#196).

A Django app label is the key `django_migrations` is written under. Moving it
would normally make every migration in this app read as unapplied on an existing
database, and Django would try to CREATE tables that are already there.

`0001`-`0011` each carry a 1:1 `replaces` pointing at their old-label
counterpart, so on a populated database the loader resolves the whole chain to
"already applied" and runs no SQL at all — which is what preserves the tables.
These tests pin both halves of that: nothing runs on an upgrade, everything runs
on a fresh install.
"""
from unittest import mock

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder
from django.test import TestCase

from apps.platform.work.models import Task, TaskType

APP_LABEL = "work"
OLD_APP_LABEL = "tasks"

# The migrations that existed under the old label, frozen. Every one must keep a
# replacement entry or an upgrade re-runs it against tables that already exist.
HISTORICAL_MIGRATIONS = [
    "0001_initial",
    "0002_run_billing_owner_id_run_last_event_at_run_task_id_and_more",
    "0003_run_idx_run_owner_status",
    "0004_the_clean_cut_run_to_task",
    "0005_subtask_containment",
    "0006_announce_outbox_id",
    "0007_task_idx_task_active_limited",
    "0008_tasktype",
    "0009_task_subtask_type_task_task_type_and_more",
    "0010_task_dim1_task_dim2_task_dim3_task_dim4_task_dim5_and_more",
    "0011_remove_task_floor_snapshot_micros",
]
LAST_HISTORICAL = HISTORICAL_MIGRATIONS[-1]
CONTENT_TYPE_MIGRATION = "0012_rename_app_label_content_types"


def _built_as_if_applied(cls, applied_keys):
    """Build `cls` against a database that recorded exactly `applied_keys`.

    Both the loader and the executor read the history once, on construction,
    so patching the recorder for that call is enough to ask what either would
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
        self.assertEqual(Task._meta.app_label, APP_LABEL)
        self.assertEqual(TaskType._meta.app_label, APP_LABEL)

    def test_table_names_are_untouched_by_the_move(self):
        # The whole move is safe only because these are explicit and unchanged.
        self.assertEqual(Task._meta.db_table, "ubb_task")
        self.assertEqual(TaskType._meta.db_table, "ubb_task_type")


class ReplacementChainTest(TestCase):
    def setUp(self):
        self.loader = _loader_with_applied([])
        self.disk = {
            name: migration
            for (app, name), migration in self.loader.disk_migrations.items()
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

    def test_the_content_type_migration_does_not_replace(self):
        # It has to run on the databases that need it, so it must stay outside
        # the chain — a `replaces` here would skip it on exactly those.
        self.assertFalse(self.disk[CONTENT_TYPE_MIGRATION].replaces)


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

    def test_the_whole_chain_resolves_as_already_applied(self):
        # This is the mechanism the tables depend on: the loader reads the old
        # label's history and concludes the new label is already applied.
        loader = _loader_with_applied(self.pre_move_history)

        for name in HISTORICAL_MIGRATIONS:
            with self.subTest(migration=name):
                self.assertIn((APP_LABEL, name), loader.applied_migrations)

    def test_an_existing_database_runs_no_schema_migration(self):
        executor = _executor_with_applied(self.pre_move_history)

        plan = executor.migration_plan([(APP_LABEL, LAST_HISTORICAL)])

        # Empty plan means no SQL: no table is renamed, dropped or recreated,
        # so every row, key, index and constraint survives by construction.
        self.assertEqual(plan, [])

    def test_only_the_content_type_relabel_runs_on_an_upgrade(self):
        executor = _executor_with_applied(self.pre_move_history)

        plan = executor.migration_plan([(APP_LABEL, CONTENT_TYPE_MIGRATION)])

        self.assertEqual(
            [(m.app_label, m.name) for m, _backwards in plan],
            [(APP_LABEL, CONTENT_TYPE_MIGRATION)],
        )


class FreshInstallTest(TestCase):
    """The negative control: on an empty database everything must still run."""

    def test_nothing_is_mistaken_for_applied(self):
        loader = _loader_with_applied([])

        for name in HISTORICAL_MIGRATIONS:
            with self.subTest(migration=name):
                self.assertNotIn((APP_LABEL, name), loader.applied_migrations)

    def test_a_fresh_database_still_builds_the_schema(self):
        # Without this, "no migration ran" would also pass on a database that
        # has no tables at all.
        executor = _executor_with_applied([])

        plan = executor.migration_plan([(APP_LABEL, CONTENT_TYPE_MIGRATION)])
        planned = [m.name for m, _backwards in plan if m.app_label == APP_LABEL]

        self.assertEqual(planned, HISTORICAL_MIGRATIONS + [CONTENT_TYPE_MIGRATION])
