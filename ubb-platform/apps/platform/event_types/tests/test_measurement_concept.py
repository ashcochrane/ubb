"""The opt-in grouping, and the three fences that make it worth having (#264).

An analyst wants to add one supplier's quantity to another supplier's
differently-named quantity on one chart — and only when they have said the two
mean the same thing. That is the whole feature. Everything else here is a fence.

* **A matching name never automatically proves equivalence.** Two declarations
  that happen to share a spelling are not grouped unless the tenant said so.
* **A differing name never prevents aggregation.** The opt-in is the entire
  mechanism; spelling is not consulted in either direction.
* **It is analytics-only.** It can never become a costing input, and it can
  never block recording: an event whose declaration carries no grouping records
  exactly as one whose declaration does.

The first two are absences, and an absence is what quietly stops holding when it
lives inside a bigger change — so each is a test that fails if the fence comes
down rather than a sentence in a docstring. The structural half of the third —
that the record carries no money, that nothing but a declaration may point at
it, and that no rating or billing module can even see it — is a property of the
tree and lives in ``apps/platform/tests/test_event_type_declaration_invariants.py``
next door.
"""
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.metering.pricing.tests._helpers import (
    receipt_without_its_per_event_facts)
from apps.metering.usage.models import Posting
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.customers.models import Customer
from apps.platform.event_types.models import (
    EventType,
    Measurement,
    MeasurementConcept,
)
from apps.platform.grouping_fields.models import GroupingField
from apps.platform.grouping_fields.queries import slot_map
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    COSTING_METHOD_CALCULATED,
    DECLARATION_STATUS_PUBLISHED,
    SOURCE_KIND_CALLER_SUPPLIED,
    UNIT_TOKEN,
)


def _tenant(name="T"):
    return Tenant.objects.create(name=name)


def _event_type(tenant, key="acme.embed", **kwargs):
    kwargs.setdefault("costing_method", COSTING_METHOD_CALCULATED)
    return EventType.objects.create(tenant=tenant, key=key, **kwargs)


def _measurement(event_type, code="prompt_tokens", **kwargs):
    kwargs.setdefault("unit", UNIT_TOKEN)
    kwargs.setdefault("source_kind", SOURCE_KIND_CALLER_SUPPLIED)
    return Measurement.objects.create(event_type=event_type, code=code, **kwargs)


def _concept(tenant, key="input_tokens"):
    return MeasurementConcept.objects.create(tenant=tenant, key=key)


@pytest.mark.django_db
class TestSpellingProvesNothing:
    """Fence one: a matching name never automatically proves equivalence."""

    def test_declaring_a_quantity_joins_no_grouping_and_creates_none(self):
        """The opt-in, stated as what happens when nobody opts in.

        This is the tripwire for the tidy-looking change that takes the whole
        feature down: declaring a quantity and quietly ``get_or_create``-ing a
        grouping for its code. It would make every chart in the product agree
        with every other one, by asserting an equivalence no tenant ever
        claimed.
        """
        tenant = _tenant()
        declared = _measurement(_event_type(tenant))

        assert declared.concept_id is None
        assert MeasurementConcept.objects.count() == 0

    def test_two_declarations_sharing_a_code_are_not_grouped(self):
        """The coincidence of spelling, with one side deliberately grouped.

        Both declarations say ``prompt_tokens``. One has been opted in. The
        other is a different quantity that happens to be spelled the same way,
        and the whole point of the opt-in is that UBB cannot tell the two cases
        apart and never guesses: adding them together on a chart is a claim only
        the tenant can make.
        """
        tenant = _tenant()
        grouped = _measurement(_event_type(tenant, key="acme.embed"))
        coincidence = _measurement(_event_type(tenant, key="acme.rerank"))
        assert grouped.code == coincidence.code

        concept = _concept(tenant)
        grouped.concept = concept
        grouped.save()

        coincidence.refresh_from_db()
        assert coincidence.concept_id is None
        assert list(concept.measurements.all()) == [grouped]

    def test_a_second_tenant_may_spell_a_grouping_the_same_way(self):
        """The grouping is tenant-level, so the key is theirs to choose.

        Two tenants using the same obvious English for their own groupings is
        the ordinary case, and a shared uniqueness would make the first tenant
        to declare one own the word.
        """
        first, second = _tenant("first"), _tenant("second")
        here, there = _concept(first), _concept(second)

        assert here.pk != there.pk
        assert here.key == there.key

    def test_one_tenant_may_not_declare_the_same_grouping_twice(self):
        """Two rows with one name are two answers to a question with one."""
        tenant = _tenant()
        _concept(tenant)

        with pytest.raises(IntegrityError):
            with transaction.atomic():
                _concept(tenant)

    def test_a_declaration_may_not_join_another_tenants_grouping(self):
        """Whose quantities these are is not a detail the grouping may blur.

        A grouping reaching across tenants would put one tenant's numbers on
        another tenant's chart, which is the worst outcome available to a
        feature whose entire job is adding quantities together. No database
        constraint can express it — the declaration's tenant is its Event
        Type's, a table away — so it is validated, and ADR-0007 §2 is explicit
        that model-level validation is a courtesy to the ordinary path. What
        makes that acceptable here is that nothing else writes this column: the
        console and the API surface arrive in #267 and go through it.
        """
        mine, theirs = _tenant("mine"), _tenant("theirs")
        declared = _measurement(_event_type(mine))
        declared.concept = _concept(theirs)

        with pytest.raises(ValidationError) as raised:
            declared.full_clean()
        assert "concept" in raised.value.message_dict

    def test_a_grouping_that_names_no_row_is_refused_the_same_way(self):
        """A validator that can raise something else is one every caller wraps.

        Walking the relation to ask whose it is would raise ``DoesNotExist``
        here instead, out of a method whose entire contract is that it raises
        ``ValidationError`` — so the owner is read narrowly and the two ways of
        not being this tenant's grouping arrive as one refusal.
        """
        tenant = _tenant()
        declared = _measurement(_event_type(tenant))
        declared.concept_id = uuid4()

        with pytest.raises(ValidationError) as raised:
            declared.full_clean()
        assert "concept" in raised.value.message_dict


