"""The work app's models live under the `work` label, on tables named
explicitly (#196).

A Django app label is the key `django_migrations` is written under, and an
implicit table name follows the label and the model's name — so a label or a
model that moved would take its table with it. The two tables here are named
explicitly, which is what let #196 move the label without a table moving, and
what keeps every foreign key, index and rule on `ubb_task` addressed by the
name it was written against.

Before the cutover (#190) this module was `test_app_label_move.py`, which also
pinned the replacement chain (`work/0001`–`0011` each replacing its old-label
counterpart) and what an upgraded or a fresh database would plan to run. The
chain left with the squash; a fresh database runs the one initial set.
"""
from django.test import TestCase

from apps.platform.work.models import Task, TaskType

APP_LABEL = "work"


class AppLabelTest(TestCase):
    def test_models_live_under_the_new_label(self):
        self.assertEqual(Task._meta.app_label, APP_LABEL)
        self.assertEqual(TaskType._meta.app_label, APP_LABEL)

    def test_table_names_are_untouched_by_the_move(self):
        # The move was safe only because these are explicit and unchanged.
        self.assertEqual(Task._meta.db_table, "ubb_task")
        self.assertEqual(TaskType._meta.db_table, "ubb_task_type")
