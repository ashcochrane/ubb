"""A constant Measurement declares its value, through the tenant's routes (#571).

A `constant` quantity's value is part of its declaration (#156 §4), so it is
declared with it, read back with it and pinned by the publication with it. On
the wire it is ALWAYS a string — for both value types — in one canonical exact
decimal form, and the declared `value_type` gives the semantics: an `integer`
constant is a whole number, a `decimal` one may carry a fraction (owner ruling
on #571, comment 6024142285).

What is asserted here is what the caller sees: the value that comes back, the
value the next read and the publication hold, and every refusal reaching them
with its own message. The canonicaliser's table and the database's half of
the rule are next door to the model, in
``apps/platform/event_types/tests/test_constant_value.py``.

Recording is not here: what a recorded quantity looks like on the wire is
#603's, and nothing in this module records anything.

It also holds the registry's same-commit rule for the closed diagnostic set,
because #571 swapped a member of it — and #570 swapped another under the same
rule, so both swaps are asserted here, surface by surface.
"""
import json
from pathlib import Path
from urllib.parse import quote

import pytest

from api.v1.tests._helpers import EVENT, BlueprintRoutes
from apps.platform.audit.models import AuditRecord
from apps.platform.event_types.exact_decimals import (
    ACCEPTED, CANONICAL, anchored)
from apps.platform.event_types.models import EventType, Measurement
from apps.platform.event_types.publication import last_published_declaration

CONTRACT = Path(__file__).resolve().parents[4] / "openapi" / "v1.json"
CONVENTION = (Path(__file__).resolve().parents[4] / "docs" / "conventions"
              / "api-contract.md")

FLAT_FEE = "flat_fee"

#: Absent from the body, as opposed to sent as null.
OMITTED = object()

#: Values a binary float would change, and two of them longer than the 28
#: digits at which a decimal context rounds.
SIXTY_DIGITS = "1234567890" * 6
FORTY_FRACTIONAL_DIGITS = "3." + "1415926535" * 4
TWO_TO_THE_FIFTY_THIRD_PLUS_ONE = "9007199254740993"

#: Twelve, written in two other scripts' digits, built from code points.
ARABIC_INDIC_TWELVE = chr(0x0661) + chr(0x0662)
FULLWIDTH_TWELVE = chr(0xFF11) + chr(0xFF12)

#: What the refusal of a spelling outside the grammar says, whatever it was.
THE_GRAMMAR = "base-10 digits with an optional leading '-'"


def test_the_contract_states_both_grammars_and_what_gives_the_meaning():
    """Text storage is fine; an underspecified public string is not. The
    request states what may be written and the response the one form it is
    answered in, each held to the grammar the server enforces — and both say
    that `value_type`, not the string, says what kind of number it is."""
    schemas = json.loads(CONTRACT.read_text(encoding="utf-8"))[
        "components"]["schemas"]

    def published(schema):
        field = schemas[schema]["properties"]["constant_value"]
        (text,) = [member for member in field["anyOf"]
                   if member.get("type") == "string"]
        assert {"type": "null"} in field["anyOf"]
        return text["pattern"], field["description"]

    accepted, said_in = published("MeasurementIn")
    canonical_form, said_out = published("MeasurementOut")

    assert (accepted, canonical_form) == (anchored(ACCEPTED),
                                          anchored(CANONICAL))
    for said in (said_in, said_out):
        assert "`value_type` gives its meaning" in said
        assert "not evidence that the value is a string" in said
    assert "constant_value" in schemas["MeasurementOut"]["required"]
    assert "constant_value" not in schemas["MeasurementIn"].get(
        "required", [])
    # And the convention that states the grammars for a reader spells the
    # same two, so it cannot drift from what the server enforces.
    convention = CONVENTION.read_text(encoding="utf-8")
    assert f"`{anchored(ACCEPTED)}`" in convention
    assert f"`{anchored(CANONICAL)}`" in convention


#: The member one valueless constant used to produce, and the one a valued
#: constant produces until a Code Builder version renders it (#571).
REMOVED = "constant_value_not_declared"
ADDED = "constant_measurement_not_renderable"

#: Every member swapped under the registry's same-commit rule, removed member
#: first. The second is #570's: a cost read off the supplier's response has a
#: truthful request field now, so the member that called its mapping
#: unsupported went, and the one saying only this Code Builder version cannot
#: yet render the read came in (#583 removes it).
SWAPS = {
    "#571": (REMOVED, ADDED),
    "#570": ("reported_cost_provider_response_unsupported",
             "reported_cost_provider_response_not_renderable"),
}

