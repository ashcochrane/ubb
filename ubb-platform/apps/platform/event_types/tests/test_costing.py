"""What the costing read answers, asked directly (#320, #428, #605).

`costing.cost_declaration` is the one read a rating path may make of the
catalogue (`apps/platform/tests/test_event_type_satellite_invariants.py`), and
until #428 it was exercised only through the compute spine's own cases. #428
gave it a fourth fact — WHICH quantity codes the declaration carries — and a
read that grows a fact is worth asking on its own, for two reasons the spine's
cases cannot cover:

* the read's own docstring promises **one query, and it stays one** on the
  hottest write path in the system, and nothing pinned that until now; and
* the fourth fact has an empty case and an absent case that look alike from
  the spine — a declaration carrying no quantities answers an empty set, and
  no declaration at all answers `None` — and the difference is the whole of
  the opt-in rule the join rests on.

**#605 moved the read onto the last publication**, for all four facts at once:
draft changes do not affect production recording. The cases below hold the
four together — a draft revision moves none of them, a publication moves all
of them — and hold the never-published Event Type to the same `None` a key
nobody declared answers, which is what routes it down the undeclared path.
The fixtures publish by default, so every case that does not say otherwise is
reading a publication.
"""
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.platform.event_types.costing import cost_declaration
from apps.platform.event_types.models import (
    EventType, Measurement, ReportedCostMapping)
from apps.platform.event_types.tests._helpers import declares_an_event_type
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    AMOUNT_REPRESENTATION_MICROS,
    COSTING_METHOD_CALCULATED,
    COSTING_METHOD_REPORTED,
    SOURCE_KIND_CALLER_SUPPLIED,
    SOURCE_KIND_PROVIDER_RESPONSE,
    UNIT_TOKEN,
)

KEY = "acme.embed"


def _tenant(name="T"):
    return Tenant.objects.create(name=name)


def _declaration(tenant, *, key=KEY, **facts):
    """`declares_an_event_type` with this module's key as the default."""
    return declares_an_event_type(tenant, key, **facts)


def _facts(declaration):
    """All four facts, so a case can say none moved — or all did."""
    return (declaration.costing_method, declaration.declares_no_cost,
            declaration.reported_cost_source_kind,
            declaration.declared_quantity_codes)


@pytest.mark.django_db
class TestWhichQuantitiesADeclarationCarries:
    """The fourth fact, and the two shapes the spine cannot tell apart."""

    def test_the_declared_codes_are_answered_as_a_set(self):
        tenant = _tenant()
        _declaration(tenant, quantities=("prompt_tokens", "completion_tokens"))

        declaration = cost_declaration(tenant=tenant, key=KEY)

        assert declaration.declared_quantity_codes == frozenset(
            {"prompt_tokens", "completion_tokens"})

    def test_a_declaration_carrying_no_quantity_answers_an_empty_set(self):
        """Empty, and a set — not `None`, and not a set holding a null.

        A publication that pinned no quantity carries an empty list of them,
        and the set read off it must be empty rather than absent: against an
        empty set every real name reads as undeclared, and against `None` the
        registry's opt-in would read as a declaration nobody made.
        """
        tenant = _tenant()
        _declaration(tenant, quantities=())

        declaration = cost_declaration(tenant=tenant, key=KEY)

        assert declaration.declared_quantity_codes == frozenset()
        assert declaration.declares_no_cost

    def test_the_codes_are_the_declarations_own_and_not_the_tenants(self):
        """Declarations are Event-Type-local (#193 §C2), and so is this set.

        The same code beneath another Event Type of the same tenant is a
        different record, and a set that pooled the tenant's catalogue would
        make a name declared ANYWHERE read as declared HERE — which is the
        exact reading the quarantine link exists to refuse.
        """
        tenant = _tenant()
        _declaration(tenant, quantities=("prompt_tokens",))
        _declaration(tenant, key="acme.rerank", quantities=("reasoning_tokens",))

        declaration = cost_declaration(tenant=tenant, key=KEY)

        assert declaration.declared_quantity_codes == frozenset({"prompt_tokens"})

    def test_no_declaration_is_none_and_not_an_empty_declaration(self):
        """The opt-in rule, at the read: absence is a different answer."""
        tenant = _tenant()
        _declaration(_tenant("Other"), quantities=("prompt_tokens",))

        assert cost_declaration(tenant=tenant, key=KEY) is None
        assert cost_declaration(tenant=tenant, key="") is None

    def test_the_other_three_facts_are_unmoved_by_the_fourth(self):
        """The count the no-cost rule reads is now derived from the set, so
        the set arriving must not have moved the rule."""
        tenant = _tenant()
        _declaration(tenant, costing_method=COSTING_METHOD_REPORTED,
                     quantities=("prompt_tokens",), mapping=True)

        declaration = cost_declaration(tenant=tenant, key=KEY)

        assert declaration.costing_method == COSTING_METHOD_REPORTED
        assert not declaration.declares_no_cost
        assert declaration.reported_cost_source_kind == \
            SOURCE_KIND_CALLER_SUPPLIED


