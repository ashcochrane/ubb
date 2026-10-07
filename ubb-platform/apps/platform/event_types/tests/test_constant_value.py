"""A constant quantity's declared value, held to the model and the database (#571).

The lifecycle a tenant drives — declare, read, publish, revise — is asserted
through the tenant's own routes, in
``api/v1/tests/test_a_constant_measurement_declares_its_value.py``. What is
here is what a route cannot reach:

* **The one canonicaliser, as a function.** The accepted grammar, the one
  stored form, and every spelling refused — including the ones Python's own
  ``Decimal`` would have read, which is the trap a grammar check leaning on it
  falls into.
* **The database's half of the rule** (ADR-0007 §2: the constraint is the
  rule). Every case writes through the ORM with no ``full_clean``, which is
  the writer the constraints exist for.
* **A publication kept before the value existed** answers ``None`` for it.
* **The migration's guard**, over states no route can produce any more.
"""
from decimal import Decimal
from importlib import import_module

import pytest
from django.apps import apps as live_apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, migrations, transaction

from apps.platform.event_types.exact_decimals import (
    NotAnExactDecimal, canonical)
from apps.platform.event_types.models import EventType, Measurement
from apps.platform.event_types.publication import last_published_declaration
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    COSTING_METHOD_CALCULATED,
    MEASUREMENT_VALUE_TYPE_DECIMAL,
    MEASUREMENT_VALUE_TYPE_INTEGER,
    SOURCE_KIND_CALLER_SUPPLIED,
    SOURCE_KIND_CONSTANT,
    UNIT_CALL,
)

THE_MIGRATION = import_module(
    "apps.platform.event_types.migrations."
    "0009_a_constant_declares_its_value")

#: Twelve, written in two other scripts' digits. Built from code points so the
#: characters this module is about are never typed into it.
ARABIC_INDIC_TWELVE = chr(0x0661) + chr(0x0662)
FULLWIDTH_TWELVE = chr(0xFF11) + chr(0xFF12)

#: Valid decimal syntax, and the one form each is stored and published in.
CANONICAL_FORMS = [
    ("01.500", "1.5"),
    ("-0", "0"),
    ("-0.000", "0"),
    ("000", "0"),
    ("-01.10", "-1.1"),
    ("0.50", "0.5"),
    ("12.0", "12"),
    ("12", "12"),
    ("-3", "-3"),
    ("-0.25", "-0.25"),
    ("100.001", "100.001"),
]

#: Spellings that are not a base-10 exact decimal as the grammar reads one.
#: Several are numbers to Python's `Decimal`, which accepts surrounding
#: whitespace, underscores, any script's digits, NaN, Infinity and exponents —
#: so a check that leaned on it would pass them.
REFUSED_SPELLINGS = [
    "", " 12", "12 ", "12\n", "+12", "1e3", "1E3", "1_000", "1,000", ".5",
    "5.", "-", "NaN", "Infinity",
    ARABIC_INDIC_TWELVE,
    FULLWIDTH_TWELVE,
]


# ---------------------------------------------------------------------------
# The one canonicaliser
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("written, stored", CANONICAL_FORMS)
def test_valid_decimal_syntax_has_one_canonical_form(written, stored):
    assert canonical(written) == stored


@pytest.mark.parametrize("written", REFUSED_SPELLINGS)
def test_a_spelling_outside_the_grammar_is_refused(written):
    with pytest.raises(NotAnExactDecimal) as refused:
        canonical(written)

    assert "base-10 digits" in str(refused.value)


@pytest.mark.parametrize("written", ["1_000", " 12", "12\n", "NaN",
                                     "Infinity", "1e3", ARABIC_INDIC_TWELVE,
                                     FULLWIDTH_TWELVE])
def test_the_spellings_python_decimal_would_have_read_are_still_refused(
        written):
    """The control the refusal above needs: each of these IS a number to
    `Decimal`, so the grammar — not Python's parser — is what refuses it."""
    Decimal(written)

    with pytest.raises(NotAnExactDecimal) as refused:
        canonical(written)

    assert "base-10 digits" in str(refused.value)


@pytest.mark.parametrize("value", [12, 12.5, True, None, b"12"])
def test_only_text_is_read_as_a_declared_value(value):
    """The stored form is text, so the reader takes text. A number reaching
    it is a caller that skipped the wire's own refusal, and reading it would
    put a binary float on the declaration path."""
    with pytest.raises(NotAnExactDecimal) as refused:
        canonical(value)

    assert "is not text" in str(refused.value)


