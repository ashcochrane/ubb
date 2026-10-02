"""The renderer's committed fixtures are what this platform answers (#577).

`ubb-codegen` turns an Integration Blueprint into files, and its tests render
committed Blueprints. A renderer tested against a Blueprint somebody imagined
proves nothing about the one the route answers, so every Blueprint under
`apps/codegen/fixtures/blueprints/` is produced HERE: configuration declared
and published through the tenant's own routes, the Blueprint asked for through
its own route, and the answer held equal to the committed file.

The same holds for the arithmetic. The generated module converts a supplier's
reported cost to micros in the tenant's own process, and the definition of
that conversion is `to_micros` and `pin_currency` in this tree. The case table
under `apps/codegen/fixtures/` carries this platform's answer to each case, so
the renderer's tests execute the generated conversion against expectations it
did not write.

**To regenerate after a deliberate change**, run this module with
`UBB_WRITE_CODEGEN_FIXTURES=1`: each test then writes its file before holding
it, and the renderer's snapshots are re-taken from the result.

**Where a fixture writes a row directly it says so, at the write.** One thing
is written: the instant of each publication, which no route sets to a value a
committed file can hold.
"""
import json
import os
from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

import pytest

from apps.platform.event_types.models import EventType
from apps.platform.event_types.reported_cost import (
    MICROS_LIMIT, AmountNotRepresentable, CurrencyDisagreement, pin_currency,
    to_micros)
from core.exceptions import UnknownCurrency
from core.money import SUPPORTED_CURRENCIES, minor_units
from core.vocabulary import (
    AMOUNT_REPRESENTATION_MAJOR_UNITS_DECIMAL as MAJOR,
    AMOUNT_REPRESENTATION_MICROS as MICROS,
    AMOUNT_REPRESENTATION_MINOR_UNITS as MINOR,
    AMOUNT_REPRESENTATION_VALUES,
    PRICING_MODE_FIXED)

from ._helpers import (
    A_JSON_SHAPE, A_PYTHON_SHAPE, INPUT_TOKENS, KIND, SEARCHES, SUBTASK_KIND,
    BlueprintRoutes)

FIXTURES = Path(__file__).resolve().parents[4] / "apps" / "codegen" / "fixtures"
BLUEPRINTS = FIXTURES / "blueprints"
REPORTED_COST_CASES = FIXTURES / "reported-cost-cases.json"
MICROS_PER_MINOR_UNIT = FIXTURES / "micros-per-minor-unit.json"

WRITING = os.environ.get("UBB_WRITE_CODEGEN_FIXTURES") == "1"

#: When every Event Type in a fixture was published. A publication is dated by
#: the clock, and the date is in the Blueprint and in its fingerprint, so a
#: file that is held equal needs it fixed.
PUBLISHED_AT = datetime(2026, 9, 1, 12, 0, tzinfo=datetime_timezone.utc)


