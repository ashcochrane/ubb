"""What the last publication said, held to the models that decide it (#573).

The lifecycle a tenant drives — publish, revise by editing a part, read — is
asserted through the tenant's own routes, in
``api/v1/tests/test_the_last_published_declaration_stays_readable.py``. What is
here is what a route cannot reach or cannot see:

* **The read's shapes are the models' pinned elements, exactly.** Three tuples
  on three models decide what a publication pins, and three shapes in
  ``publication.py`` are what a reader is handed. Nothing but this module makes
  the second set follow the first.
* **Declarations published before copies were kept.** No route can produce one
  any more, so the rows are written directly — the one place in this ticket
  that is right, because the subject is the migration and not the lifecycle.
* **The order the lifecycle takes its lock in**, which is the whole of why a
  copy cannot be composed from parts that are about to change under it.
"""
from importlib import import_module

import pytest
from django.apps import apps as live_apps
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.platform.event_types.models import (
    DeclarationIncomplete, EventType, Measurement, Provider,
    ReportedCostMapping,
)
from apps.platform.event_types.publication import (
    PublishedDeclaration, PublishedMeasurement, PublishedReportedCostMapping,
    last_published_declaration,
)
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    AMOUNT_REPRESENTATION_MICROS,
    COSTING_METHOD_REPORTED,
    DECLARATION_STATUS_DRAFT,
    DECLARATION_STATUS_PUBLISHED,
    SOURCE_KIND_CALLER_SUPPLIED,
    SOURCE_KIND_PROVIDER_RESPONSE,
    SOURCE_SHAPE_ID_GOOGLE_GENAI_PYTHON_V1,
    SOURCE_SHAPE_ID_OPENAI_RESPONSES_PYTHON_V1,
    UNIT_TOKEN,
)

KEY = "acme.embed"

keep_what_is_published_now = import_module(
    "apps.platform.event_types.migrations."
    "0007_the_last_published_declaration_is_kept").keep_what_is_published_now


def _declared(tenant=None, key=KEY):
    """A `reported` Event Type with one quantity and its mapping, in draft."""
    tenant = tenant or Tenant.objects.create(name="T")
    event_type = EventType.objects.create(
        tenant=tenant, key=key, costing_method=COSTING_METHOD_REPORTED,
        source_shape_id=SOURCE_SHAPE_ID_OPENAI_RESPONSES_PYTHON_V1)
    Measurement.objects.create(
        event_type=event_type, code="input_tokens", unit=UNIT_TOKEN,
        display_name="Input tokens", required_for_costing=True,
        source_kind=SOURCE_KIND_PROVIDER_RESPONSE,
        source_path=["usage", "input_tokens"])
    ReportedCostMapping.objects.create(
        event_type=event_type, source_kind=SOURCE_KIND_CALLER_SUPPLIED,
        amount_representation=AMOUNT_REPRESENTATION_MICROS, currency="usd")
    return EventType.objects.get(pk=event_type.pk)


def _published(tenant=None, key=KEY):
    return _declared(tenant, key).publish()


def _read(event_type):
    return last_published_declaration(tenant=event_type.tenant,
                                      key=event_type.key)


# ---------------------------------------------------------------------------
# The shapes are the pinned elements
# ---------------------------------------------------------------------------

def test_each_shape_carries_exactly_what_its_model_pins():
    """A field that becomes pinned must reach the read, and this is what says so.

    `EventType._declaration_to_pin` composes the copy FROM these tuples, so a
    grown tuple is kept from the next publication on without anyone deciding
    it. The shapes are written out, so they do not follow — and a copy carrying
    an element its shape does not name fails to read at all. Whoever grows a
    tuple therefore owes two things, and this going red is where they find out:
    the element on the shape, and a migration saying what the copies already
    kept are to answer for it.
    """
    lifecycle = ("published_revision", "published_at")
    parts = ("measurements", "reported_cost_mapping")

    assert PublishedDeclaration._fields == (
        *EventType.PINNED, *lifecycle, *parts)
    assert PublishedMeasurement._fields == Measurement.PINNED
    assert PublishedReportedCostMapping._fields == ReportedCostMapping.PINNED


