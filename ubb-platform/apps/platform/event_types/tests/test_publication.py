"""What the last publication said, held to the models that decide it (#573).

The lifecycle a tenant drives — publish, revise by editing a part, read — is
asserted through the tenant's own routes, in
``api/v1/tests/test_the_last_published_declaration_stays_readable.py``. What is
here is what a route cannot reach or cannot see:

* **The read's shapes are the models' pinned elements, exactly.** Three tuples
  on three models decide what a publication pins, and three shapes in
  ``publication.py`` are what a reader is handed. Nothing but this module makes
  the second set follow the first.
* **The order the lifecycle takes its lock in**, which is the whole of why a
  copy cannot be composed from parts that are about to change under it.

(Before the cutover, #190, this module also drove the two backfills that gave a
declaration published before copies were kept its copy — `event_types/0007` —
and gave a kept copy its supplier — `event_types/0012`. A fresh database holds
no declaration published before either, so every copy is the one `publish`
composes, which the cases below read.)
"""
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from django.utils import timezone

from apps.platform.event_types.models import (
    PROVIDER_KEY, DeclarationIncomplete, EventCategory, EventType, Measurement,
    Provider, ReportedCostMapping,
)
from apps.platform.event_types.publication import (
    PublishedDeclaration, PublishedMeasurement, PublishedReportedCostMapping,
    draft_declaration, last_published_declaration,
)
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    COSTING_METHOD_REPORTED,
    DECLARATION_STATUS_DRAFT,
    DECLARATION_STATUS_PUBLISHED,
    SOURCE_SHAPE_ID_GOOGLE_GENAI_PYTHON_V1,
    UNIT_CALL,
    UNIT_TOKEN,
)

from ._helpers import declares_an_event_type

KEY = "acme.embed"


def _declared(tenant=None, key=KEY):
    """A `reported` Event Type with one quantity and its mapping, in draft."""
    tenant = tenant or Tenant.objects.create(name="T")
    event_type = declares_an_event_type(
        tenant, key, costing_method=COSTING_METHOD_REPORTED,
        quantities=("input_tokens",), mapping=True, published=False)
    return EventType.objects.get(pk=event_type.pk)


def _recount(event_type):
    """Revise the declaration: its one quantity is counted in another unit."""
    quantity = event_type.measurements.get()
    quantity.unit = UNIT_CALL
    quantity.save()


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
    # The one element kept in another form than it is pinned in: the supplier
    # is pinned by its identity and kept by its key, the form recording reads
    # (#572; the consultant's review of #618).
    kept = tuple(PROVIDER_KEY if name == "provider_id" else name
                 for name in EventType.PINNED)

    assert PublishedDeclaration._fields == (*kept, *lifecycle, *parts)
    assert PublishedMeasurement._fields == Measurement.PINNED
    assert PublishedReportedCostMapping._fields == ReportedCostMapping.PINNED


@pytest.mark.django_db
def test_what_is_not_pinned_may_change_without_touching_the_publication():
    """The other half of the same line. A caption corrected and a category
    re-filed reach no generated integration and no money, so neither is a
    revision — and neither is in the copy, where it would only be a second
    answer going stale."""
    published = _published()
    before = _read(published)

    quantity = published.measurements.get()
    quantity.display_name = "Prompt tokens"
    quantity.save()
    published.category = EventCategory.objects.create(
        tenant=published.tenant, key="chat")
    published.save()

    assert EventType.objects.get(pk=published.pk).declaration_status \
        == DECLARATION_STATUS_PUBLISHED
    assert _read(published) == before


def _supplied(published, key="openai"):
    """`published`, re-published naming a supplier of its own."""
    published.provider = Provider.objects.create(tenant=published.tenant,
                                                 key=key)
    published.publish()
    return EventType.objects.get(pk=published.pk)


@pytest.mark.django_db
def test_the_supplier_is_pinned_and_kept_by_its_key():
    """Re-pointing an Event Type at another supplier is a revision (#572,
    #605): recording keeps answering under the supplier that was published,
    until the change is published too."""
    published = _supplied(_published())
    assert _read(published).provider_key == "openai"

    published.provider = Provider.objects.create(tenant=published.tenant,
                                                 key="anthropic")
    published.save()

    assert EventType.objects.get(pk=published.pk).declaration_status \
        == DECLARATION_STATUS_DRAFT
    assert _read(published).provider_key == "openai"
    published.publish()
    assert _read(published).provider_key == "anthropic"


