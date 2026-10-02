"""What an Event Type said when it was last published (#573).

A tenant who revises a published declaration has two in play: the one their
deployed integration was generated against, and the one they are editing. The
catalogue's rows are the second — a revision returns the Event Type to draft in
place — so anything that must keep faith with the integration already shipped
cannot read them. This is the read for that: the declaration the CURRENT
publication pinned, whatever has happened to the draft since.

**It never answers with the draft.** Nothing published means ``None``, and that
covers an Event Type that was never published exactly as it covers a key nobody
declared. Falling back to the live rows there would hand a caller a declaration
no integration was ever generated against, labelled as one that was.

**The draft has a read of its own (#576)**, :func:`draft_declaration`, for a
caller that means to see one. It answers in the same shape and says what it is
by claiming no publication, so the two can never be mistaken for each other by
a caller holding only the answer.

**Plain data, for the reason ``costing.py`` next door gives.** A caller needs
what the publication said and has no business holding a record it could save —
least of all this one, where a save would rewrite the past.

**What is here is what publication pins, and nothing else.** Each shape below
carries exactly the elements its model declares in ``PINNED``, and
``tests/test_publication.py`` holds the two to each other. The supplier, the
category, a quantity's display name and its analytics grouping are absent on
purpose: none of them is pinned, so each may change without a new publication,
and the current value on the catalogue is the right one to read. A copy of them
here would be a second answer that goes stale the first time one is corrected.

**Internal.** Not on the tenant contract: the Event Type routes serve the live
declaration, and what consumes this is the composition layer resolving an
integration from published configuration.
"""
from datetime import datetime
from typing import NamedTuple

from .models import MEASUREMENTS, REPORTED_COST_MAPPING, EventType


class PublishedMeasurement(NamedTuple):
    """One declared quantity, as the publication pinned it."""

    code: str
    value_type: str
    unit: str
    required_for_costing: bool
    source_kind: str
    #: Canonical segments, as declared — never rendered here.
    source_path: tuple[str, ...]


class PublishedReportedCostMapping(NamedTuple):
    """Where the supplier's own cost figure is read from, as pinned."""

    source_kind: str
    source_path: tuple[str, ...]
    amount_representation: str
    #: Exactly one of this and `currency_path` is set, as on the record.
    currency: str
    currency_path: tuple[str, ...]


class PublishedDeclaration(NamedTuple):
    """One Event Type's declaration at its current publication."""

    key: str
    costing_method: str
    source_shape_id: str
    source_shape_label: str
    #: Which publication this is, and when it happened. Both are the row's
    #: own: a revision returns the Event Type to draft and moves neither.
    #: `None` only on `draft_declaration`'s answer, which is no publication.
    published_revision: int | None
    published_at: datetime | None
    #: In code order.
    measurements: tuple[PublishedMeasurement, ...]
    #: `None` where the publication pinned no mapping — a different statement
    #: from this whole record being `None`, which is no publication at all.
    reported_cost_mapping: PublishedReportedCostMapping | None


def last_published_declaration(*, tenant, key):
    """What `key` declared for `tenant` at its current publication, or `None`.

    `None` is *nothing published*: the key is not declared, or it is and has
    never been published. A caller that must tell those apart asks the
    catalogue whether the key exists; what this refuses to do is make up the
    difference from a draft.

    One query, on the ``uq_event_type_key`` unique index, and no join: the
    parts beneath the Event Type are not consulted, because they are the draft.
    """
    if not key:
        return None
    row = (EventType.objects.filter(tenant=tenant, key=key)
           .values_list("published_revision", "published_at",
                        "published_declaration").first())
    if row is None:
        return None
    published_revision, published_at, pinned = row
    if pinned is None:
        return None
    return _in_the_reads_shape(pinned, published_revision=published_revision,
                               published_at=published_at)


def draft_declaration(*, tenant, key):
    """What `key` declares for `tenant` NOW, edits and all, or `None` (#576).

    The other read, for the one caller that asks to see a draft on purpose:
    an admin previewing how a proposed declaration would resolve. It is a
    separate function rather than a flag on the read above so that nothing
    reaches a draft by forgetting an argument.

    The same shape, because a preview resolves a draft exactly as a
    publication is resolved — and **it claims no publication**: the revision
    and its date are `None`, whatever the row counts, because what is returned
    is not what any publication said. That is the only place either is
    `None`. `None` for the whole record means the key is not declared.

    Composed by the Event Type's own `_declaration_to_pin`, the function a
    publication keeps its copy from, so the draft read and the published one
    cannot come to disagree about which elements a declaration has.
    """
    if not key:
        return None
    event_type = EventType.objects.filter(tenant=tenant, key=key).first()
    if event_type is None:
        return None
    return _in_the_reads_shape(event_type._declaration_to_pin(),
                               published_revision=None, published_at=None)


def _in_the_reads_shape(pinned, *, published_revision, published_at):
    """A declaration's pinned elements, as the plain data both reads return."""
    # Every element is handed over by NAME, the Event Type's own as much as a
    # part's, so a copy carrying one its shape does not name fails here rather
    # than being read without it.
    own = dict(pinned)
    measurements = own.pop(MEASUREMENTS)
    mapping = own.pop(REPORTED_COST_MAPPING)
    return PublishedDeclaration(
        **own,
        published_revision=published_revision,
        published_at=published_at,
        measurements=tuple(
            PublishedMeasurement(**{**measurement, "source_path": tuple(
                measurement["source_path"])})
            for measurement in measurements),
        reported_cost_mapping=(None if mapping is None else
                               PublishedReportedCostMapping(**{
                                   **mapping,
                                   "source_path": tuple(mapping["source_path"]),
                                   "currency_path": tuple(
                                       mapping["currency_path"])})),
    )
