"""A draft declared before a book change named its line is given one (#553).

A change names its `line` since `pricing/0032`, and the planner refuses one
that names none. A draft declared before that holds rate changes with no
`line` — a rate was the one line a book held — and left as it was it could
neither be read as a diff nor published. So `0032` gives each of its changes
`line: rate`, and leaves a PUBLISHED record as the history it is.

⚠ THE MIGRATION IS RUN THROUGH DJANGO'S OWN EXECUTOR, back to `0031` and
forward again, inside the test's transaction — as
`apps/metering/usage/tests/test_the_regime_decides_why_a_price_does_not_apply.py`
runs `usage/0047`, and with its `SET CONSTRAINTS ALL IMMEDIATE` for the same
reason. The rows are written in the old shape directly: no route writes a
change without its line any more, which is the point.
"""
import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.metering.pricing.models import PricingBook, PricingBookPublish
from apps.platform.tenants.models import Tenant

BEFORE_IT = ("pricing", "0031_a_delivered_piece_of_work_is_charged_once")
NAMED_BY = ("pricing", "0032_an_agreed_price_is_published_with_provenance")

#: A rate change as a draft held it before a change named its line.
AN_OLD_RATE_CHANGE = {"kind": "add", "measurement_key": "input_tokens",
                      "rate_per_unit_micros": 3, "unit_quantity": 1}


def _migrate_to(target):
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    MigrationExecutor(connection).migrate([target])


def _a_record(book, *changes, published=False):
    now = timezone.now()
    return PricingBookPublish.objects.create(
        tenant=book.tenant, pricing_book=book, effective_at=now,
        declaration_status="published" if published else "draft",
        published_at=now if published else None, changes=list(changes))


@pytest.mark.django_db
class TestADraftOfTheOldShapeIsGivenItsLine:

    def setup_method(self):
        tenant = Tenant.objects.create(name="T", products=["metering"])
        self.book = PricingBook.objects.create(tenant=tenant, key="catalogue",
                                               is_default=True)

    def _through_the_migration(self, *records):
        _migrate_to(BEFORE_IT)
        _migrate_to(NAMED_BY)
        for record in records:
            record.refresh_from_db()

    def test_each_change_of_an_old_draft_names_the_rate_line(self):
        draft = _a_record(self.book, AN_OLD_RATE_CHANGE,
                          {**AN_OLD_RATE_CHANGE, "kind": "retire"})

        self._through_the_migration(draft)

        assert draft.changes == [
            {"line": "rate", **AN_OLD_RATE_CHANGE},
            {"line": "rate", **AN_OLD_RATE_CHANGE, "kind": "retire"}]

    def test_a_change_that_names_its_line_is_left_as_it_is(self):
        an_agreed_price = {"line": "agreed_price", "kind": "add",
                           "task_type": "transcode",
                           "agreed_price_micros": 8_000_000}
        draft = _a_record(self.book, an_agreed_price,
                          {"line": "rate", **AN_OLD_RATE_CHANGE})

        _migrate_to(BEFORE_IT)
        # Back across `0032` the field did not exist; forward, it is named
        # again — and what named its line before is what it named.
        _migrate_to(NAMED_BY)
        draft.refresh_from_db()

        assert [change["line"] for change in draft.changes] == [
            "agreed_price", "rate"]
        assert draft.changes[1] == {"line": "rate", **AN_OLD_RATE_CHANGE}

    def test_a_published_record_is_history_and_is_left_alone(self):
        published = _a_record(self.book, AN_OLD_RATE_CHANGE, published=True)

        self._through_the_migration(published)

        assert published.changes == [AN_OLD_RATE_CHANGE]
