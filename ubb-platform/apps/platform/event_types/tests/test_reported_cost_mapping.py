"""The reported supplier cost mapping, against a real database (#266).

An Event Type costed from a number the supplier reports has one field that
matters more than any other — **where that number comes from** — and until now
every integrator hand-wrote it into a repository UBB never sees. This record is
that field declared.

What is worth testing here is the narrowing. The source vocabulary is shared
with the declared quantities beside it and then cut down, because a cost is not
a quantity:

* **A supplier response requires a path.** A cost read from a response that
  does not say where is a cost read from nowhere.
* **Caller-supplied emits a required runtime parameter.** The generated
  integration must ask for the number, so the declaration has to be able to say
  so.
* **A constant is rejected outright.** A fixed per-call supplier cost is a
  configured cost rule; "reported" cannot mean both "a number that arrives" and
  "a number that never arrives".
* **A derived cost is refused in v1**, as a stated limitation rather than a
  defect: its constraint is "a named, declarative transformation" and that
  transformation vocabulary has no design and no owner.

The arithmetic and the currency comparison are values rather than rows and are
next door in ``test_reported_cost.py``. The structural claims — the mapping is a
SIBLING of the quantities, it holds no amount, and no raw decimal reaches UBB —
are properties of the tree and live in
``apps/platform/tests/test_reported_cost_invariants.py``.
"""
import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.platform.event_types.models import (
    EventType,
    Measurement,
    REPORTED_COST_PARAMETER,
    ReportedCostMapping,
)
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    AMOUNT_REPRESENTATION_MAJOR_UNITS_DECIMAL,
    AMOUNT_REPRESENTATION_MICROS,
    COSTING_METHOD_CALCULATED,
    COSTING_METHOD_REPORTED,
    DECLARATION_STATUS_DRAFT,
    DECLARATION_STATUS_PUBLISHED,
    SOURCE_KIND_CALLER_SUPPLIED,
    SOURCE_KIND_CONSTANT,
    SOURCE_KIND_DERIVED,
    SOURCE_KIND_PROVIDER_RESPONSE,
    SOURCE_SHAPE_ID_GOOGLE_GEMINI_REST_V1,
    UNIT_TOKEN,
)


def _tenant(name="T"):
    return Tenant.objects.create(name=name)


def _event_type(tenant, key="acme.embed", **kwargs):
    kwargs.setdefault("costing_method", COSTING_METHOD_REPORTED)
    return EventType.objects.create(tenant=tenant, key=key, **kwargs)


def _mapping(event_type, **kwargs):
    """A mapping in its commonest shape: read from the response, in dollars."""
    kwargs.setdefault("source_kind", SOURCE_KIND_PROVIDER_RESPONSE)
    kwargs.setdefault("source_path", ["usage", "total_cost"])
    kwargs.setdefault("amount_representation",
                      AMOUNT_REPRESENTATION_MAJOR_UNITS_DECIMAL)
    kwargs.setdefault("currency", "usd")
    return ReportedCostMapping(event_type=event_type, **kwargs)


def _declared(event_type, **kwargs):
    mapping = _mapping(event_type, **kwargs)
    mapping.full_clean()
    mapping.save()
    return mapping