@pytest.mark.django_db
class TestSpellingNeverPrevents:
    """Fence two: a differing name never prevents aggregation."""

    def test_two_declarations_with_different_codes_are_grouped_once_assigned(self):
        """The feature itself, and the reason the opt-in is the mechanism.

        A Gemini integration and an OpenAI integration never have to agree
        about spelling to both be correct — so the day an analyst wants one
        chart across the two, the thing standing in the way must not be that
        one says ``prompt_tokens`` and the other says ``input_tokens``.
        """
        tenant = _tenant()
        gemini = _measurement(_event_type(tenant, key="gemini.generate"),
                              code="prompt_tokens")
        openai = _measurement(_event_type(tenant, key="openai.responses"),
                              code="input_tokens")
        assert gemini.code != openai.code

        concept = _concept(tenant)
        for declared in (gemini, openai):
            declared.concept = concept
            declared.save()

        assert set(concept.measurements.all()) == {gemini, openai}

    def test_the_grouping_spans_event_types_and_stays_one_per_declaration(self):
        """Many declarations to one grouping, and one grouping per declaration.

        The direction matters both ways. A grouping that could hold only one
        declaration would group nothing; a declaration in several groupings
        would make *"which grouping is this quantity in"* a question with
        several answers, and an analyst adding up a chart would get a different
        total depending on which answer the query happened to take.
        """
        tenant = _tenant()
        concept, other = _concept(tenant), _concept(tenant, key="output_tokens")
        first = _measurement(_event_type(tenant, key="gemini.generate"),
                             concept=concept)
        second = _measurement(_event_type(tenant, key="openai.responses"),
                              code="input_tokens", concept=concept)

        assert concept.measurements.count() == 2
        first.concept = other
        first.save()
        first.refresh_from_db()

        assert first.concept_id == other.pk
        assert set(concept.measurements.all()) == {second}

    def test_a_grouping_cannot_be_deleted_out_from_under_a_declaration(self):
        """Retired by unassignment, never by a delete that rewrites the past.

        Deleting a grouping a declaration still points at would silently
        un-group historical numbers — the failure a finance owner finds a
        quarter later and cannot repair. The same rule, and the same reasoning,
        as the supplier next door.
        """
        tenant = _tenant()
        concept = _concept(tenant)
        declared = _measurement(_event_type(tenant), concept=concept)

        with pytest.raises(ProtectedError):
            with transaction.atomic():
                concept.delete()

        declared.concept = None
        declared.save()
        concept.delete()
        assert MeasurementConcept.objects.count() == 0


