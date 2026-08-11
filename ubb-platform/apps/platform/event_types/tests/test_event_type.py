"""The Event Type's declaration lifecycle, exercised against a real database (#262).

The aggregate root the rest of slice 2 hangs off. What is worth testing about it
is not that Django can save a row: it is the four claims the ticket makes about
*publication*, each of which a smaller design breaks silently rather than loudly.

* An incomplete declaration stays in ``draft`` — a half-built mapping never
  reaches a tenant's production integration.
* A change to a published declaration is a **revised publication**, never a
  silent reinterpretation of code a tenant has already generated and deployed.
* Two operational variants of one call are two independent Event Types, never
  one averaged one.
* One active response shape per Event Type, named exactly once.

The structural claims — no grouping axis, no cost amount, exactly one shape
declaration and no relation between two Event Types — are properties of the
*tree* rather than of a row, so they live next door in
``apps/platform/tests/test_event_type_declaration_invariants.py`` where they can
be classified through a real walker with negative controls.
"""
import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.platform.event_types.models import (
    DeclarationIncomplete,
    EventCategory,
    EventType,
    Provider,
    REPORTED_COST_MAPPING,
    ReportedCostMapping,
)
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    AMOUNT_REPRESENTATION_MICROS,
    COSTING_METHOD_CALCULATED,
    COSTING_METHOD_REPORTED,
    DECLARATION_STATUS_DRAFT,
    DECLARATION_STATUS_PUBLISHED,
    SOURCE_KIND_CALLER_SUPPLIED,
    SOURCE_SHAPE_ID_CUSTOM,
    SOURCE_SHAPE_ID_OPENAI_RESPONSES_PYTHON_V1,
)


def _tenant(name="T"):
    return Tenant.objects.create(name=name)


def _event_type(tenant, key="acme.embed", **kwargs):
    kwargs.setdefault("costing_method", COSTING_METHOD_CALCULATED)
    return EventType.objects.create(tenant=tenant, key=key, **kwargs)


def _mapping(event_type):
    """The simplest complete reported-cost mapping: the caller supplies the
    number, already in micros, in a currency pinned here (#266)."""
    return ReportedCostMapping.objects.create(
        event_type=event_type, source_kind=SOURCE_KIND_CALLER_SUPPLIED,
        amount_representation=AMOUNT_REPRESENTATION_MICROS, currency="usd")


@pytest.mark.django_db
class TestTheKeyBelongsToTheTenant:
    """UBB owns the entity and never enumerates the keys (map #137 constraint 5)."""

    def test_a_key_ubb_has_never_heard_of_is_accepted(self):
        t = _tenant()
        declared = _event_type(t, key="internal.nightly-reindex.v2")
        declared.full_clean()
        assert EventType.objects.get(pk=declared.pk).key == "internal.nightly-reindex.v2"

    def test_a_key_is_unique_per_tenant(self):
        t = _tenant()
        _event_type(t, key="acme.embed")
        with pytest.raises(IntegrityError):
            _event_type(t, key="acme.embed")

    def test_two_tenants_may_spell_a_key_the_same_way(self):
        a, b = _tenant("A"), _tenant("B")
        first, second = _event_type(a), _event_type(b)
        assert first.pk != second.pk


@pytest.mark.django_db
class TestBothSatellitesAreOptional:
    """Internal work with no supplier is a normal declaration (#261, #262)."""

    def test_an_event_type_carrying_neither_is_valid(self):
        declared = _event_type(_tenant())
        declared.full_clean()
        assert declared.provider_id is None and declared.category_id is None

    def test_an_event_type_may_carry_both(self):
        t = _tenant()
        provider = Provider.objects.create(tenant=t, key="acme-inference")
        category = EventCategory.objects.create(tenant=t, key="inference")
        declared = _event_type(t, provider=provider, category=category)
        declared.full_clean()

        assert declared.provider_id == provider.pk
        assert declared.category_id == category.pk

    def test_a_supplier_in_use_cannot_be_deleted_out_from_under_a_declaration(self):
        """Retired, never deleted — enforced rather than trusted.

        The Provider's own tests pin that retirement leaves the past readable.
        This is the other half: nothing may take the record away while a
        declaration still points at it, because the delete would leave the
        historical attribution unresolvable.
        """
        t = _tenant()
        provider = Provider.objects.create(tenant=t, key="acme-inference")
        _event_type(t, provider=provider)

        from django.db.models import ProtectedError
        with pytest.raises(ProtectedError):
            provider.delete()


