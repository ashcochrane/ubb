"""An agreed price's window is frozen and closed once, by the database (#553,
spec story 28).

`TaskPrice.valid_from` is declared FROZEN and `valid_to` SET_ONCE, exactly as
the rate's two instants are, and `trg_task_price_declared_transitions` holds
them (installed by `pricing/0032` before the cutover, #190; by the pricing
rules migration since, whose reverse is proven centrally in
`apps/platform/tests/test_the_database_rules_are_carried.py`). ADR-0007 §2
asks for the rule across every door, so each refusal
below is driven through `QuerySet.update()`, raw SQL and `save()` — and the
transition-class gate (`apps/platform/tests/test_transition_class_declarations.py`)
covers the two columns by declaration alone, which proves they are NAMED by a
rule; this module is what proves the rule HOLDS.

This is the one module of #553 that writes the table directly: a refusal of a
write outside the publish act can only be shown by making one.
"""
import re
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.metering.pricing.models import TaskPrice
from apps.metering.pricing.tests._helpers import (
    DOORS, RefusalThroughEveryDoorMixin, a_price_for_whole_work,
    database_rules_guarding, through_the_queryset)
from apps.platform.tenants.models import Tenant
from core.transitions import FROZEN, SET_ONCE

TABLE = TaskPrice._meta.db_table
TRIGGER = "trg_task_price_declared_transitions"


def _a_line(**fields):
    tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
    return a_price_for_whole_work(tenant, task_type="transcode",
                                  agreed_price_micros=8_000_000, **fields)


def _closed(**fields):
    return _a_line(valid_to=timezone.now() - timedelta(days=1), **fields)


class TheEffectiveMomentIsFrozenTest(RefusalThroughEveryDoorMixin, TestCase):
    REFUSAL_NAME = "valid_from is declared frozen"

    def test_the_moment_cannot_be_moved_earlier(self):
        self.assert_every_door_refuses(
            _a_line(), valid_from=timezone.now() - timedelta(days=1))

    def test_the_moment_cannot_be_moved_later(self):
        self.assert_every_door_refuses(
            _a_line(), valid_from=timezone.now() + timedelta(days=1))

    def test_the_refusal_names_its_class(self):
        with self.assertRaisesRegex(IntegrityError, FROZEN):
            with transaction.atomic():
                through_the_queryset(
                    _a_line(), valid_from=timezone.now() - timedelta(days=1))


class TheClosingMomentIsSetOnceTest(RefusalThroughEveryDoorMixin, TestCase):
    REFUSAL_NAME = "valid_to is declared set_once"

    def test_an_open_line_can_be_closed_through_every_door(self):
        """The control: a rule refusing every write to the column would pass
        every refusal below, and no agreed price could then be retired."""
        closing = timezone.now()
        for name, door in DOORS:
            with self.subTest(door=name):
                line = _a_line()
                door(line, valid_to=closing)
                line.refresh_from_db()
                self.assertEqual(line.valid_to, closing)

    def test_a_closed_line_cannot_be_closed_at_another_moment(self):
        self.assert_every_door_refuses(_closed(), valid_to=timezone.now())

    def test_a_closed_line_cannot_be_reopened(self):
        self.assert_every_door_refuses(_closed(), valid_to=None)

    def test_the_refusal_names_its_class(self):
        with self.assertRaisesRegex(IntegrityError, SET_ONCE):
            with transaction.atomic():
                through_the_queryset(_closed(), valid_to=None)

    def test_a_column_the_rule_says_nothing_about_still_writes(self):
        """The rule guards two columns, not the row: a fixture that adjusts a
        line's amount (the pin tests do) is not this rule's business."""
        line = _a_line()
        through_the_queryset(line, agreed_price_micros=9_000_000)
        line.refresh_from_db()
        self.assertEqual(line.agreed_price_micros, 9_000_000)


class TheRuleIsATriggerOnThisTableTest(TestCase):
    """Read off the live catalogue: a migration that ran is evidence that a
    file executed, not that a rule is installed."""

    def _the_trigger(self):
        rows = database_rules_guarding(TABLE)
        self.assertEqual({name for name, _, _ in rows}, {TRIGGER})
        return rows[0]

    def test_it_fires_before_each_updated_row_and_never_on_insert(self):
        _, tgtype, _ = self._the_trigger()
        self.assertTrue(tgtype & (1 << 0), "not FOR EACH ROW")
        self.assertTrue(tgtype & (1 << 1), "not BEFORE")
        self.assertTrue(tgtype & (1 << 4), "does not fire on UPDATE")
        self.assertFalse(tgtype & (1 << 2), "fires on INSERT")
        self.assertFalse(tgtype & (1 << 3), "fires on DELETE")

    def test_each_declared_column_is_named_inside_the_refusal_itself(self):
        """With its comments stripped: a comment naming a column satisfies
        "named in the body" for a branch that has been deleted."""
        _, _, body = self._the_trigger()
        executable = "\n".join(re.sub(r"--.*$", "", line)
                               for line in body.splitlines())
        for column in TaskPrice.transition_classes:
            with self.subTest(column=column):
                self.assertIn(f"NEW.{column}", executable)