#: #570's removed member's explanation, in its own WORDS (#571's owner
#: ruling: a new diagnostic that replaces a false explanation replaces it on
#: every surface — so the search is for what it said, not only for its name).
#: Each phrase sits on ONE line of a surface that carried it at `555fd1e4` —
#: the label, the catalogue, and the header of both blocked files — because a
#: generated file wraps its prose, and a phrase spanning a line break would
#: match nothing before the swap as well as after it. #571's own is not here:
#: "has no configured value" is still the renderer's true sentence for a token
#: that has none, and #571's tests pin where.
OLD_EXPLANATIONS = {
    "#570": ("cannot be recorded yet",
             "generated call can carry a cost read that way",
             "Declare it as supplied",
             "by the caller with the request below"),
}

#: Every generated surface the closed set of diagnostic codes reaches.
GENERATED = (
    "openapi/v1.json", "openapi/known-values.json",
    "ubb-platform/core/vocabulary.py", "ubb-sdk/ubb/vocabulary.py",
    "ubb-sdk/ubb/_core/models/integration_blueprint_diagnostic_code.py",
    "apps/ui/src/api/schema.json", "apps/ui/src/lib/vocabulary.ts",
    "apps/ui/src/locales/en.json", "apps/codegen/src/catalogue.ts",
)


def _registry_values(concept):
    """A closed concept's values, line-walked: the platform's lock carries no
    YAML parser."""
    lines = (CONTRACT.parents[1] / "domain-vocabulary" / "concepts"
             / "code-builder.yaml").read_text(encoding="utf-8").splitlines()
    start = lines.index(f"{concept}:")
    at = lines.index("  values:", start) + 1
    values = []
    while lines[at].startswith("    - "):
        values.append(lines[at].removeprefix("    - "))
        at += 1
    return values


def _platform_written():
    """Every file a renderer or the platform wrote: the committed Blueprint
    fixtures, the rendered snapshots, and Verify's answers."""
    root = CONTRACT.parents[1]
    written = [*(root / "apps" / "codegen" / "fixtures" / "blueprints").glob(
        "*.json"), *(root / "apps" / "codegen" / "tests" / "__snapshots__"
                     ).rglob("*.*"),
               *(root / "apps" / "ui" / "src" / "features" / "developers"
                 / "api" / "verifications").glob("*.json")]
    assert len(written) > 100, "the platform-written files were not found"
    return written


@pytest.mark.parametrize("ticket", sorted(SWAPS))
def test_the_removed_member_is_on_no_surface_and_its_successor_on_every_one(
        ticket):
    """The registry's same-commit rule, surface by surface: a state nothing
    produces any more is named on no surface, and the state that replaced it
    on every one. (#571: nothing can declare a constant without its value. #570:
    a cost read off the supplier's response has a transport of its own.) The
    registry's own comment records each removal, so the registry is read by
    its values."""
    removed, added = SWAPS[ticket]
    root = CONTRACT.parents[1]

    assert removed not in _registry_values("diagnostic_code")
    assert added in _registry_values("diagnostic_code")
    for path in GENERATED:
        text = (root / path).read_text(encoding="utf-8")
        assert removed not in text, path
        assert added in text, path
    assert [path.name for path in _platform_written()
            if removed in path.read_text(encoding="utf-8")] == []


@pytest.mark.parametrize("ticket", sorted(OLD_EXPLANATIONS))
def test_no_generated_surface_still_gives_the_removed_explanation(ticket):
    """A false explanation goes with its member, in its own words: no file a
    renderer or the platform wrote, and no generated surface, still carries a
    phrase of the explanation the removed member gave — each one a phrase that
    surface did carry before the swap, so this can go red."""
    root = CONTRACT.parents[1]
    surfaces = [*_platform_written(), *(root / path for path in GENERATED)]
    for words in OLD_EXPLANATIONS[ticket]:
        assert [path.name for path in surfaces
                if words in path.read_text(encoding="utf-8")] == [], words


def a_constant(value=OMITTED, *, value_type="decimal",
               source_kind="constant", source_path=()):
    body = {"display_name": "Flat fee", "value_type": value_type,
            "unit": "call", "required_for_costing": False,
            "source_kind": source_kind, "source_path": list(source_path)}
    if value is not OMITTED:
        body["constant_value"] = value
    return body