@pytest.mark.django_db
class TestTheReadIsTheLastPublication:
    """Draft changes do not affect production recording (#605)."""

    def test_a_draft_revision_moves_none_of_the_four_facts(self):
        """Every fact revised in draft at once, and the read unmoved — then
        published, and every one of them moved. One case for the four because
        the owner ruled them one unit: a read that took one fact from the
        publication and another from the draft fails here whichever it is."""
        tenant = _tenant()
        event_type = _declaration(tenant, costing_method=COSTING_METHOD_REPORTED,
                                  quantities=("prompt_tokens",), mapping=True)
        published = _facts(cost_declaration(tenant=tenant, key=KEY))

        event_type = EventType.objects.get(pk=event_type.pk)
        event_type.costing_method = COSTING_METHOD_CALCULATED
        event_type.save()
        Measurement.objects.create(event_type=event_type, code="cached_tokens",
                                   unit=UNIT_TOKEN,
                                   source_kind=SOURCE_KIND_CALLER_SUPPLIED)
        mapping = ReportedCostMapping.objects.get(event_type=event_type)
        mapping.source_kind = SOURCE_KIND_PROVIDER_RESPONSE
        mapping.source_path = ["usage", "total_cost"]
        mapping.save()

        assert _facts(cost_declaration(tenant=tenant, key=KEY)) == published

        EventType.objects.get(pk=event_type.pk).publish()

        assert _facts(cost_declaration(tenant=tenant, key=KEY)) == (
            COSTING_METHOD_CALCULATED, False, SOURCE_KIND_PROVIDER_RESPONSE,
            frozenset({"prompt_tokens", "cached_tokens"}))

    def test_a_withdrawn_mapping_still_carries_a_cost_until_published(self):
        """The no-cost rule's mapping half, read off the publication: a
        calculated declaration with a published mapping carries a cost, and
        withdrawing the mapping in draft does not make it free."""
        tenant = _tenant()
        event_type = _declaration(tenant, mapping=True)
        assert not cost_declaration(tenant=tenant, key=KEY).declares_no_cost

        ReportedCostMapping.objects.get(event_type=event_type).delete()

        assert not cost_declaration(tenant=tenant, key=KEY).declares_no_cost

        EventType.objects.get(pk=event_type.pk).publish()

        assert cost_declaration(tenant=tenant, key=KEY).declares_no_cost

    def test_declared_and_never_published_answers_what_no_declaration_does(self):
        """The draft is not operational, so the read answers exactly what it
        answers for a key nobody declared — which is what sends a recording
        down the undeclared path rather than a path of its own."""
        tenant = _tenant()
        _declaration(tenant, costing_method=COSTING_METHOD_REPORTED,
                     quantities=("prompt_tokens",), mapping=True,
                     published=False)

        assert cost_declaration(tenant=tenant, key=KEY) == \
            cost_declaration(tenant=tenant, key="nobody.declared")

    def test_a_publication_with_no_kept_copy_reads_as_never_published(self):
        """Published and then revised before #573 kept copies: the row counts
        a publication whose content it no longer holds. Nothing is made up for
        it — it reads as unpublished until it is published again."""
        tenant = _tenant()
        event_type = _declaration(tenant, quantities=("prompt_tokens",))
        EventType.objects.filter(pk=event_type.pk).update(
            published_declaration=None)
        assert EventType.objects.get(pk=event_type.pk).published_revision == 1

        assert cost_declaration(tenant=tenant, key=KEY) is None


@pytest.mark.django_db
class TestOneQueryAndItStaysOne:
    """The module's own promise, pinned — the read sits on the recording path."""

    def test_the_read_is_one_query_whatever_the_declaration_carries(self):
        tenant = _tenant()
        _declaration(tenant, quantities=("prompt_tokens", "completion_tokens"),
                     mapping=True)

        with CaptureQueriesContext(connection) as queries:
            declaration = cost_declaration(tenant=tenant, key=KEY)

        assert len(queries) == 1, [q["sql"] for q in queries]
        assert declaration.declared_quantity_codes == frozenset(
            {"prompt_tokens", "completion_tokens"})
        assert declaration.reported_cost_source_kind == \
            SOURCE_KIND_CALLER_SUPPLIED

    def test_the_read_is_one_query_for_a_bare_declaration_too(self):
        tenant = _tenant()
        _declaration(tenant, quantities=())

        with CaptureQueriesContext(connection) as queries:
            cost_declaration(tenant=tenant, key=KEY)

        assert len(queries) == 1, [q["sql"] for q in queries]

    def test_the_read_never_visits_the_parts(self):
        """The parts beneath an Event Type ARE the draft, so the one query
        must not join them: a read that did would be one refactor from
        answering with them again."""
        tenant = _tenant()
        _declaration(tenant, quantities=("prompt_tokens",), mapping=True)

        with CaptureQueriesContext(connection) as queries:
            cost_declaration(tenant=tenant, key=KEY)

        (statement,) = [q["sql"] for q in queries]
        assert Measurement._meta.db_table not in statement
        assert ReportedCostMapping._meta.db_table not in statement