@pytest.mark.django_db
def test_a_supplier_renamed_revises_every_declaration_naming_it():
    """The key is what a publication keeps, so renaming the supplier is a
    change to each declaration naming it — and takes effect when each is
    published again. Retiring one is not: what may be attached next is not
    what a publication says."""
    published = _supplied(_published())
    supplier = published.provider

    supplier.retired_at = timezone.now()
    supplier.save()
    assert EventType.objects.get(pk=published.pk).declaration_status \
        == DECLARATION_STATUS_PUBLISHED

    supplier.key = "openai-eu"
    supplier.save()

    revised = EventType.objects.get(pk=published.pk)
    assert revised.declaration_status == DECLARATION_STATUS_DRAFT
    assert _read(revised).provider_key == "openai"
    revised.publish()
    assert _read(revised).provider_key == "openai-eu"


@pytest.mark.django_db
def test_a_declaration_naming_no_supplier_is_kept_naming_none():
    """`""`, the one spelling of *no supplier* the copy keeps — never a
    missing key, which the read would answer `None` for. Before the cutover
    (#190) this was the form `event_types/0012` wrote into every copy kept
    before the supplier was pinned, held beside that backfill."""
    unsupplied = _published(key="acme.internal")

    assert unsupplied.provider_id is None
    assert EventType.objects.get(
        pk=unsupplied.pk).published_declaration[PROVIDER_KEY] == ""
    assert _read(unsupplied).provider_key == ""


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
def test_a_publication_counts_on_from_the_rows_revision_not_its_own():
    """Two instances of one draft, published one after the other with a
    change between. The second was loaded before the first published, so it
    remembers revision 0 — and writing 1 again would put one number on two
    different declarations."""
    first = _declared()
    second = EventType.objects.get(pk=first.pk)
    first.publish()
    assert _read(first).published_revision == 1

    second.source_shape_id = SOURCE_SHAPE_ID_GOOGLE_GENAI_PYTHON_V1
    second.publish()

    kept = _read(second)
    assert kept.published_revision == 2
    assert kept.source_shape_id == SOURCE_SHAPE_ID_GOOGLE_GENAI_PYTHON_V1


@pytest.mark.django_db
def test_a_publication_pins_the_parts_as_the_rows_hold_them():
    """An instance that prefetched its quantities before one was changed
    still remembers the old one. What it publishes is what is declared NOW —
    a copy composed from the prefetch would pin a declaration nobody
    published."""
    remembering = (EventType.objects.prefetch_related("measurements")
                   .get(pk=_declared().pk))
    assert [m.unit for m in remembering.measurements.all()] == [UNIT_TOKEN]
    _recount(EventType.objects.get(pk=remembering.pk))

    remembering.publish()

    assert [m.unit for m in _read(remembering).measurements] == [UNIT_CALL]


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
    quantity.unit = UNIT_CALL

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


# ---------------------------------------------------------------------------
# The draft has a read of its own (#576)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_the_draft_read_answers_the_edit_and_claims_no_publication():
    """Published, then revised: the two reads answer two declarations. The
    draft one says what the rows say now, and says it is no publication —
    which is how a caller holding only the answer tells them apart."""
    published = _published()
    _recount(published)

    draft = draft_declaration(tenant=published.tenant, key=KEY)
    last = _read(published)

    assert draft.measurements[0].unit == UNIT_CALL
    assert last.measurements[0].unit == UNIT_TOKEN
    assert (draft.published_revision, draft.published_at) == (None, None)
    assert last.published_revision == 1
    # The same shape apart from what was edited and what a draft cannot
    # claim, so a caller resolves a draft exactly as it resolves a
    # publication.
    assert draft._replace(
        published_revision=last.published_revision,
        published_at=last.published_at,
        measurements=last.measurements) == last


@pytest.mark.django_db
def test_the_draft_read_answers_a_declaration_never_published():
    """Where the published read has nothing to say, by design."""
    declared = _declared()

    assert _read(declared) is None
    draft = draft_declaration(tenant=declared.tenant, key=KEY)
    assert (draft.key, draft.costing_method) == (KEY, COSTING_METHOD_REPORTED)
    assert [quantity.code for quantity in draft.measurements] == [
        "input_tokens"]
    assert draft.reported_cost_mapping is not None


@pytest.mark.django_db
def test_the_draft_read_answers_none_for_a_key_nobody_declared():
    tenant = Tenant.objects.create(name="T")

    assert draft_declaration(tenant=tenant, key="not.declared") is None
    assert draft_declaration(tenant=tenant, key="") is None