def _held(path, produced):
    """`produced` is what `path` holds — written first when asked to."""
    if WRITING:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(produced, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8", newline="\n")
    assert path.is_file(), (
        f"{path.name} is not committed. Run this module with "
        f"UBB_WRITE_CODEGEN_FIXTURES=1 and commit what it writes.")
    assert json.loads(path.read_text(encoding="utf-8")) == produced, (
        f"{path.name} is no longer what the platform answers. If the change "
        f"is meant, run this module with UBB_WRITE_CODEGEN_FIXTURES=1, then "
        f"re-take the renderer's snapshots (`pnpm --dir apps/codegen "
        f"test:update`) and read the diff.")


# ---------------------------------------------------------------------------
# The Blueprints
# ---------------------------------------------------------------------------

class _Configured(BlueprintRoutes):
    """The shared route fixture, with a publication's instant held still."""

    def _publish(self, key):
        published = self._call(
            "post", f"/api/v1/event-types/{quote(key, safe='')}/publish")
        # Written to the row: no route sets the instant of a publication.
        EventType.objects.filter(tenant=self.tenant, key=key).update(
            published_at=PUBLISHED_AT)
        return published

    def _quantity(self, event_type, code, declared):
        self._call(
            "put",
            f"/api/v1/event-types/{quote(event_type, safe='')}/measurements/"
            f"{quote(code, safe='')}", declared)


def _a_quantity(source_kind, *, unit="token", path=(), required=True,
                value_type="integer"):
    return {"display_name": "", "value_type": value_type, "unit": unit,
            "required_for_costing": required, "source_kind": source_kind,
            "source_path": list(path)}


def _calculated_cost(routes):
    """A kind of work with a ceiling and a required Grouping Field, and one
    Event Type costed from quantities: two read off the supplier's Python
    object, one the caller supplies."""
    routes._grouping_fields(("environment", "task"))
    routes._kinds({"key": KIND, "task_cogs_ceiling_micros": 5_000_000,
                   "required_grouping_fields": ["environment"]})
    routes._event_type(
        "chat.completion", provider="openai", shape=A_PYTHON_SHAPE,
        measurements={
            "input_tokens": INPUT_TOKENS,
            "output_tokens": _a_quantity("provider_response",
                                         path=["usage", "output_tokens"]),
            "searches": SEARCHES})
    return routes._resolve(task_type=KIND, event_types=["chat.completion"])


def _reported_cost(routes):
    """An Event Type costed from the supplier's own figure, which the caller
    supplies as a decimal of the major unit."""
    routes._a_kind("web_research")
    routes._event_type(
        "web.search", costing_method="reported", provider="serpapi",
        measurements={"searches": SEARCHES},
        mapping={"source_kind": "caller_supplied",
                 "amount_representation": MAJOR, "currency": "usd"})
    return routes._resolve(task_type="web_research",
                           event_types=["web.search"])


def _direct_task_events(routes):
    """Two Event Types recorded straight against the Task: no Subtask, no
    Grouping Field, no ceiling, nothing read off a response."""
    routes._a_kind("support_reply")
    routes._event_type("reply.sent", measurements={
        "replies": _a_quantity("caller_supplied", unit="reply")})
    routes._event_type("search.run", measurements={"searches": SEARCHES})
    return routes._resolve(task_type="support_reply",
                           event_types=["search.run", "reply.sent"])


def _explicit_subtasks(routes):
    """A Subtask kind the integration creates, with its own required Grouping
    Field, and an Event Type read off a web API's JSON — one of whose paths is
    spelled against the shape's convention, which is advice and blocks
    nothing."""
    routes._grouping_fields(("environment", "task"), ("phase", "subtask"))
    routes._kinds(
        {"key": KIND, "task_cogs_ceiling_micros": 5_000_000,
         "required_grouping_fields": ["environment"]},
        {"key": SUBTASK_KIND, "kind": "subtask", "uncapped": True,
         "required_grouping_fields": ["phase"]})
    routes._event_type(
        "gemini.generate", provider="google", shape=A_JSON_SHAPE,
        measurements={
            "prompt_tokens": _a_quantity(
                "provider_response",
                path=["usageMetadata", "promptTokenCount"]),
            "candidate_tokens": _a_quantity(
                "provider_response",
                path=["usage_metadata", "candidates_token_count"])})
    return routes._resolve(task_type=KIND, event_types=["gemini.generate"],
                           subtask_types=[SUBTASK_KIND])


def _fixed_price(routes):
    """A kind of work sold whole, at one agreed price."""
    routes._kinds({"key": "report", "uncapped": True,
                   "pricing_mode": PRICING_MODE_FIXED})
    routes._event_type("reply.sent", measurements={
        "replies": _a_quantity("caller_supplied", unit="reply")})
    return routes._resolve(task_type="report", event_types=["reply.sent"])


def _scaffold(routes):
    """A tenant that has declared nothing, and selected nothing."""
    return routes._resolve()


def _blocked(routes):
    """Every way a known structure can lack something it cannot run without:
    a constant with no declared value, a derived quantity, a cost read off the
    supplier's response, and an Event Type never published."""
    routes._a_kind()
    routes._event_type(
        "chat.completion", shape=A_PYTHON_SHAPE,
        measurements={
            "input_tokens": INPUT_TOKENS,
            "flat_fee": _a_quantity("constant", unit="call"),
            "ratio": _a_quantity("derived", unit="token",
                                 value_type="decimal")})
    routes._event_type(
        "web.search", costing_method="reported", shape=A_JSON_SHAPE,
        measurements={"searches": SEARCHES},
        mapping={"source_kind": "provider_response",
                 "amount_representation": MAJOR,
                 "source_path": ["cost", "total"], "currency": "usd"})
    routes._event_type("draft.only", measurements={"searches": SEARCHES},
                       publish=False)
    return routes._resolve(
        task_type=KIND,
        event_types=["chat.completion", "web.search", "draft.only"])


#: Declared names carrying each character a renderer could trip over. Every
#: one is admitted by the route that declares it — which is what makes this a
#: fixture of something a tenant can really hold.
ODD_EVENT_TYPE = "it's a $5 chat-completion"
ODD_QUANTITIES = (
    "it's", "$HOME", "$(whoami)", "back`tick", "back\\slash", 'dou"ble',
    "naïve–日本語", "cache-read", "cache read tokens", "per.cent%", "{braces}",
    "class")


def _odd_names(routes):
    """Names with an apostrophe, a dollar sign, command-like text, a backtick,
    a backslash, a quote, characters outside ASCII, a hyphen, spaces, the two
    characters a token name encodes, braces and a Python keyword."""
    routes._kinds({"key": "report-generation", "uncapped": True})
    routes._call("post", "/api/v1/providers", {"key": "o'reilly & co"})
    routes._call("post", "/api/v1/event-types",
                 {"key": ODD_EVENT_TYPE, "costing_method": "calculated",
                  "source_shape_id": A_JSON_SHAPE,
                  "provider_key": "o'reilly & co"})
    for code in ODD_QUANTITIES:
        routes._quantity(ODD_EVENT_TYPE, code,
                         _a_quantity("caller_supplied", unit="token"))
    routes._quantity(
        ODD_EVENT_TYPE, "read off a hyphenated key",
        _a_quantity("provider_response", path=["x-usage", "total tokens"]))
    routes._publish(ODD_EVENT_TYPE)
    return routes._resolve(task_type="report-generation",
                           event_types=[ODD_EVENT_TYPE])


def _draft_preview(routes):
    """What an admin is shown of configuration not yet published: resolved
    from the draft, stored nowhere, carrying no fingerprint."""
    routes._a_kind()
    routes._event_type("chat.completion", measurements={
        "input_tokens": INPUT_TOKENS}, publish=False)
    return routes._resolve(task_type=KIND, event_types=["chat.completion"],
                           draft_preview=True)


#: Every committed Blueprint, by file name, and what declares it.
BLUEPRINT_FIXTURES = {
    "calculated-cost": _calculated_cost,
    "reported-cost": _reported_cost,
    "direct-task-events": _direct_task_events,
    "explicit-subtasks": _explicit_subtasks,
    "fixed-price": _fixed_price,
    "scaffold": _scaffold,
    "blocked": _blocked,
    "odd-names": _odd_names,
    "draft-preview": _draft_preview,
}

#: What each one must be for the renderer's branches to be the ones named: a
#: fixture that drifted to another verdict would leave its snapshot green over
#: a branch nothing renders any more.
READINESS = {
    "calculated-cost": "complete",
    "reported-cost": "complete",
    "direct-task-events": "complete",
    "explicit-subtasks": "complete",
    "fixed-price": "complete",
    "scaffold": "scaffold",
    "blocked": "blocked",
    "odd-names": "complete",
    "draft-preview": "complete",
}


@pytest.mark.django_db
@pytest.mark.parametrize("name", sorted(BLUEPRINT_FIXTURES))
def test_a_committed_blueprint_is_what_the_route_answers(name):
    routes = _Configured()
    routes.setup_method()

    blueprint = BLUEPRINT_FIXTURES[name](routes)

    assert blueprint["readiness"] == READINESS[name], blueprint["diagnostics"]
    _held(BLUEPRINTS / f"{name}.json", blueprint)


def test_every_committed_blueprint_is_one_this_module_produces():
    """A Blueprint added by hand beside these would be a fixture nothing holds
    to the route."""
    committed = sorted(path.stem for path in BLUEPRINTS.glob("*.json"))

    assert committed == sorted(BLUEPRINT_FIXTURES)
    assert sorted(READINESS) == sorted(BLUEPRINT_FIXTURES)


@pytest.mark.django_db
def test_the_fixtures_cover_what_they_are_named_for():
    """Each fixture is committed for a branch, and this is the branch being
    there: a route that started refusing the declaration, or a resolver that
    stopped emitting the token, would otherwise leave a fixture that renders
    something else under the old name."""
    def resolved(name):
        routes = _Configured()
        routes.setup_method()
        return BLUEPRINT_FIXTURES[name](routes)

    def tokens(blueprint):
        return [argument for call in blueprint["calls"]
                for argument in call["arguments"]]

    def literal(blueprint, name):
        return [token["value"] for token in tokens(blueprint)
                if token["name"] == name]

    assert literal(resolved("fixed-price"), "task_type.pricing_mode") == [
        PRICING_MODE_FIXED]
    assert literal(resolved("reported-cost"),
                   "provider_cost_micros.amount_representation") == [MAJOR]
    assert literal(resolved("explicit-subtasks"),
                   "event_type.response_shape_representation") == ["json"]
    assert literal(resolved("calculated-cost"),
                   "event_type.response_shape_representation") == [
                       "python_object"]
    assert [d["code"] for d in resolved("explicit-subtasks")["diagnostics"]
            ] == ["source_path_convention_mismatch"]
    assert sorted({d["code"] for d in resolved("blocked")["diagnostics"]}) == [
        "constant_value_not_declared", "derived_measurement_unsupported",
        "event_type_not_published",
        "reported_cost_provider_response_unsupported"]
    preview = resolved("draft-preview")
    assert preview["configuration_fingerprint"] is None
    odd = resolved("odd-names")
    assert sorted(literal(odd, "measurements")) == sorted(
        ODD_QUANTITIES + ("read off a hyphenated key",))
    assert literal(odd, "event_type") == [ODD_EVENT_TYPE]


# ---------------------------------------------------------------------------
# The conversion a generated module performs
# ---------------------------------------------------------------------------

def _decimal(text):
    return {"type": "decimal", "text": text}


def _integer(number):
    return {"type": "integer", "text": str(number)}


def _string(text):
    return {"type": "string", "text": text}


#: A reported amount, what it is declared to represent, and its currency. The
#: amounts are spelled as text with the type they arrive as, because the type
#: is half of the question: a float and a decimal string of the same digits
#: are answered differently.
AMOUNTS = [
    (_decimal("0.00123"), MAJOR, "usd"),
    (_decimal("12.5"), MINOR, "usd"),
    (_integer(1230), MICROS, "usd"),
    (_decimal("0.000000"), MAJOR, "usd"),
    (_string("0.1"), MAJOR, "usd"),
    (_string(" 0.5 "), MAJOR, "usd"),
    (_string("1_000"), MICROS, "usd"),
    (_decimal("1.000000000"), MICROS, "usd"),
    (_decimal("-0.5"), MAJOR, "usd"),
    (_decimal("9223372036854.775807"), MAJOR, "usd"),
    (_decimal("0.0000001"), MAJOR, "usd"),
    (_decimal("1.5"), MICROS, "usd"),
    (_decimal("1.0001"), MINOR, "usd"),
    (_decimal("1.00001"), MINOR, "usd"),
    (_decimal("1E-9"), MAJOR, "usd"),
    (_decimal("1E+3"), MAJOR, "usd"),
    (_decimal("1.0000000000000000000000000000001"), MICROS, "usd"),
    (_decimal("123456789012.3456789012345678901234567"), MICROS, "usd"),
    ({"type": "float", "text": "0.1"}, MAJOR, "usd"),
    ({"type": "float", "text": "2.0"}, MICROS, "usd"),
    ({"type": "boolean", "text": "true"}, MICROS, "usd"),
    ({"type": "none", "text": ""}, MICROS, "usd"),
    (_string("free"), MICROS, "usd"),
    (_string(""), MICROS, "usd"),
    (_decimal("Infinity"), MICROS, "usd"),
    (_decimal("NaN"), MICROS, "usd"),
    (_decimal("1E+999999999"), MAJOR, "usd"),
    (_decimal("1E-999999999"), MAJOR, "usd"),
    (_decimal("1." + "0" * 50), MICROS, "usd"),
    (_decimal("10000000000000"), MAJOR, "usd"),
    (_decimal("-10000000000000"), MAJOR, "usd"),
    (_integer(MICROS_LIMIT), MICROS, "usd"),
    (_integer(MICROS_LIMIT + 1), MICROS, "usd"),
    (_integer(1), "hundredths_of_a_farthing", "usd"),
    (_integer(1), MINOR, "eur"),
    (_integer(1), MINOR, "USD"),
    (_integer(1), MINOR, "jpy"),
    (_integer(1), MINOR, ""),
    (_integer(1), MICROS, "jpy"),
    (_integer(1), MAJOR, "xyz"),
] + [(_integer(1), representation, "usd")
     for representation in sorted(AMOUNT_REPRESENTATION_VALUES)
] + [(_integer(1), MINOR, currency)
     for currency in sorted(SUPPORTED_CURRENCIES)]

#: The currency a declaration pins, and the one the supplier returned.
CURRENCIES = [
    ("usd", "usd"), ("usd", None), ("usd", " USD "), ("usd", "eur"),
    ("USD", "usd"), (" Usd ", None), ("xyz", None), ("", "gbp"),
    ("", "jpy"), ("", None), ("usd", ""), ("gbp", "GBP"),
]

#: Which of the two things a refusal is about. A generated module raises its
#: own two types, since it cannot import this tree's.
_REFUSALS = {AmountNotRepresentable: "amount", CurrencyDisagreement: "currency",
             UnknownCurrency: "currency"}


def _the_amount(amount):
    kind, text = amount["type"], amount["text"]
    if kind == "decimal":
        return Decimal(text)
    if kind == "integer":
        return int(text)
    if kind == "float":
        return float(text)
    if kind == "boolean":
        return text == "true"
    if kind == "none":
        return None
    assert kind == "string", kind
    return text


def _answered(operation, *arguments):
    try:
        return {"answer": operation(*arguments)}
    except tuple(_REFUSALS) as refused:
        return {"refused": _REFUSALS[type(refused)]}


def test_the_reported_cost_cases_carry_this_platforms_answers():
    produced = {
        "amounts": [
            {"amount": amount, "representation": representation,
             "currency": currency,
             "expected": _answered(to_micros, _the_amount(amount),
                                   representation, currency)}
            for amount, representation, currency in AMOUNTS],
        "currencies": [
            {"declared": declared, "reported": reported,
             "expected": _answered(pin_currency, declared, reported)}
            for declared, reported in CURRENCIES],
    }

    _held(REPORTED_COST_CASES, produced)


def test_the_currency_table_is_this_platforms():
    """A generated module holds the micros in one minor unit of each currency
    UBB holds, because it converts in the tenant's process and cannot ask.
    The renderer's catalogue is held equal to this file, and this file to the
    one table that knows."""
    _held(MICROS_PER_MINOR_UNIT, {
        currency: minor_units(currency)
        for currency in sorted(SUPPORTED_CURRENCIES)})


def test_the_reported_cost_cases_reach_every_answer_there_is():
    """The vacuity guard: a table of nothing but conversions that succeed, or
    nothing but refusals, would hold a generated module to half the rule."""
    def outcomes(operation, cases):
        return {next(iter(_answered(operation, *case))) for case in cases}

    amounts = [(_the_amount(amount), representation, currency)
               for amount, representation, currency in AMOUNTS]

    assert outcomes(to_micros, amounts) == {"answer", "refused"}
    assert outcomes(pin_currency, CURRENCIES) == {"answer", "refused"}
    assert {_answered(to_micros, *case).get("refused") for case in amounts
            } == {None, "amount", "currency"}