@pytest.mark.django_db
class TestAConstantDeclaresItsValue(BlueprintRoutes):

    def setup_method(self):
        super().setup_method()
        self._event_type(measurements={}, publish=False)

    def _declare(self, body, code=FLAT_FEE):
        return self._send("put", f"/api/v1/event-types/{EVENT}/measurements/"
                                 f"{quote(code, safe='')}", body)

    def _kept(self):
        return last_published_declaration(tenant=self.tenant, key=EVENT)

    def _stored(self, code=FLAT_FEE):
        return Measurement.objects.get(event_type__tenant=self.tenant,
                                       code=code).constant_value

    def _refused(self, body, *, says):
        refused = self._declare(body)
        assert refused.status_code == 422, refused.content
        detail = refused.json()["detail"]
        assert detail.startswith("constant_value: "), detail
        assert says in detail, detail
        return detail

    # -- declared, read back and published ---------------------------------

    @pytest.mark.parametrize("value_type, value", [("integer", "12"),
                                                   ("decimal", "12.5")])
    def test_a_constant_declares_reads_back_and_publishes(self, value_type,
                                                          value):
        declared = self._declare(a_constant(value, value_type=value_type))

        assert declared.status_code == 201, declared.content
        assert declared.json()["constant_value"] == value
        listed = self._call("get",
                            f"/api/v1/event-types/{EVENT}/measurements")
        assert [m["constant_value"] for m in listed["data"]] == [value]
        published = self._publish()
        assert [m["constant_value"] for m in published["measurements"]] == [
            value]
        assert [(m.code, m.value_type, m.constant_value)
                for m in self._kept().measurements] == [
            (FLAT_FEE, value_type, value)]

    def test_another_kind_reads_back_with_no_value(self):
        """Always present on the response, and null where nothing is
        declared — never absent, never an empty string."""
        declared = self._declare(a_constant(source_kind="caller_supplied"))

        assert declared.status_code == 201, declared.content
        assert declared.json()["constant_value"] is None
        self._publish()
        assert self._kept().measurements[0].constant_value is None

    def test_a_whole_number_written_carefully_is_an_integer_constant(self):
        """`12.0` is a whole number written by somebody being careful — the
        Measurement contract's own reader already accepts it — and it is
        stored, read and published as `12`."""
        declared = self._declare(a_constant("12.0", value_type="integer"))

        assert declared.status_code == 201, declared.content
        assert declared.json()["constant_value"] == "12"
        assert self._stored() == "12"
        self._publish()
        assert self._kept().measurements[0].constant_value == "12"

    @pytest.mark.parametrize("value_type, value", [("integer", "-3"),
                                                   ("decimal", "-0.25")])
    def test_a_negative_constant_declares_and_publishes(self, value_type,
                                                        value):
        """The Measurement contract has no sign rule, so #571 adds none. The
        recording route's own `>= 0` is #603's to decide."""
        declared = self._declare(a_constant(value, value_type=value_type))

        assert declared.status_code == 201, declared.content
        assert declared.json()["constant_value"] == value
        self._publish()
        assert self._kept().measurements[0].constant_value == value

    # -- one canonical form ------------------------------------------------

    @pytest.mark.parametrize("written, stored", [
        ("01.500", "1.5"), ("-0", "0"), ("-0.000", "0"), ("000", "0"),
        ("-01.10", "-1.1"), ("0.50", "0.5"),
    ])
    def test_valid_decimal_syntax_is_kept_in_its_one_canonical_form(
            self, written, stored):
        declared = self._declare(a_constant(written))

        assert declared.status_code == 201, declared.content
        assert declared.json()["constant_value"] == stored
        assert self._stored() == stored
        self._publish()
        assert self._kept().measurements[0].constant_value == stored
        pinned = EventType.objects.get(tenant=self.tenant,
                                       key=EVENT).published_declaration
        assert pinned["measurements"][0]["constant_value"] == stored

    # -- refused -----------------------------------------------------------

    @pytest.mark.parametrize("written", [
        "", " 12", "12 ", "12\n", "+12", "1e3", "1E3", "1_000", "1,000",
        ".5", "5.", "-", "NaN", "Infinity", ARABIC_INDIC_TWELVE,
        FULLWIDTH_TWELVE,
    ])
    def test_a_spelling_outside_the_grammar_is_refused(self, written):
        self._refused(a_constant(written), says=THE_GRAMMAR)

        assert not Measurement.objects.filter(
            event_type__tenant=self.tenant).exists()

    @pytest.mark.parametrize("sent", [12, 12.5, True])
    def test_a_json_number_or_flag_is_refused_as_the_wrong_representation(
            self, sent):
        """The value is a string on the wire for both value types. A JSON
        number would have crossed as a binary float in most clients, and
        nothing on the server turns one into text."""
        refused = self._declare(a_constant(sent))

        assert refused.status_code == 422, refused.content
        assert [(error["loc"][-1], error["type"])
                for error in refused.json()["errors"]] == [
            ("constant_value", "string_type")]
        assert not Measurement.objects.filter(
            event_type__tenant=self.tenant).exists()

    def test_a_fraction_is_refused_where_a_whole_number_is_declared(self):
        self._refused(a_constant("12.5", value_type="integer"),
                      says="is declared as a whole number and '12.5' is not "
                           "one")

    @pytest.mark.parametrize("value", [OMITTED, None])
    def test_a_constant_without_a_value_is_refused(self, value):
        self._refused(a_constant(value),
                      says="a constant quantity's value is part of its "
                           "declaration")

    @pytest.mark.parametrize("kind, path", [
        ("caller_supplied", ()), ("provider_response", ("usage", "calls")),
        ("derived", ()),
    ])
    def test_a_value_on_another_kind_is_refused(self, kind, path):
        self._refused(a_constant("12", source_kind=kind, source_path=path),
                      says=f"declared as '{kind}', which is not a constant")

    def test_a_put_that_makes_an_integer_of_a_fraction_is_refused(self):
        self._declare(a_constant("12.5"))

        self._refused(a_constant("12.5", value_type="integer"),
                      says="is declared as a whole number")

        assert self._stored() == "12.5"
        assert Measurement.objects.get(
            event_type__tenant=self.tenant).value_type == "decimal"

    def test_a_put_that_moves_the_kind_but_keeps_the_value_is_refused(self):
        self._declare(a_constant("12.5"))

        self._refused(a_constant("12.5", source_kind="caller_supplied"),
                      says="which is not a constant")

        assert Measurement.objects.get(
            event_type__tenant=self.tenant).source_kind == "constant"

    # -- the publication ---------------------------------------------------

    def test_a_changed_value_revises_and_publishing_pins_the_new_one(self):
        self._declare(a_constant("12"))
        self._publish()

        self._declare(a_constant("13"))

        assert self._call("get", f"/api/v1/event-types/{EVENT}")[
            "declaration_status"] == "draft"
        assert self._kept().measurements[0].constant_value == "12"
        self._publish()
        kept = self._kept()
        assert (kept.published_revision,
                kept.measurements[0].constant_value) == (2, "13")

    def test_the_same_value_in_another_spelling_is_not_a_change(self):
        """Canonical forms are what is compared: `1.50` over `1.5` is the
        value already published, so the Event Type stays published."""
        self._declare(a_constant("1.5"))
        self._publish()

        redeclared = self._declare(a_constant("1.50"))

        assert redeclared.status_code == 200, redeclared.content
        assert redeclared.json()["constant_value"] == "1.5"
        event_type = self._call("get", f"/api/v1/event-types/{EVENT}")
        assert (event_type["declaration_status"],
                event_type["published_revision"]) == ("published", 1)

    # -- exact, however long -----------------------------------------------

    @pytest.mark.parametrize("value_type, value", [
        ("integer", SIXTY_DIGITS),
        ("decimal", FORTY_FRACTIONAL_DIGITS),
        ("integer", TWO_TO_THE_FIFTY_THIRD_PLUS_ONE),
    ])
    def test_a_long_value_crosses_every_stage_byte_for_byte(self, value_type,
                                                           value):
        """Declared, answered, stored, published, kept and audited, with no
        stage converting it. A float gives 2**53 + 1 back as ...992, and
        `Decimal.normalize()` and arithmetic round at 28 digits, which the
        sixty-digit and forty-fractional-digit values are longer than."""
        declared = self._declare(a_constant(value, value_type=value_type))

        assert declared.status_code == 201, declared.content
        assert f'"constant_value": "{value}"'.encode() in declared.content \
            or f'"constant_value":"{value}"'.encode() in declared.content
        assert declared.json()["constant_value"] == value
        assert self._stored() == value
        published = self._send("post",
                               f"/api/v1/event-types/{EVENT}/publish")
        assert json.loads(published.content)["measurements"][0][
            "constant_value"] == value
        assert self._kept().measurements[0].constant_value == value
        audited = {record.action: record.metadata for record in
                   AuditRecord.objects.filter(tenant_id=self.tenant.id)}
        assert audited["measurement.declared"]["constant_value"] == value
        assert audited["event_type.published"]["measurements"][0][
            "constant_value"] == value