@pytest.mark.django_db
class TestTheMappingIsASiblingNotAQuantity:
    """A Measurement is a quantity with a unit; a reported supplier cost is
    money with a currency. Folding the second into the first would make the
    unit meaningless or force it to mean "currency"."""

    def test_one_event_type_holds_one_mapping(self):
        event_type = _event_type(_tenant())

        mapping = _declared(event_type)

        assert event_type.reported_cost_mapping == mapping
        assert mapping.currency == "usd"

    def test_a_second_mapping_on_one_event_type_is_refused(self):
        """One per Event Type, at the database. Two mappings are two answers to
        what a call cost with no rule for which wins — the shape the exact-
        variant-then-default ladder was deleted for."""
        event_type = _event_type(_tenant())
        _declared(event_type)

        with pytest.raises(IntegrityError), transaction.atomic():
            ReportedCostMapping.objects.create(
                event_type=event_type,
                source_kind=SOURCE_KIND_CALLER_SUPPLIED,
                amount_representation=AMOUNT_REPRESENTATION_MICROS,
                currency="usd")

    def test_it_carries_no_unit_and_no_value_type(self):
        """The two fields that would have arrived if this had been forced into
        the quantity's shape. A unit here would either be meaningless or have to
        mean "currency", and a value type would put money under a caller-set
        unbounded integer."""
        fields = {field.name for field in ReportedCostMapping._meta.get_fields()}

        assert "unit" not in fields
        assert "value_type" not in fields
        # The positive half: what a quantity has and this has instead.
        assert {"unit", "value_type"} <= {f.name for f in Measurement._meta.get_fields()}
        assert "currency" in fields

    def test_the_declared_quantities_are_untouched_by_it(self):
        """A sibling, so declaring one neither requires nor produces a quantity."""
        event_type = _event_type(_tenant())

        _declared(event_type)

        assert list(event_type.measurements.all()) == []


@pytest.mark.django_db
class TestTheSourceVocabularyIsSharedButNarrowed:
    """Four kinds are declared on the concept; two of them are a reported cost."""

    def test_a_supplier_response_requires_a_path(self):
        """A cost read from the response that does not say where in it is the
        undeclared field this whole ticket exists to declare."""
        event_type = _event_type(_tenant())

        with pytest.raises(ValidationError) as refused:
            _mapping(event_type, source_path=[]).full_clean()

        assert "source_path" in refused.value.message_dict

    def test_a_supplier_response_with_a_path_is_accepted(self):
        """The positive control the refusal above is worthless without."""
        event_type = _event_type(_tenant())

        mapping = _declared(event_type, source_path=["usage", "cost"])

        assert mapping.source_path == ["usage", "cost"]

    def test_the_caller_supplied_kind_emits_a_required_runtime_parameter(self):
        """The generated integration cannot read this number anywhere, so it has
        to ask for it — and the declaration is what tells the builder to."""
        event_type = _event_type(_tenant())

        mapping = _declared(event_type, source_kind=SOURCE_KIND_CALLER_SUPPLIED,
                            source_path=[])

        assert mapping.required_runtime_parameters() == (REPORTED_COST_PARAMETER,)

    def test_a_cost_read_from_the_response_asks_the_caller_for_nothing(self):
        """The other half, without which the method above could return the same
        answer for every mapping in the tree."""
        event_type = _event_type(_tenant())

        mapping = _declared(event_type)

        assert mapping.required_runtime_parameters() == ()

    def test_a_caller_supplied_cost_may_not_also_carry_a_path(self):
        """A path on a kind that reads no response would be emitted by nothing —
        the same rule the declared quantity beside it holds."""
        event_type = _event_type(_tenant())

        with pytest.raises(ValidationError) as refused:
            _mapping(event_type, source_kind=SOURCE_KIND_CALLER_SUPPLIED,
                     source_path=["usage", "cost"]).full_clean()

        assert "source_path" in refused.value.message_dict

    def test_a_constant_is_rejected_as_a_reported_cost(self):
        """Permanently, and on the merits rather than for want of design work.

        A fixed per-call supplier cost is a configured cost rule. "Reported"
        cannot mean both "a number that arrives" and "a number that never
        arrives", and admitting the second would make every rule about where the
        number comes from optional.
        """
        event_type = _event_type(_tenant())

        with pytest.raises(ValidationError) as refused:
            _mapping(event_type, source_kind=SOURCE_KIND_CONSTANT,
                     source_path=[]).full_clean()

        message = " ".join(refused.value.message_dict["source_kind"])
        assert "cost rule" in message

    def test_a_derived_cost_is_refused_as_a_stated_v1_limitation(self):
        """Refused at the same boundary as the constant and for a different
        reason, and the message has to say which.

        The value ships registered and unusable. Its constraint is "a named,
        declarative transformation" and that transformation vocabulary has no
        design and no owner — so this is a limitation with a stated shape rather
        than a defect, and a reader must be able to tell it from the permanent
        rejection beside it.
        """
        event_type = _event_type(_tenant())

        with pytest.raises(ValidationError) as refused:
            _mapping(event_type, source_kind=SOURCE_KIND_DERIVED,
                     source_path=[]).full_clean()

        message = " ".join(refused.value.message_dict["source_kind"])
        assert "v1" in message
        assert "transformation" in message
        # The two refusals are not one refusal wearing two hats.
        assert "cost rule" not in message

    def test_the_derived_value_is_still_a_source_kind_the_registry_owns(self):
        """The refusal is at this boundary and nowhere else: a declared quantity
        may still be derived, and this ticket does not retire the value."""
        event_type = _event_type(_tenant(), key="acme.rerank",
                                 costing_method=COSTING_METHOD_CALCULATED)

        quantity = Measurement(event_type=event_type, code="cached_tokens",
                               unit=UNIT_TOKEN, source_kind=SOURCE_KIND_DERIVED)
        quantity.full_clean()

    def test_a_source_kind_that_is_not_one_is_refused(self):
        event_type = _event_type(_tenant())

        with pytest.raises(ValidationError) as refused:
            _mapping(event_type, source_kind="telepathy",
                     source_path=[]).full_clean()

        assert "source_kind" in refused.value.message_dict


