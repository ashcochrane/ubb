"""The Grouping Field models live under the `grouping_fields` label, on tables
named for them (#259, ADR-0006 §9).

#259 moved the app label and renamed both models and both tables in one
commit. What stays true after it is pinned here: the label the models carry,
and the two table names, spelled out because an implicit name would follow a
model rename silently. G9 in `apps/platform/tests/test_model_naming.py`
derives the same names mechanically.

Before the cutover (#190) this module was `test_app_label_move.py`, which also
pinned the move itself — the replacement chain under the retired label, the
content-type relabel and its reverse, the upgrade and fresh-install plans, and
that the table rename rendered `ALTER TABLE ... RENAME TO` rather than a
rebuild. Those were facts about migrations the squash deleted; a fresh database
creates the two tables under these names directly.

The cutover also named the value table's lookup index and three uniqueness
constraints canonically (#190, ADR-0026 §4): no retired word, and each says
what it holds. They are read out of the installed catalogue below.
"""
from django.db import connection
from django.test import TestCase

from apps.platform.grouping_fields.models import GroupingField, GroupingFieldValue

APP_LABEL = "grouping_fields"

#: The tables, spelled out.
TABLES = ("ubb_grouping_field", "ubb_grouping_field_value")


class AppLabelTest(TestCase):
    def test_models_live_under_the_new_label(self):
        self.assertEqual(GroupingField._meta.app_label, APP_LABEL)
        self.assertEqual(GroupingFieldValue._meta.app_label, APP_LABEL)

    def test_each_table_tracks_its_own_model_name(self):
        # ADR-0006 §9. G9 in test_model_naming.py derives the same names
        # mechanically; these are spelled out because an implicit table name
        # would follow a model rename silently.
        self.assertEqual(GroupingField._meta.db_table, TABLES[0])
        self.assertEqual(GroupingFieldValue._meta.db_table, TABLES[1])


class TheCanonicalNamesAreInstalledTest(TestCase):
    """What the fresh initial set installs, read from PostgreSQL rather than
    from the models, so a name the migration and the model disagreed on would
    show here."""

    def test_the_value_index_is_the_concise_canonical_one(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT indexdef FROM pg_indexes WHERE tablename = %s "
                "AND indexname = %s", [TABLES[1], "idx_grouping_value_tenant_key"])
            (definition,) = cursor.fetchone()
        self.assertIn("btree (tenant_id, key)", definition)

    def test_the_uniqueness_rules_carry_the_grouping_field_name(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT conname FROM pg_constraint WHERE conrelid IN "
                "(%s::regclass, %s::regclass) AND contype = 'u'", list(TABLES))
            names = {name for (name,) in cursor.fetchall()}
        self.assertEqual(names, {"uq_grouping_field_key", "uq_grouping_field_slot",
                                 "uq_grouping_field_value"})