@pytest.mark.django_db
class TestAnIncompleteDeclarationStaysInDraft:
    """A tenant edits in ``draft``; nothing half-built reaches production."""

    def test_a_new_declaration_starts_in_draft(self):
        assert _event_type(_tenant()).declaration_status == DECLARATION_STATUS_DRAFT

    def test_a_calculated_declaration_publishes(self):
        declared = _event_type(_tenant())

        declared.publish()

        assert declared.declaration_status == DECLARATION_STATUS_PUBLISHED
        assert declared.published_revision == 1
        assert declared.published_at is not None
        assert EventType.objects.get(pk=declared.pk).declaration_status \
            == DECLARATION_STATUS_PUBLISHED

    def test_a_reported_declaration_missing_its_mapping_stays_in_draft(self):
        """AC: the mandatory reported-cost mapping is missing, so publication is
        refused and the record stays where a tenant can still edit it.

        The mapping is a record declared beneath the Event Type and it arrives
        in #266 — so today a `reported` declaration is incomplete by
        construction, which is the truth about this tree rather than a stub.
        """
        declared = _event_type(_tenant(), costing_method=COSTING_METHOD_REPORTED)

        with pytest.raises(DeclarationIncomplete) as refused:
            declared.publish()

        assert REPORTED_COST_MAPPING in str(refused.value)
        assert declared.declaration_status == DECLARATION_STATUS_DRAFT
        assert declared.published_revision == 0
        assert EventType.objects.get(pk=declared.pk).declaration_status \
            == DECLARATION_STATUS_DRAFT

    def test_the_blocker_clears_when_the_mapping_is_there(self):
        """The positive control the refusal above is worthless without.

        Without it, a check that returned "incomplete" for every `reported`
        declaration whatever it carried would pass — and the rule under test is
        that publication reads the MAPPING's presence, not the costing method.
        """
        declared = _event_type(_tenant(), costing_method=COSTING_METHOD_REPORTED)
        assert declared.publication_blockers()

        _mapping(declared)

        declared.refresh_from_db()
        assert declared.publication_blockers() == ()
        declared.publish()
        assert declared.declaration_status == DECLARATION_STATUS_PUBLISHED

    def test_presence_is_the_question_because_the_relation_is_one_to_one(self):
        """The shape the rule must not be at the mercy of, now decided.

        A reverse one-to-one answers `None` when absent, which is what makes
        "is it there" one comparison. A to-many would answer with a MANAGER —
        never `None` — and the blocker would clear for every `reported`
        declaration in the tree at once, silently. #266 declared the first
        shape; this is what holds it to that, because the rule above reads
        emptiness and only one of the two shapes expresses emptiness that way.
        """
        relation = EventType._meta.get_field(REPORTED_COST_MAPPING)

        assert relation.one_to_one, (
            f"{REPORTED_COST_MAPPING} is no longer one-to-one, so "
            f"`publication_blockers` is asking a presence question of a "
            f"manager and will answer 'complete' for every reported "
            f"declaration there is")

    def test_the_reported_cost_mapping_pins_the_publication(self):
        """The obligation this file has carried since #262, now payable.

        Publication pins the response shape, the structured paths and the
        reported-cost mapping, because an incorrect mapping produces an
        incorrect supplier cost. `EventType.PINNED` was where that was expected
        to land and it is not where it could: `PINNED` is a tuple of THIS
        record's own field names, read with `getattr`, and the mapping is a row
        beneath it — the same discovery #263 made about the structured paths,
        which pin through `revise_declaration()` instead.

        So the tripwire's mechanism was wrong and its obligation was right, and
        what replaces it asks the obligation directly and behaviourally: change
        the mapping, and the declaration must be back in draft. That is
        strictly more than the name-in-a-tuple check it replaces, which a
        mapping could have satisfied while revising nothing.
        """
        declared = _event_type(_tenant(), costing_method=COSTING_METHOD_REPORTED)
        mapping = _mapping(declared)
        declared.refresh_from_db()
        declared.publish()

        mapping.currency = "gbp"
        mapping.save()

        assert EventType.objects.get(pk=declared.pk).declaration_status \
            == DECLARATION_STATUS_DRAFT, (
            "a changed mapping left the declaration published, so an "
            "integration a tenant already generated and deployed is now a "
            "reading of a contract that moved under it")

    def test_publishing_an_unchanged_declaration_again_pins_nothing_new(self):
        """There is no second declaration to pin, so there is no second revision."""
        declared = _event_type(_tenant())
        declared.publish()

        declared.publish()

        assert declared.published_revision == 1