@pytest.mark.parametrize("written", [
    "1" * 60,
    "0." + "1234567891" * 4,
    "9007199254740993",
    "-" + "9" * 45 + "." + "9" * 45,
])
def test_a_value_a_float_or_a_decimal_context_would_change_is_kept_exactly(
        written):
    """No precision limit governs a Measurement quantity, and nothing on the
    way to storage rounds. A float gives 2**53 + 1 back as ...992; the other
    three are longer than the 28 digits at which `Decimal.normalize()` and
    arithmetic round."""
    assert canonical(written) == written


# ---------------------------------------------------------------------------
# The database's half of the rule
# ---------------------------------------------------------------------------

def _event_type(tenant=None, key="acme.call"):
    tenant = tenant or Tenant.objects.create(name="T")
    return EventType.objects.create(tenant=tenant, key=key,
                                    costing_method=COSTING_METHOD_CALCULATED)


def _written(event_type, **declared):
    """A quantity written through the ORM, which runs no `full_clean`."""
    declared.setdefault("code", "flat_fee")
    declared.setdefault("unit", UNIT_CALL)
    declared.setdefault("source_kind", SOURCE_KIND_CONSTANT)
    declared.setdefault("value_type", MEASUREMENT_VALUE_TYPE_DECIMAL)
    with transaction.atomic():
        return Measurement.objects.create(event_type=event_type, **declared)


@pytest.mark.django_db
class TestTheDatabaseHoldsTheRule:

    def test_a_constant_with_a_canonical_value_is_written(self):
        written = _written(_event_type(), constant_value="-12.5")

        assert Measurement.objects.get(pk=written.pk).constant_value == "-12.5"

    def test_a_constant_without_a_value_is_refused(self):
        with pytest.raises(IntegrityError) as refused:
            _written(_event_type(), constant_value=None)

        assert "ck_measurement_constant_value_iff_constant" in str(
            refused.value)

    def test_a_value_on_another_kind_is_refused(self):
        with pytest.raises(IntegrityError) as refused:
            _written(_event_type(), source_kind=SOURCE_KIND_CALLER_SUPPLIED,
                     constant_value="12")

        assert "ck_measurement_constant_value_iff_constant" in str(
            refused.value)

    @pytest.mark.parametrize("written", ["01.5", "1.50", "-0", "1.", "+1",
                                         "1e3", ARABIC_INDIC_TWELVE, ""])
    def test_a_value_not_in_its_canonical_form_is_refused(self, written):
        with pytest.raises(IntegrityError) as refused:
            _written(_event_type(), constant_value=written)

        assert "ck_measurement_constant_value_is_canonical" in str(
            refused.value)

    def test_a_fraction_under_an_integer_declaration_is_refused(self):
        with pytest.raises(IntegrityError) as refused:
            _written(_event_type(), value_type=MEASUREMENT_VALUE_TYPE_INTEGER,
                     constant_value="12.5")

        assert "ck_measurement_integer_constant_is_whole" in str(
            refused.value)


@pytest.mark.django_db
@pytest.mark.parametrize("value", [12.5, 0.1 + 0.2, 12, True])
def test_the_model_reads_no_number_as_text_on_the_way_to_the_rule(value):
    """Django's `TextField` reads any value as text with `str()` while the
    fields are cleaned — which, for a float, is its binary expansion
    (`0.30000000000000004`). A writer that skips the wire's refusal meets the
    canonicaliser's own instead, and nothing is stored."""
    declared = Measurement(event_type=_event_type(), code="flat_fee",
                           unit=UNIT_CALL, source_kind=SOURCE_KIND_CONSTANT,
                           value_type=MEASUREMENT_VALUE_TYPE_DECIMAL,
                           constant_value=value)

    with pytest.raises(ValidationError) as refused:
        declared.full_clean()

    assert "is not text" in " ".join(
        refused.value.message_dict["constant_value"])
    assert declared.constant_value == value


# ---------------------------------------------------------------------------
# A publication kept before the value existed
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_a_copy_kept_before_the_value_existed_answers_none_for_it():
    """A copy `publish` kept before #571 has no `constant_value` at all. The
    migration that added it refused to run over any copy pinning a constant,
    so every quantity such a copy holds is one with no value: the read says
    `None`, and makes nothing up."""
    event_type = _event_type()
    _written(event_type, code="searches",
             source_kind=SOURCE_KIND_CALLER_SUPPLIED, constant_value=None)
    event_type = EventType.objects.get(pk=event_type.pk).publish()
    kept = dict(EventType.objects.get(pk=event_type.pk).published_declaration)
    kept["measurements"] = [
        {name: value for name, value in quantity.items()
         if name != "constant_value"}
        for quantity in kept["measurements"]]
    EventType.objects.filter(pk=event_type.pk).update(
        published_declaration=kept)

    read = last_published_declaration(tenant=event_type.tenant,
                                      key=event_type.key)

    assert [(quantity.code, quantity.constant_value)
            for quantity in read.measurements] == [("searches", None)]


