"""The declared quantity, exercised against a real database (#263).

What is worth testing here is not that Django can save a row. It is the four
claims the ticket makes, each of which the shape it replaces got wrong silently:

* **Declarations are Event-Type-local.** The same code on two Event Types is two
  independent records that happen to share a spelling, and neither constrains
  the other.
* **Only a declared quantity may participate in monetary calculation** — so a
  misspelled one is no longer silently free. It stops contributing *and* the
  declaration it failed to match is reported as missing.
* **The value type is enforced.** A quantity declared whole cannot be recorded
  as a fraction, and UBB refuses rather than rounds.
* **The unit is open.** A tenant may declare one UBB has never heard of.

The path grammar, the renderer and the advisory checker are values rather than
rows and are next door in ``test_source_paths.py``. The structural claims — a
Measurement carries no amount and no currency, and no grouping axis — are
properties of the tree and live in
``apps/platform/tests/test_event_type_declaration_invariants.py``.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.platform.event_types.models import (
    EventType,
    Measurement,
    ValueTypeMismatch,
    VALUE_TYPE_DECIMAL,
    VALUE_TYPE_INTEGER,
)
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    COSTING_METHOD_CALCULATED,
    DECLARATION_STATUS_DRAFT,
    DECLARATION_STATUS_PUBLISHED,
    SOURCE_KIND_CALLER_SUPPLIED,
    SOURCE_KIND_CONSTANT,
    SOURCE_KIND_DERIVED,
    SOURCE_KIND_PROVIDER_RESPONSE,
    SOURCE_SHAPE_ID_GOOGLE_GEMINI_REST_V1,
    SOURCE_SHAPE_ID_GOOGLE_GENAI_PYTHON_V1,
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


@pytest.mark.django_db
class TestDeclarationsAreEventTypeLocal:
    """Name-equality was never the correctness boundary."""

    def test_the_same_code_on_two_event_types_is_two_records(self):
        """One tenant's two supplier integrations never have to agree.

        A correctly named declaration mapped to the wrong supplier field is
        wrong, and an oddly named one mapped correctly is right — so the two
        rows below are not a duplicate to be reconciled. They are two answers to
        two different questions that happen to share a spelling.
        """
        tenant = _tenant()
        first = _event_type(tenant, key="acme.embed")
        second = _event_type(tenant, key="acme.rerank")

        here = _measurement(first, source_kind=SOURCE_KIND_PROVIDER_RESPONSE,
                            source_path=["usage", "prompt_tokens"])
        there = _measurement(second, unit="request",
                             source_kind=SOURCE_KIND_CALLER_SUPPLIED)

        assert here.pk != there.pk
        assert Measurement.objects.filter(code="prompt_tokens").count() == 2
        assert here.unit != there.unit
        assert here.source_kind != there.source_kind

    def test_neither_constrains_the_other(self):
        """Changing one leaves the other exactly where it was."""
        tenant = _tenant()
        first, second = (_event_type(tenant, key="acme.embed"),
                         _event_type(tenant, key="acme.rerank"))
        here = _measurement(first)
        there = _measurement(second, unit="request")

        here.unit = "second"
        here.value_type = VALUE_TYPE_DECIMAL
        here.save()

        there.refresh_from_db()
        assert there.unit == "request"
        assert there.value_type == VALUE_TYPE_INTEGER

    def test_one_event_type_may_not_declare_a_code_twice(self):
        """The other direction: local does not mean unconstrained.

        Two rows under one Event Type spelling one quantity two ways is the
        ambiguity the whole declaration exists to remove.
        """
        declared = _event_type(_tenant())
        _measurement(declared)

        with pytest.raises(IntegrityError), transaction.atomic():
            _measurement(declared)

    def test_deleting_an_event_type_takes_its_declarations_with_it(self):
        """They are parts of one declaration, not records in their own right."""
        tenant = _tenant()
        declared = _event_type(tenant)
        _measurement(declared)
        _measurement(_event_type(tenant, key="acme.rerank"))

        declared.delete()

        assert Measurement.objects.count() == 1


@pytest.mark.django_db
class TestOnlyADeclaredQuantityReachesACost:
    """The ticket's headline: a misspelled quantity is no longer silently free."""

    def test_a_misspelled_quantity_leaves_the_cost_incomplete(self):
        """It used to hit a `continue` and contribute nothing, with no signal.

        Now it still contributes nothing — and the declaration it failed to
        match is reported as missing, so the event is visibly not fully costed
        instead of silently cheap.
        """
        declared = _event_type(_tenant())
        _measurement(declared, code="prompt_tokens", required_for_costing=True)

        missing = declared.missing_required_measurements({"promt_tokens"})

        assert missing == ("prompt_tokens",)

    def test_a_declared_quantity_that_arrived_is_not_missing(self):
        """The positive control. A check nothing can satisfy is not a check."""
        declared = _event_type(_tenant())
        _measurement(declared, code="prompt_tokens", required_for_costing=True)

        assert declared.missing_required_measurements({"prompt_tokens"}) == ()

    def test_a_quantity_whose_absence_blocks_nothing_is_not_missing(self):
        """The flag is the whole difference between the two states."""
        declared = _event_type(_tenant())
        _measurement(declared, code="cache_reads", required_for_costing=False)

        assert declared.missing_required_measurements(set()) == ()

    def test_a_code_declared_on_a_sibling_does_not_answer_for_this_one(self):
        """Locality, seen from the costing side.

        Declaring `prompt_tokens` on the rerank call does not make it declared
        on the embed call, however identically it is spelled.
        """
        tenant = _tenant()
        here = _event_type(tenant, key="acme.embed")
        there = _event_type(tenant, key="acme.rerank")
        _measurement(here, code="prompt_tokens", required_for_costing=True)
        _measurement(there, code="prompt_tokens", required_for_costing=True)

        assert here.missing_required_measurements(set()) == ("prompt_tokens",)
        assert there.missing_required_measurements({"prompt_tokens"}) == ()

    def test_every_missing_declaration_is_reported_not_only_the_first(self):
        declared = _event_type(_tenant())
        _measurement(declared, code="prompt_tokens", required_for_costing=True)
        _measurement(declared, code="completion_tokens", required_for_costing=True)

        assert declared.missing_required_measurements(set()) == (
            "completion_tokens", "prompt_tokens")