@pytest.mark.django_db
class TestAChangedDeclarationIsARevisedPublication:
    """Code a tenant has generated and deployed is never quietly reinterpreted."""

    def test_changing_a_pinned_element_returns_the_declaration_to_draft(self):
        declared = _event_type(
            _tenant(), source_shape_id=SOURCE_SHAPE_ID_OPENAI_RESPONSES_PYTHON_V1)
        declared.publish()

        reloaded = EventType.objects.get(pk=declared.pk)
        reloaded.source_shape_id = SOURCE_SHAPE_ID_CUSTOM
        reloaded.source_shape_label = "our own wrapper"
        reloaded.save()

        stored = EventType.objects.get(pk=declared.pk)
        assert stored.declaration_status == DECLARATION_STATUS_DRAFT
        # The publication the tenant generated against did not move under them.
        assert stored.published_revision == 1

    def test_republishing_a_changed_declaration_is_the_next_revision(self):
        declared = _event_type(_tenant())
        declared.publish()

        declared.costing_method = COSTING_METHOD_REPORTED
        _mapping(declared)
        declared.save()
        assert declared.declaration_status == DECLARATION_STATUS_DRAFT

        declared.publish()

        assert declared.declaration_status == DECLARATION_STATUS_PUBLISHED
        assert declared.published_revision == 2

    def test_editing_and_republishing_in_one_step_is_the_next_revision(self):
        """The natural sequence, with no intermediate save: change it, publish it.

        Publication pins what the declaration says now, so this has to reach the
        database as a published revision 2. A `publish` that took "the record is
        already published" as "there is nothing to do" would return a record it
        had neither published nor saved, and say nothing about either.
        """
        declared = _event_type(_tenant())
        declared.publish()

        reloaded = EventType.objects.get(pk=declared.pk)
        reloaded.key = "acme.embed.v2"
        reloaded.publish()

        stored = EventType.objects.get(pk=declared.pk)
        assert stored.key == "acme.embed.v2"
        assert stored.declaration_status == DECLARATION_STATUS_PUBLISHED
        assert stored.published_revision == 2

    def test_naming_the_changed_field_does_not_dodge_the_guard(self):
        """`update_fields` is the obvious way round a save-time rule."""
        declared = _event_type(_tenant())
        declared.publish()

        reloaded = EventType.objects.get(pk=declared.pk)
        reloaded.key = "acme.embed.v2"
        reloaded.save(update_fields=["key"])

        assert EventType.objects.get(pk=declared.pk).declaration_status \
            == DECLARATION_STATUS_DRAFT

    def test_a_deferred_load_does_not_dodge_the_guard_either(self):
        """The careful caller's spelling, which is the one that fails open.

        ``only("key")`` defers the rest of the row, so an instance loaded that
        way never saw the declaration it is about to change — and Django then
        narrows ``update_fields`` to the fields it did load. A guard that took
        its baseline only at load time reads "no baseline" here, which is
        indistinguishable from "nothing changed", and the live publication
        moves underneath the tenant in silence.
        """
        declared = _event_type(_tenant())
        declared.publish()

        deferred = EventType.objects.only("key").get(pk=declared.pk)
        deferred.key = "acme.embed.v2"
        deferred.save()

        stored = EventType.objects.get(pk=declared.pk)
        assert stored.key == "acme.embed.v2"
        assert stored.declaration_status == DECLARATION_STATUS_DRAFT
        assert stored.published_revision == 1

    def test_the_change_that_unpublished_it_is_actually_written(self):
        """Widening `update_fields` for the status alone would invent a state.

        A record reading `draft` because a pinned element changed, while that
        element was never written, is a third state nobody declared — and the
        next save would compare against a baseline the database never held.
        """
        declared = _event_type(_tenant())
        declared.publish()

        reloaded = EventType.objects.get(pk=declared.pk)
        reloaded.key = "acme.embed.v2"
        reloaded.save(update_fields=["published_at"])

        stored = EventType.objects.get(pk=declared.pk)
        assert stored.key == "acme.embed.v2"
        assert stored.declaration_status == DECLARATION_STATUS_DRAFT

    def test_an_unpinned_element_leaves_the_publication_alone(self):
        """The other direction, which a guard that unpublished on any save fails.

        The category reaches no money and appears in no generated integration,
        so re-filing a published Event Type under a different analytics grouping
        cannot invalidate code that was generated from it.
        """
        t = _tenant()
        declared = _event_type(t)
        declared.publish()

        reloaded = EventType.objects.get(pk=declared.pk)
        reloaded.category = EventCategory.objects.create(tenant=t, key="inference")
        reloaded.save()

        stored = EventType.objects.get(pk=declared.pk)
        assert stored.declaration_status == DECLARATION_STATUS_PUBLISHED
        assert stored.published_revision == 1