@pytest.mark.django_db
class TestWhatTheNumberMeansIsDeclared:
    """The conversion to micros is generated once and exactly, which it can only
    be if the declaration says what the supplier's number represents."""

    def test_the_representation_is_held_by_reference(self):
        event_type = _event_type(_tenant())

        mapping = _declared(event_type,
                            amount_representation=AMOUNT_REPRESENTATION_MICROS)

        assert mapping.amount_representation == AMOUNT_REPRESENTATION_MICROS

    def test_a_representation_ubb_does_not_own_is_refused(self):
        event_type = _event_type(_tenant())

        with pytest.raises(ValidationError) as refused:
            _mapping(event_type,
                     amount_representation="farthings").full_clean()

        assert "amount_representation" in refused.value.message_dict

    def test_an_undeclared_representation_is_refused(self):
        """A number whose meaning is undeclared is the hand-written multiplier
        this record exists to delete, arriving as an empty column."""
        event_type = _event_type(_tenant())

        with pytest.raises(ValidationError):
            _mapping(event_type, amount_representation="").full_clean()


@pytest.mark.django_db
class TestTheCurrencyIsPinnedExactlyOnce:
    """Pinned on the mapping or read from the response, never both and never
    neither — because a cost denominated in nothing is one a reader cannot
    compare to anything."""

    def test_a_fixed_currency_pins_it(self):
        event_type = _event_type(_tenant())

        mapping = _declared(event_type, currency="gbp")

        assert mapping.currency == "gbp"
        assert mapping.currency_path == []

    def test_a_supplier_returned_currency_pins_it_by_path(self):
        event_type = _event_type(_tenant())

        mapping = _declared(event_type, currency="",
                            currency_path=["usage", "currency"])

        assert mapping.currency_path == ["usage", "currency"]

    def test_declaring_both_is_refused(self):
        """Two answers to one question, and the wrong one is always the one
        nobody is looking at."""
        event_type = _event_type(_tenant())

        with pytest.raises(ValidationError):
            _mapping(event_type, currency="usd",
                     currency_path=["usage", "currency"]).full_clean()

    def test_declaring_neither_is_refused(self):
        event_type = _event_type(_tenant())

        with pytest.raises(ValidationError):
            _mapping(event_type, currency="").full_clean()

    def test_the_database_refuses_both_and_neither_too(self):
        """The model-level rule is a courtesy to the ordinary path (ADR-0007 §2)
        and `objects.create` goes round it. This one is a structural fact that
        no growth in the currency table can make false, so the database holds
        it."""
        event_type = _event_type(_tenant())

        with pytest.raises(IntegrityError), transaction.atomic():
            ReportedCostMapping.objects.create(
                event_type=event_type,
                source_kind=SOURCE_KIND_CALLER_SUPPLIED,
                amount_representation=AMOUNT_REPRESENTATION_MICROS,
                currency="usd", currency_path=["usage", "currency"])

    def test_a_currency_ubb_cannot_hold_is_refused(self):
        """UBB holds money in micros of a currency whose minor unit it knows.
        A code with no known minor unit cannot reach Stripe, and a declaration
        that pinned one would be pinning a cost nobody can settle."""
        event_type = _event_type(_tenant())

        with pytest.raises(ValidationError) as refused:
            _mapping(event_type, currency="jpy").full_clean()

        assert "currency" in refused.value.message_dict

    def test_the_capitalised_code_is_refused_by_name_rather_than_by_absence(self):
        """`USD` is a supported currency spelled the way most suppliers spell
        it, and "unsupported" would be a true-sounding message about the wrong
        thing. UBB spells its codes in lower case and says so."""
        event_type = _event_type(_tenant())

        with pytest.raises(ValidationError) as refused:
            _mapping(event_type, currency="USD").full_clean()

        assert "lower case" in " ".join(refused.value.message_dict["currency"])

    def test_a_supplier_returned_currency_needs_a_supplier_read_amount(self):
        """The currency path is read from the response the amount is read from,
        under the one shape the Event Type declares. A mapping that reads no
        response has none to read a currency out of."""
        event_type = _event_type(_tenant())

        with pytest.raises(ValidationError) as refused:
            _mapping(event_type, source_kind=SOURCE_KIND_CALLER_SUPPLIED,
                     source_path=[], currency="",
                     currency_path=["usage", "currency"]).full_clean()

        assert "currency_path" in refused.value.message_dict