@pytest.mark.django_db
class TestTheValueTypeIsEnforced:
    """A count that must be whole cannot arrive as a fraction."""

    def test_a_whole_declaration_refuses_a_fraction(self):
        declared = _measurement(_event_type(_tenant()),
                                value_type=VALUE_TYPE_INTEGER)

        with pytest.raises(ValueTypeMismatch):
            declared.validate_value(Decimal("2.5"))

    def test_a_whole_declaration_refuses_a_fraction_however_it_is_spelled(self):
        declared = _measurement(_event_type(_tenant()),
                                value_type=VALUE_TYPE_INTEGER)

        for value in ("2.5", 2.5, Decimal("0.0001")):
            with pytest.raises(ValueTypeMismatch):
                declared.validate_value(value)

    def test_it_refuses_rather_than_rounds(self):
        """The direction is the decision.

        Rounding it, or widening the declaration, are both somebody's
        commercial call — and a quantity quietly rounded at the door is one
        nobody can reconcile back to what the supplier reported.
        """
        declared = _measurement(_event_type(_tenant()),
                                value_type=VALUE_TYPE_INTEGER)

        with pytest.raises(ValueTypeMismatch) as refused:
            declared.validate_value("2.5")

        assert "round" in str(refused.value)

    def test_a_whole_declaration_accepts_a_whole_number_in_any_spelling(self):
        """The positive control, including the trailing zero.

        `Decimal("2.0")` is a whole number written by somebody being careful,
        and a check that read the string instead of the value would refuse it.
        """
        declared = _measurement(_event_type(_tenant()),
                                value_type=VALUE_TYPE_INTEGER)

        for value in (2, "2", Decimal("2"), Decimal("2.0"), 2.0):
            assert declared.validate_value(value) == Decimal("2")

    def test_a_decimal_declaration_accepts_a_fraction(self):
        declared = _measurement(_event_type(_tenant()),
                                value_type=VALUE_TYPE_DECIMAL)

        assert declared.validate_value("2.5") == Decimal("2.5")

    def test_a_flag_is_not_the_number_one(self):
        """`bool` subclasses `int`, so `True` passes every numeric test there is."""
        declared = _measurement(_event_type(_tenant()),
                                value_type=VALUE_TYPE_INTEGER)

        with pytest.raises(ValueTypeMismatch):
            declared.validate_value(True)

    def test_something_that_is_not_a_number_is_refused(self):
        declared = _measurement(_event_type(_tenant()),
                                value_type=VALUE_TYPE_DECIMAL)

        for value in ("plenty", None, [1], float("nan"), float("inf")):
            with pytest.raises(ValueTypeMismatch):
                declared.validate_value(value)

    def test_a_float_is_read_as_the_number_that_was_sent(self):
        """A supplier's `0.1` means a tenth.

        Reading it through its exact binary expansion would be UBB inventing
        seventeen digits of precision nobody sent.
        """
        declared = _measurement(_event_type(_tenant()),
                                value_type=VALUE_TYPE_DECIMAL)

        assert declared.validate_value(0.1) == Decimal("0.1")

    def test_a_value_type_ubb_does_not_own_is_refused(self):
        declared = _measurement(_event_type(_tenant()))
        declared.value_type = "whole"

        with pytest.raises(ValidationError) as refused:
            declared.full_clean()

        assert "value_type" in refused.value.error_dict


