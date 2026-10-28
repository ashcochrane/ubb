"""A field that returns only some of its closed concept's values (R10-W5, the
owner's review of #621): it renders as a plain string carrying the concept and
its own values, and the response boundary refuses any other value.

The values the published contract then carries are pinned on the committed
document, in `tests/contracts/test_openapi_known_values.py` (`FIELD_ENUMS`).
"""
import pytest
from ninja import Schema
from pydantic import ValidationError

from core.field_values import CONCEPT_KEY, FIELD_VALUES_KEY, a_field_of
from core.vocabulary import (
    MEASURE_STATUS_INCOMPLETE, MEASURE_STATUS_KNOWN,
    MEASURE_STATUS_UNAVAILABLE_AT_REQUESTED_GRAIN, REVENUE_BASIS_RECOGNISED,
    REVENUE_BASIS_RECORDED)


class _Answer(Schema):
    basis: a_field_of("revenue_basis", REVENUE_BASIS_RECOGNISED)
    status: a_field_of("measure_status", MEASURE_STATUS_KNOWN,
                       MEASURE_STATUS_INCOMPLETE)


def test_the_field_renders_a_string_naming_its_concept_and_its_values():
    properties = _Answer.model_json_schema()["properties"]

    # No `enum` and no `const` of pydantic's own: the export writes the enum
    # from the registry, and refuses one it finds already written.
    assert properties["basis"] == {
        "title": "Basis", "type": "string", CONCEPT_KEY: "revenue_basis",
        FIELD_VALUES_KEY: [REVENUE_BASIS_RECOGNISED]}
    assert properties["status"][FIELD_VALUES_KEY] == [
        MEASURE_STATUS_KNOWN, MEASURE_STATUS_INCOMPLETE]
    assert "enum" not in properties["status"]


def test_the_boundary_refuses_a_value_of_the_concept_the_field_cannot_return():
    assert _Answer(basis=REVENUE_BASIS_RECOGNISED,
                   status=MEASURE_STATUS_INCOMPLETE).basis == (
        REVENUE_BASIS_RECOGNISED)

    with pytest.raises(ValidationError):
        _Answer(basis=REVENUE_BASIS_RECORDED, status=MEASURE_STATUS_KNOWN)
    with pytest.raises(ValidationError):
        _Answer(basis=REVENUE_BASIS_RECOGNISED,
                status=MEASURE_STATUS_UNAVAILABLE_AT_REQUESTED_GRAIN)


@pytest.mark.parametrize("values", [(), ("known", "known")])
def test_a_field_names_at_least_one_value_and_each_once(values):
    with pytest.raises(ValueError):
        a_field_of("measure_status", *values)