@pytest.mark.django_db
class TestThePathsAreStructuredAndAdvisedOn:
    """Both paths are the same kind of thing as a declared quantity's, so they
    get the same grammar and the same advice — and the advice never rewrites."""

    def test_an_expression_is_not_a_path(self):
        event_type = _event_type(_tenant())

        with pytest.raises(ValidationError) as refused:
            _mapping(event_type,
                     source_path=["usage.total_cost"]).full_clean()

        assert "source_path" in refused.value.message_dict

    def test_an_expression_is_not_a_currency_path_either(self):
        event_type = _event_type(_tenant())

        with pytest.raises(ValidationError) as refused:
            _mapping(event_type, currency="",
                     currency_path=["usage['currency']"]).full_clean()

        assert "currency_path" in refused.value.message_dict

    def test_a_path_inconsistent_with_the_declared_shape_is_advised_on(self):
        event_type = _event_type(
            _tenant(), source_shape_id=SOURCE_SHAPE_ID_GOOGLE_GEMINI_REST_V1)

        mapping = _declared(event_type, source_path=["usage_metadata", "cost"])

        advice = mapping.declaration_advisories()
        assert advice
        # Advice, never a substitution: the tenant's own spelling is quoted and
        # what UBB would have written instead appears nowhere.
        assert "usage_metadata" in " ".join(advice)
        assert "usageMetadata" not in " ".join(advice)

    def test_the_currency_path_is_advised_on_too(self):
        event_type = _event_type(
            _tenant(), source_shape_id=SOURCE_SHAPE_ID_GOOGLE_GEMINI_REST_V1)

        mapping = _declared(event_type, source_path=["cost"], currency="",
                            currency_path=["usage_metadata", "currency"])

        assert any("usage_metadata" in advice
                   for advice in mapping.declaration_advisories())

    def test_a_consistent_declaration_is_advised_on_not_at_all(self):
        event_type = _event_type(
            _tenant(), source_shape_id=SOURCE_SHAPE_ID_GOOGLE_GEMINI_REST_V1)

        mapping = _declared(event_type, source_path=["usageMetadata", "cost"])

        assert mapping.declaration_advisories() == ()