@pytest.mark.django_db
class TestOperationalVariantsAreTwoEventTypes:
    """A batch endpoint and a standard one are two costable things, not one.

    Variants-are-not-identities was reversed for operational variants:
    declaring the variant separately is the supported shape, because averaging
    two genuinely different supplier costs produces a number that is wrong for
    both.
    """

    def test_two_variants_of_one_call_are_two_independent_declarations(self):
        t = _tenant()
        supplier = Provider.objects.create(tenant=t, key="acme-inference")
        standard = _event_type(t, key="acme.embed", provider=supplier)
        batch = _event_type(t, key="acme.embed.batch", provider=supplier,
                            costing_method=COSTING_METHOD_REPORTED)

        assert standard.pk != batch.pk
        # One supplier, two costing declarations. Nothing averages them, and
        # nothing on either record can even name the other — which is the claim
        # `test_event_type_declaration_invariants.py` holds to the tree.
        assert standard.costing_method != batch.costing_method
        assert standard.provider_id == batch.provider_id

    def test_publishing_one_variant_leaves_the_other_where_it_was(self):
        t = _tenant()
        standard = _event_type(t, key="acme.embed")
        batch = _event_type(t, key="acme.embed.batch")

        standard.publish()

        assert EventType.objects.get(pk=batch.pk).declaration_status \
            == DECLARATION_STATUS_DRAFT
        assert EventType.objects.get(pk=batch.pk).published_revision == 0

    def test_revising_one_variant_does_not_revise_the_other(self):
        t = _tenant()
        standard = _event_type(t, key="acme.embed")
        batch = _event_type(t, key="acme.embed.batch")
        standard.publish()
        batch.publish()

        standard.source_shape_id = SOURCE_SHAPE_ID_OPENAI_RESPONSES_PYTHON_V1
        standard.save()

        assert EventType.objects.get(pk=standard.pk).declaration_status \
            == DECLARATION_STATUS_DRAFT
        assert EventType.objects.get(pk=batch.pk).declaration_status \
            == DECLARATION_STATUS_PUBLISHED