@pytest.mark.django_db
def test_what_is_not_pinned_may_change_without_touching_the_publication():
    """The other half of the same line. A supplier re-filed and a caption
    corrected reach no generated integration, so neither is a revision — and
    neither is in the copy, where it would only be a second answer going
    stale."""
    published = _published()
    before = _read(published)

    quantity = published.measurements.get()
    quantity.display_name = "Prompt tokens"
    quantity.save()
    published.provider = Provider.objects.create(tenant=published.tenant,
                                                 key="openai")
    published.save()

    assert EventType.objects.get(pk=published.pk).declaration_status \
        == DECLARATION_STATUS_PUBLISHED
    assert _read(published) == before


@pytest.mark.django_db
def test_changing_and_publishing_in_one_step_keeps_what_was_published():
    """The natural sequence with no save in between. What gets kept is the
    declaration being published — not the one the row held a moment ago."""
    published = EventType.objects.get(pk=_published().pk)

    published.source_shape_id = SOURCE_SHAPE_ID_GOOGLE_GENAI_PYTHON_V1
    published.publish()

    kept = _read(published)
    assert kept.source_shape_id == SOURCE_SHAPE_ID_GOOGLE_GENAI_PYTHON_V1
    assert kept.published_revision == 2


@pytest.mark.django_db
def test_the_read_is_one_query_and_never_visits_the_parts(
        django_assert_num_queries):
    """The parts beneath an Event Type ARE the draft. A read that joined them
    would be one refactor from answering with them."""
    published = _published()
    tenant = published.tenant

    with django_assert_num_queries(1) as captured:
        last_published_declaration(tenant=tenant, key=KEY)

    statement = captured.captured_queries[0]["sql"]
    assert Measurement._meta.db_table not in statement
    assert ReportedCostMapping._meta.db_table not in statement


# ---------------------------------------------------------------------------
# Declarations published before copies were kept
# ---------------------------------------------------------------------------

def _as_before_copies_were_kept(event_type):
    """The row as a tree without this column would have left it."""
    EventType.objects.filter(pk=event_type.pk).update(
        published_declaration=None)


@pytest.mark.django_db
def test_a_declaration_already_published_is_given_the_copy_it_would_have():
    """Its rows still say what it pinned — nothing has revised it — and no
    later act would fill the copy in: publishing it again moves nothing."""
    published = _published()
    kept = _read(published)
    _as_before_copies_were_kept(published)
    assert _read(published) is None

    keep_what_is_published_now(live_apps, None)

    assert _read(published) == kept
    assert kept.measurements[0].source_path == ("usage", "input_tokens")


@pytest.mark.django_db
def test_a_declaration_revised_before_copies_were_kept_is_not_given_one():
    """What it published was overwritten in place and is gone. Composing a
    copy from the draft would label an unpublished declaration as the
    published one, so it reads as nothing published — and publishing it again
    is what brings a copy back."""
    revised = _published()
    quantity = revised.measurements.get()
    quantity.source_path = ["usage", "prompt_tokens"]
    quantity.save()
    _as_before_copies_were_kept(revised)
    revised = EventType.objects.get(pk=revised.pk)
    assert revised.declaration_status == DECLARATION_STATUS_DRAFT
    assert revised.published_revision == 1

    keep_what_is_published_now(live_apps, None)

    assert _read(revised) is None

    revised.publish()
    again = _read(revised)
    assert again.published_revision == 2
    assert again.measurements[0].source_path == ("usage", "prompt_tokens")