@pytest.mark.django_db
class TestPublicationPinsTheMapping:
    """An incorrect mapping produces an incorrect COGS, so the mapping is part
    of what publication pins — and a change to it is a revised publication
    rather than a silent reinterpretation of code already deployed."""

    def test_a_reported_declaration_publishes_once_its_mapping_is_there(self):
        event_type = _event_type(_tenant())
        assert event_type.publication_blockers()

        _declared(event_type)

        event_type.refresh_from_db()
        assert event_type.publication_blockers() == ()
        event_type.publish()
        assert event_type.declaration_status == DECLARATION_STATUS_PUBLISHED

    def test_changing_the_mapping_returns_the_declaration_to_draft(self):
        event_type = _event_type(_tenant())
        mapping = _declared(event_type)
        event_type.refresh_from_db()
        event_type.publish()

        mapping.source_path = ["usage", "billed_cost"]
        mapping.save()

        stored = EventType.objects.get(pk=event_type.pk)
        assert stored.declaration_status == DECLARATION_STATUS_DRAFT
        # The publication the tenant generated against did not move under them.
        assert stored.published_revision == 1

    def test_a_narrowed_save_still_revises_the_publication(self):
        """`update_fields` is widened by whichever pinned elements actually
        changed. Naming one field is the obvious way round a save-time guard,
        and a declaration that stayed published over a changed currency would be
        a live integration reinterpreted in silence."""
        event_type = _event_type(_tenant())
        mapping = _declared(event_type)
        event_type.refresh_from_db()
        event_type.publish()

        mapping.currency = "gbp"
        mapping.save(update_fields=["updated_at"])

        assert EventType.objects.get(pk=event_type.pk).declaration_status \
            == DECLARATION_STATUS_DRAFT
        assert ReportedCostMapping.objects.get(pk=mapping.pk).currency == "gbp"

    def test_a_save_that_changes_nothing_pinned_leaves_it_published(self):
        """The other direction, without which the rule above would be "any save
        un-publishes" — which is a different and much blunter rule."""
        event_type = _event_type(_tenant())
        mapping = _declared(event_type)
        event_type.refresh_from_db()
        event_type.publish()

        ReportedCostMapping.objects.get(pk=mapping.pk).save()

        assert EventType.objects.get(pk=event_type.pk).declaration_status \
            == DECLARATION_STATUS_PUBLISHED

    def test_withdrawing_the_mapping_revises_the_publication_too(self):
        """And leaves the declaration unpublishable, which is the point: the
        code a tenant deployed reads a cost from somewhere this declaration no
        longer describes."""
        event_type = _event_type(_tenant())
        mapping = _declared(event_type)
        event_type.refresh_from_db()
        event_type.publish()

        mapping.delete()

        stored = EventType.objects.get(pk=event_type.pk)
        assert stored.declaration_status == DECLARATION_STATUS_DRAFT
        assert stored.publication_blockers()

    def test_the_mapping_goes_when_its_event_type_does(self):
        """Part of a declaration rather than a record of money that happened —
        so it is deleted with the declaration, not protected from it."""
        event_type = _event_type(_tenant())
        _declared(event_type)

        event_type.delete()

        assert ReportedCostMapping.objects.count() == 0


@pytest.mark.django_db
class TestNothingBehaviouralIsWired:
    """Slice 2 owns the declaration; slice 3 owns every behaviour it selects."""

    def test_a_declared_mapping_resolves_no_cost(self):
        """It sits inert. Nothing reads it, nothing rates against it, and the
        record carries no resolved amount for anything to have written."""
        event_type = _event_type(_tenant())

        mapping = _declared(event_type)

        assert not hasattr(mapping, "resolve_cost")
        assert not any(field.name.endswith("_micros")
                       for field in mapping._meta.get_fields())