# ---------------------------------------------------------------------------
# The migration's guard
# ---------------------------------------------------------------------------

guard = THE_MIGRATION.refuse_a_constant_without_a_value


def test_the_guard_runs_after_the_column_and_before_the_rules():
    """The order is the whole of what makes the guard honest: after the
    column exists, so the rows it reads are the rows the rules will judge,
    and before any rule is added, so its refusal — naming what it found —
    arrives instead of a bare constraint violation."""
    operations = THE_MIGRATION.Migration.operations

    assert [type(operation) for operation in operations] == [
        migrations.AddField, migrations.RunPython, migrations.AddConstraint,
        migrations.AddConstraint, migrations.AddConstraint]
    assert operations[1].code is guard
    assert operations[0].name == "constant_value"


@pytest.mark.django_db
def test_the_guard_lets_a_tree_with_no_valueless_constant_through():
    event_type = _event_type()
    _written(event_type, constant_value="2")
    _written(event_type, code="searches",
             source_kind=SOURCE_KIND_CALLER_SUPPLIED, constant_value=None)
    EventType.objects.get(pk=event_type.pk).publish()

    guard(live_apps, None)


def _without_the_rule_that_a_constant_owes_a_value():
    """Drop the rule for the rest of this test's transaction, which rolls it
    back. A constant row with no value is a state the database now refuses,
    so this is the only way to plant the tree the guard exists for."""
    (rule,) = [constraint for constraint in Measurement._meta.constraints
               if constraint.name
               == "ck_measurement_constant_value_iff_constant"]
    with connection.schema_editor() as editor:
        editor.remove_constraint(Measurement, rule)


@pytest.mark.django_db
def test_the_guard_refuses_a_constant_row_with_no_value_and_names_it():
    """Named by everything it takes to find it — the tenant's id and name,
    the Event Type, the quantity and the row — and by how to clear it, with
    nothing repaired."""
    tenant = Tenant.objects.create(name="Acme pre-launch")
    event_type = _event_type(tenant, key="acme.flat")
    _without_the_rule_that_a_constant_owes_a_value()
    # Written through the ORM: no route can declare a constant without its
    # value any more, which is the point of the rule just dropped.
    held = _written(event_type, constant_value=None)

    with pytest.raises(THE_MIGRATION.ConstantWithoutAValue) as refused:
        guard(live_apps, None)

    said = str(refused.value)
    assert (f"declared quantity 'flat_fee' (Measurement {held.pk}) under "
            f"Event Type 'acme.flat' of tenant {tenant.pk} "
            f"('Acme pre-launch')") in said
    assert "never invents one, and repairs nothing" in said
    assert "DELETE /api/v1/event-types/<key>/measurements/<code>" in said
    assert "reset that tenant's pre-launch configuration" in said
    assert Measurement.objects.get(pk=held.pk).constant_value is None


@pytest.mark.django_db
def test_the_guard_refuses_a_kept_publication_pinning_a_valueless_constant():
    tenant = Tenant.objects.create(name="Acme pre-launch")
    event_type = _event_type(tenant, key="acme.flat")
    _written(event_type, code="searches",
             source_kind=SOURCE_KIND_CALLER_SUPPLIED, constant_value=None)
    EventType.objects.get(pk=event_type.pk).publish()
    kept = dict(EventType.objects.get(pk=event_type.pk).published_declaration)
    # Written through the ORM: a copy is composed only by `publish`, from rows
    # that can no longer hold a constant without its value. This is a copy as
    # a tree before #571 kept it — no `constant_value` key at all.
    kept["measurements"] = [{
        "code": "flat_fee", "value_type": MEASUREMENT_VALUE_TYPE_DECIMAL,
        "unit": UNIT_CALL, "required_for_costing": False,
        "source_kind": SOURCE_KIND_CONSTANT, "source_path": []}]
    EventType.objects.filter(pk=event_type.pk).update(
        published_declaration=kept)

    with pytest.raises(THE_MIGRATION.ConstantWithoutAValue) as refused:
        guard(live_apps, None)

    said = str(refused.value)
    assert (f"kept publication of Event Type 'acme.flat' (EventType "
            f"{event_type.pk}) of tenant {tenant.pk} ('Acme pre-launch'), "
            f"pinning quantity 'flat_fee'") in said
    assert "POST /api/v1/event-types/<key>/publish" in said
    assert EventType.objects.get(pk=event_type.pk).published_declaration \
        == kept