@pytest.mark.django_db
def test_the_backfill_leaves_a_copy_already_kept_alone():
    """Run twice, or run over a tree that has been publishing since: a copy
    that is there was written by the publication and is not recomposed."""
    revised = _published()
    kept = _read(revised)
    quantity = revised.measurements.get()
    quantity.source_path = ["usage", "prompt_tokens"]
    quantity.save()
    # Published once more by a writer that goes round the model, so the row
    # says `published` over parts the copy does not describe — the one state
    # in which recomposing would visibly move it.
    EventType.objects.filter(pk=revised.pk).update(
        declaration_status=DECLARATION_STATUS_PUBLISHED)

    keep_what_is_published_now(live_apps, None)

    assert _read(revised) == kept


# ---------------------------------------------------------------------------
# The lock, and the order it is taken in
# ---------------------------------------------------------------------------

def _statements_touching(captured, table):
    return [(index, query["sql"]) for index, query in enumerate(captured)
            if f'"{table}"' in query["sql"]]


@pytest.mark.django_db
def test_a_publication_locks_its_row_before_it_reads_its_parts():
    """Otherwise the copy is composed from parts another transaction is free
    to change before the row says `published` — and the row would then say it
    over parts the copy does not describe.

    This holds the ORDER, which is what the argument in
    `EventType.revise_declaration` rests on. It does not interleave two
    transactions; the claim that the order is sufficient is that docstring's.
    """
    declared = _declared()

    with CaptureQueriesContext(connection) as captured:
        declared.publish()

    on_the_row = _statements_touching(captured, EventType._meta.db_table)
    locked_at = next(index for index, sql in on_the_row
                     if "FOR UPDATE" in sql)
    for part in (Measurement, ReportedCostMapping):
        read_at = [index for index, _ in
                   _statements_touching(captured, part._meta.db_table)]
        assert read_at, f"{part.__name__} was never read by the publication"
        # The LAST read is the one the copy is composed from. The mapping is
        # also looked at once before the lock, for the ordinary refusal; what
        # is pinned is never taken from that look.
        assert locked_at < max(read_at)
    written_at = next(index for index, sql in on_the_row
                      if sql.startswith("UPDATE"))
    assert locked_at < written_at


@pytest.mark.django_db
def test_a_publication_asks_the_rows_whether_its_mapping_is_still_there():
    """An instance that remembers a mapping is not evidence there is one.

    Withdrawn by a writer this instance never heard from; the ordinary refusal
    reads what the instance holds and passes. Published anyway, the copy would
    be a `reported` declaration with nowhere to read its cost from, kept as
    the thing a tenant's integration is generated against.
    """
    remembering = (EventType.objects.select_related("reported_cost_mapping")
                   .get(pk=_declared().pk))
    assert remembering.publication_blockers() == ()
    ReportedCostMapping.objects.filter(event_type=remembering).delete()

    with pytest.raises(DeclarationIncomplete):
        remembering.publish()

    stored = EventType.objects.get(pk=remembering.pk)
    assert stored.declaration_status == DECLARATION_STATUS_DRAFT
    assert stored.published_revision == 0
    assert _read(stored) is None


@pytest.mark.django_db
def test_a_revision_locks_the_row_before_it_asks_whether_it_is_published():
    """The other side of the same lock. A conditional update against a
    publication still in flight matches nothing and does not wait; a lock
    does."""
    published = _published()
    quantity = published.measurements.get()
    quantity.source_path = ["usage", "prompt_tokens"]

    with CaptureQueriesContext(connection) as captured:
        quantity.save()

    on_the_row = _statements_touching(captured, EventType._meta.db_table)
    locked_at = next(index for index, sql in on_the_row
                     if "FOR UPDATE" in sql)
    returned_to_draft_at = next(index for index, sql in on_the_row
                                if sql.startswith("UPDATE"))
    assert locked_at < returned_to_draft_at
    assert EventType.objects.get(pk=published.pk).declaration_status \
        == DECLARATION_STATUS_DRAFT