@pytest.mark.django_db
class TestTheUnitIsOpen:
    """The quantity a tenant sells is the tenant's to choose."""

    def test_a_unit_ubb_has_never_heard_of_is_accepted(self):
        declared = _measurement(_event_type(_tenant()), unit="rendered-page")
        declared.full_clean()

        assert Measurement.objects.get(pk=declared.pk).unit == "rendered-page"

    def test_a_unit_ubb_has_never_heard_of_draws_no_advice_either(self):
        """Accepted in SILENCE.

        Advising on it would be UBB leaning on a tenant to use UBB's catalogue,
        which is the whole thing an open concept refuses to do.
        """
        declared = _measurement(_event_type(_tenant()), unit="rendered-page")

        assert declared.declaration_advisories() == ()

    def test_one_of_ubbs_own_spellings_draws_no_advice(self):
        declared = _measurement(_event_type(_tenant()), unit=UNIT_TOKEN)

        assert declared.declaration_advisories() == ()

    def test_a_near_miss_is_advised_and_never_corrected(self):
        """`Tokens` and `token` are one noun spelled twice.

        Both are accepted; what is worth saying is that two spellings across two
        declarations read as two different things on one invoice. The advice
        quotes what the tenant wrote — and the column still holds it afterwards.
        """
        declared = _measurement(_event_type(_tenant()), unit="Tokens")

        advice = declared.declaration_advisories()

        assert len(advice) == 1 and "Tokens" in advice[0]
        declared.refresh_from_db()
        assert declared.unit == "Tokens"

    def test_a_quantity_with_no_noun_beside_it_is_refused(self):
        """The one thing an open set can still insist on."""
        declared = _measurement(_event_type(_tenant()))
        declared.unit = "   "

        with pytest.raises(ValidationError) as refused:
            declared.full_clean()

        assert "unit" in refused.value.error_dict

    def test_the_database_refuses_an_undeclared_unit_too(self):
        """ADR-0007 §2: `clean()` is a courtesy, the constraint is the rule."""
        with pytest.raises(IntegrityError), transaction.atomic():
            _measurement(_event_type(_tenant()), unit="")


