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
"""
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