@pytest.mark.django_db
class TestAnalyticsOnly:
    """Fence three: it can reach no cost, and it can block no recording."""

    def test_grouping_a_published_declaration_leaves_it_published(self):
        """The publication test for "reaches no emitted code".

        A change to what a tenant's generated integration was built against
        returns the declaration to draft — the code, the paths and the noun
        beside each number all do. This does not, and that is analytics-only seen
        from the other side: an analyst re-filing two quantities under one
        heading is not a change to what UBB will accept or to what the
        integration must send. Returning a live integration to draft over it
        would be a cost with nothing on the other side.
        """
        tenant = _tenant()
        event_type = _event_type(tenant)
        declared = _measurement(event_type)
        event_type.publish()
        assert event_type.declaration_status == DECLARATION_STATUS_PUBLISHED

        declared.concept = _concept(tenant)
        declared.save()

        event_type.refresh_from_db()
        assert event_type.declaration_status == DECLARATION_STATUS_PUBLISHED
        assert "concept" not in Measurement.PINNED

    def test_recording_is_identical_with_and_without_a_grouping(self):
        """The fence stated at the only place it can actually be tested.

        Nothing in slice 2 rates against the catalogue, so this passes today by
        construction — which is exactly why it is written now. The day the
        declaration is wired to recording (slice 3), the grouping is the
        attribute most likely to be read on the way past, and reading it is one
        refactor away from an unknown grouping refusing an event. An analytics
        opt-in that can reject a call is not analytics-only.
        """
        tenant = _tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        event_type = _event_type(tenant)
        declared = _measurement(event_type)

        def _record(key):
            # The first four arguments are positional deliberately: the third
            # is spelled with a word this programme has retired, and naming it
            # here would extend a debt a later slice owes rather than pay it.
            return UsageService.record_usage(
                tenant, customer, key, event_type=event_type.key,
                provider_cost_micros=1_000_000)

        ungrouped = _record("before")
        declared.concept = _concept(tenant)
        declared.save()
        grouped = _record("after")

        # Every recorded field, compared whole rather than one at a time: a
        # comparison that named the fields would go on passing when the wiring
        # arrives and adds one.
        #
        # Two things inside the Pricing Receipt are masked, and only two: the
        # subject it names and the instant it resolved as of are per-event by
        # construction (#349), the way `event_id` beside them always was. The
        # rest of the record — both methods, both statuses, the components and
        # the totals — is compared whole, which is where "identical with and
        # without a grouping" actually bites. The helper says which two facts
        # are masked and why; it also addresses the receipt through the model's
        # own constant, for the same reason the first four arguments above are
        # positional.
        def _comparable(result):
            return receipt_without_its_per_event_facts(
                {k: v for k, v in result.items() if k != "event_id"})

        assert _comparable(grouped) == _comparable(ungrouped)
        rows = [Posting.objects.get(id=result["event_id"])
                for result in (ungrouped, grouped)]
        assert [row.event_type for row in rows] == [event_type.key] * 2
        assert len({row.provider_cost_micros for row in rows}) == 1

    def test_recording_succeeds_where_no_grouping_was_ever_declared(self):
        """The other half: the ordinary tenant, who never uses this at all.

        Most tenants will not group anything, and the feature must be invisible
        to them rather than a step they have to skip.
        """
        tenant = _tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        _measurement(_event_type(tenant))

        result = UsageService.record_usage(tenant, customer, "i",
                                           provider_cost_micros=1_000_000)

        assert MeasurementConcept.objects.count() == 0
        assert Posting.objects.filter(id=result["event_id"]).exists()


@pytest.mark.django_db
class TestItConsumesNoSlot:
    """It groups measurement RECORDS, so it is not an axis and holds no slot."""

    def test_declaring_a_grouping_leaves_the_slot_map_untouched(self):
        """The registry next door is a different vocabulary, and a finite one.

        A Grouping Field binds a tenant's key to one of a fixed number of
        physical columns on the posting, and every slot spent is one a real
        analytics axis cannot have. This grouping spends none: it is a relation
        between declarations, and it groups measurement records rather than
        events.
        """
        tenant = _tenant()
        GroupingField.objects.create(tenant=tenant, key="region", slot="grouping_field_1")
        before = slot_map(tenant.id)

        _concept(tenant, key="tokens")

        assert slot_map(tenant.id) == before == {"region": "grouping_field_1"}
        assert GroupingField.objects.filter(tenant=tenant).count() == 1

    def test_the_two_registries_may_share_a_spelling_without_meeting(self):
        """The same English, declared in both, still names two different things.

        A tenant with a ``region`` axis and a ``region`` grouping has said two
        unrelated things, and the moment one leaks into the other both the
        finite slots and the opt-in are wrong.
        """
        tenant = _tenant()
        GroupingField.objects.create(tenant=tenant, key="region", slot="grouping_field_2")
        concept = _concept(tenant, key="region")

        assert slot_map(tenant.id) == {"region": "grouping_field_2"}
        assert "slot" not in {field.name for field
                              in MeasurementConcept._meta.get_fields()}
        assert MeasurementConcept.objects.filter(key="region").count() == 1
        assert concept.measurements.count() == 0