@pytest.mark.django_db
class TestOneActiveResponseShape:
    """The shape is declared once, and named exactly one way.

    A recognised identifier, or a label for a wrapper UBB does not know — never
    both, because two names for one shape are two answers to a question with
    one answer.
    """

    def test_a_recognised_shape_needs_no_label(self):
        declared = _event_type(
            _tenant(), source_shape_id=SOURCE_SHAPE_ID_OPENAI_RESPONSES_PYTHON_V1)
        declared.full_clean()

    def test_a_recognised_shape_may_not_also_carry_a_label(self):
        declared = _event_type(
            _tenant(), source_shape_id=SOURCE_SHAPE_ID_OPENAI_RESPONSES_PYTHON_V1,
            source_shape_label="our own name for it")
        with pytest.raises(ValidationError) as refused:
            declared.full_clean()
        assert "source_shape_label" in refused.value.message_dict

    def test_a_shape_ubb_cannot_validate_against_must_be_named(self):
        declared = _event_type(_tenant(), source_shape_id=SOURCE_SHAPE_ID_CUSTOM)
        with pytest.raises(ValidationError) as refused:
            declared.full_clean()
        assert "source_shape_label" in refused.value.message_dict

    def test_a_wrapper_of_the_tenants_own_is_a_supported_declaration(self):
        declared = _event_type(_tenant(), source_shape_id=SOURCE_SHAPE_ID_CUSTOM,
                               source_shape_label="acme internal client v3")
        declared.full_clean()

    def test_a_shape_ubb_has_never_heard_of_stays_legal(self):
        """ADR-0003: an open concept learning a value is never a rejection.

        It is unrecognised rather than illegal, so it takes a label for the
        same reason `custom` does — UBB validates nothing against it.
        """
        declared = _event_type(_tenant(), source_shape_id="acme.internal.v1",
                               source_shape_label="acme internal client v3")
        declared.full_clean()

    def test_declaring_no_shape_at_all_is_valid(self):
        declared = _event_type(_tenant())
        declared.full_clean()
        assert declared.source_shape_id == "" and declared.source_shape_label == ""

    def test_a_label_with_no_shape_is_refused_by_the_database(self):
        """The half that must survive code that never calls `full_clean`."""
        t = _tenant()
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                EventType.objects.create(
                    tenant=t, key="acme.embed",
                    costing_method=COSTING_METHOD_CALCULATED,
                    source_shape_label="a name for a shape nobody declared")


@pytest.mark.django_db
class TestTheClosedVocabulariesAreHeldToTheirValues:
    """`declaration_status` and the costing method come from the registry.

    The by-reference half is structural — the module imports the generated
    names — and the census gate is what reads it. What a row can still be
    wrong about is a value from outside the set, so that is refused here.
    """

    def test_a_costing_method_outside_the_set_is_refused(self):
        declared = _event_type(_tenant())
        declared.costing_method = "guessed"
        with pytest.raises(ValidationError) as refused:
            declared.full_clean()
        assert "costing_method" in refused.value.message_dict

    def test_a_declaration_status_outside_the_set_is_refused(self):
        declared = _event_type(_tenant())
        declared.declaration_status = "half-published"
        with pytest.raises(ValidationError) as refused:
            declared.full_clean()
        assert "declaration_status" in refused.value.message_dict

    def test_the_database_refuses_them_too(self):
        t = _tenant()
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                EventType.objects.create(tenant=t, key="acme.embed",
                                         costing_method="guessed")