@pytest.mark.django_db
class TestTheSourceDeclaration:
    """Where the number comes from, and what that obliges."""

    def test_a_source_kind_ubb_does_not_own_is_refused(self):
        declared = _measurement(_event_type(_tenant()))
        declared.source_kind = "telepathy"

        with pytest.raises(ValidationError) as refused:
            declared.full_clean()

        assert "source_kind" in refused.value.error_dict

    def test_the_database_refuses_it_too(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            _measurement(_event_type(_tenant()), source_kind="telepathy")

    def test_a_quantity_read_from_the_response_must_say_where(self):
        declared = _measurement(_event_type(_tenant()),
                                source_kind=SOURCE_KIND_PROVIDER_RESPONSE,
                                source_path=["usage", "prompt_tokens"])
        declared.full_clean()

        declared.source_path = []
        with pytest.raises(ValidationError) as refused:
            declared.full_clean()

        assert "source_path" in refused.value.error_dict

    @pytest.mark.parametrize("kind", [SOURCE_KIND_CALLER_SUPPLIED,
                                      SOURCE_KIND_DERIVED,
                                      SOURCE_KIND_CONSTANT])
    def test_a_quantity_that_reads_no_response_carries_no_path(self, kind):
        """A path on a kind that reads nothing would be emitted by nothing.

        `derived` is the interesting one: a quantity derived from several
        supplier fields needs a named transformation, and the transformation
        vocabulary has no design and no owner (#193 §D4). One path cannot
        express one, so a path here would be a claim this slice cannot honour.
        """
        declared = _measurement(_event_type(_tenant()), source_kind=kind)
        declared.full_clean()

        declared.source_path = ["usage", "prompt_tokens"]
        with pytest.raises(ValidationError) as refused:
            declared.full_clean()

        assert "source_path" in refused.value.error_dict

    def test_a_code_expression_is_refused_as_a_path(self):
        declared = _measurement(_event_type(_tenant()),
                                source_kind=SOURCE_KIND_PROVIDER_RESPONSE,
                                source_path=["usage", "prompt_tokens"])
        declared.source_path = ["response.usage.prompt_tokens"]

        with pytest.raises(ValidationError) as refused:
            declared.full_clean()

        assert "source_path" in refused.value.error_dict

    def test_the_path_survives_the_round_trip_exactly(self):
        """Structured data in, the same structured data out."""
        declared = _measurement(_event_type(_tenant()),
                                source_kind=SOURCE_KIND_PROVIDER_RESPONSE,
                                source_path=["usageMetadata", "promptTokenCount"])

        assert Measurement.objects.get(pk=declared.pk).source_path == [
            "usageMetadata", "promptTokenCount"]


@pytest.mark.django_db
class TestTheAdvisoryCheckerWarnsAndNeverSubstitutes:
    """A path inconsistent with the shape it is declared against."""

    def _declared(self, shape, path):
        event_type = _event_type(_tenant(), source_shape_id=shape)
        return _measurement(event_type,
                            source_kind=SOURCE_KIND_PROVIDER_RESPONSE,
                            source_path=path)

    def test_an_inconsistent_path_is_advised(self):
        declared = self._declared(SOURCE_SHAPE_ID_GOOGLE_GENAI_PYTHON_V1,
                                  ["usageMetadata", "promptTokenCount"])

        assert len(declared.declaration_advisories()) == 2

    def test_it_is_advice_and_not_a_refusal(self):
        """The declaration still validates and still saves.

        Refusing it would be UBB claiming to know a supplier's response shape
        better than the tenant integrating against it, on the strength of a
        naming convention.
        """
        declared = self._declared(SOURCE_SHAPE_ID_GOOGLE_GENAI_PYTHON_V1,
                                  ["usageMetadata", "promptTokenCount"])

        declared.full_clean()
        declared.save()

        assert Measurement.objects.get(pk=declared.pk).source_path == [
            "usageMetadata", "promptTokenCount"]

    def test_nothing_is_substituted(self):
        """The failure mode being designed out, checked at the column.

        Reading the advice does not rewrite the path — not in the instance and
        not in the row behind it.
        """
        declared = self._declared(SOURCE_SHAPE_ID_GOOGLE_GENAI_PYTHON_V1,
                                  ["usageMetadata", "promptTokenCount"])

        declared.declaration_advisories()
        declared.refresh_from_db()

        assert declared.source_path == ["usageMetadata", "promptTokenCount"]

    def test_a_consistent_path_draws_no_advice(self):
        declared = self._declared(SOURCE_SHAPE_ID_GOOGLE_GEMINI_REST_V1,
                                  ["usageMetadata", "promptTokenCount"])

        assert declared.declaration_advisories() == ()


@pytest.mark.django_db
class TestTheDeclarationBeneathAPublishedEventType:
    """Publication pins the structured paths (#193 §B7), so a change revises it.

    An incorrect path produces an incorrect supplier cost, and the code a tenant
    generated and deployed was generated against the path as it read then. A
    silent change would make the deployed integration a reading of a contract
    that has moved.
    """

    def _published(self):
        declared = _event_type(_tenant())
        declared.publish()
        assert declared.declaration_status == DECLARATION_STATUS_PUBLISHED
        return declared

    def test_changing_a_path_returns_the_event_type_to_draft(self):
        declared = self._published()
        quantity = _measurement(declared,
                                source_kind=SOURCE_KIND_PROVIDER_RESPONSE,
                                source_path=["usage", "prompt_tokens"])
        declared.refresh_from_db()
        declared.publish()

        quantity.source_path = ["usage", "input_tokens"]
        quantity.save()

        assert (EventType.objects.get(pk=declared.pk).declaration_status
                == DECLARATION_STATUS_DRAFT)

    def test_declaring_a_new_quantity_returns_it_to_draft(self):
        """A published Event Type that grows a required quantity is a different
        declaration from the one the tenant generated their integration
        against."""
        declared = self._published()

        _measurement(declared, required_for_costing=True)

        assert (EventType.objects.get(pk=declared.pk).declaration_status
                == DECLARATION_STATUS_DRAFT)

    def test_withdrawing_a_quantity_returns_it_to_draft(self):
        declared = self._published()
        quantity = _measurement(declared)
        declared.refresh_from_db()
        declared.publish()

        quantity.delete()

        assert (EventType.objects.get(pk=declared.pk).declaration_status
                == DECLARATION_STATUS_DRAFT)

    def test_the_published_revision_does_not_move(self):
        """The code the tenant already deployed did not move either."""
        declared = self._published()
        _measurement(declared)

        declared.refresh_from_db()
        assert declared.published_revision == 1

    def test_a_cosmetic_change_is_not_a_revision(self):
        """A corrected caption reaches no emitted behaviour.

        Returning a live integration to draft over it would be a cost with
        nothing on the other side, which is why `display_name` is not pinned.
        """
        declared = self._published()
        quantity = _measurement(declared)
        declared.refresh_from_db()
        declared.publish()

        quantity.display_name = "Prompt tokens"
        quantity.save()

        assert (EventType.objects.get(pk=declared.pk).declaration_status
                == DECLARATION_STATUS_PUBLISHED)

    def test_saving_an_unchanged_declaration_is_not_a_revision(self):
        declared = self._published()
        _measurement(declared)
        declared.refresh_from_db()
        declared.publish()

        quantity = Measurement.objects.get(event_type=declared)
        quantity.save()

        assert (EventType.objects.get(pk=declared.pk).declaration_status
                == DECLARATION_STATUS_PUBLISHED)

    def test_the_guard_holds_on_a_deferred_load(self):
        """The spelling a careful caller reaches for.

        `only("source_path")` defers the rest of the row, so a baseline taken
        at load time would be absent — and absent is indistinguishable from
        unchanged, which is the direction that fails OPEN.
        """
        declared = self._published()
        _measurement(declared)
        declared.refresh_from_db()
        declared.publish()

        quantity = Measurement.objects.only("source_path").get(
            event_type=declared)
        quantity.unit = "second"
        quantity.save()

        assert (EventType.objects.get(pk=declared.pk).declaration_status
                == DECLARATION_STATUS_DRAFT)

    def test_a_draft_stays_a_draft(self):
        """Nothing to revise, and nothing pretends otherwise."""
        declared = _event_type(_tenant())

        _measurement(declared)

        assert (EventType.objects.get(pk=declared.pk).declaration_status
                == DECLARATION_STATUS_DRAFT)
        assert EventType.objects.get(pk=declared.pk).published_revision == 0


@pytest.mark.django_db
class TestTheAnalyticsGroupingIsStillOwed:

    def test_the_grouping_arrives_optional_or_this_goes_red(self):
        """A tripwire for the ticket that builds the grouping (#264).

        The grouping is tenant-level, opt-in and analytics-only, and the record
        it points at does not exist here — so the attribute cannot be built in
        this commit. What CAN be built is the check that fires when it lands:
        an assignment that is not optional would make an analytics grouping a
        precondition for declaring a quantity, which is the one thing #264's
        three fences all forbid. Written the way ``SATELLITE_HOLDERS`` was, a
        ticket before its model existed: vacuous today, red on the commit that
        lands the relation without making it optional.
        """
        grouping = [field for field in Measurement._meta.get_fields()
                    if getattr(field, "is_relation", False)
                    and field.name not in {"event_type"}
                    and field.concrete]

        for field in grouping:
            assert field.null and field.blank, (
                f"Measurement.{field.name} has arrived and is not optional. A "
                f"measurement declaration records a quantity whether or not a "
                f"tenant has grouped it for analytics (#264)")
