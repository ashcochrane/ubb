"""The renderer's committed fixtures are what this platform answers (#577, #578).

`ubb-codegen` turns an Integration Blueprint into files, and its tests render
committed Blueprints. A renderer tested against a Blueprint somebody imagined
proves nothing about the one the route answers, so every Blueprint under
`apps/codegen/fixtures/blueprints/` is produced HERE: configuration declared
and published through the tenant's own routes, the Blueprint asked for through
its own route, and the answer held equal to the committed file.

**One file per branch and per target.** A Blueprint is resolved FOR a target,
so each branch is committed twice: under its own name for the Python target,
and under `shell-<name>` for the shell one. The two are the same declarations
wherever both targets can read them. Where they cannot be — a shell file reads
the JSON a web API returns and never a Python library's object — the shell
fixture declares the JSON shape, and `shell-unreadable-shape` is the Python
branch's own configuration asked for as shell, which is blocked.

The same holds for the arithmetic. A generated file converts a supplier's
reported cost to micros in the tenant's own process, and the definition of
that conversion is `to_micros` and `pin_currency` in this tree. The case table
under `apps/codegen/fixtures/` carries this platform's answer to each case, so
the renderer's tests execute the generated conversion against expectations it
did not write. Each case carries two answers, because a shell file holds text
and nothing else: what this platform answers for the amount as the value it
is, and what it answers for the same amount handed over as its text. A cost
read off the supplier's response (#583) is a third kind of case, answered
once: the response's own JSON text, read by Python's `json` at the declared
path and converted, which every target must answer alike.

**To regenerate after a deliberate change**, run this module with
`UBB_WRITE_CODEGEN_FIXTURES=1`: each test then writes its file before holding
it, and the renderer's snapshots are re-taken from the result.

**Where a fixture writes a row directly it says so, at the write.** One thing
is written: the instant of each publication, which no route sets to a value a
committed file can hold.

**The console's Verify answers are this platform's too (#581).** The Code
Builder page shows what Verify answered, and its mock answers with what this
module wrote under `apps/ui/src/features/developers/api/verifications/`: each
committed Blueprint's configuration declared again, its fingerprint asked to
verify a pinned request through the route, and the answer held equal to the
committed file. Two things in an answer are new on every run — the ids of the
records the run made and then discarded, and the instants it made them at — so
the file holds every id-shaped string renumbered in the order it first
appears and every instant-shaped string as one held instant, which is what a
stopped clock would have answered. That is safe only because every such string
in an answer is one the run made, and the test checks it on each run: each
instant is no earlier than the request, and no id appears in the request or in
the committed Blueprint. Nothing else is touched.
"""
import json
import os
import re
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
    CODE_TARGET_PYTHON_SDK as PYTHON,
    CODE_TARGET_SHELL_HTTP as SHELL,
    PRICING_MODE_FIXED)

from ._helpers import (
    A_JSON_SHAPE, A_PYTHON_SHAPE, INPUT_TOKENS, KIND, SEARCHES, SUBTASK_KIND,
    BlueprintRoutes)

FIXTURES = Path(__file__).resolve().parents[4] / "apps" / "codegen" / "fixtures"
BLUEPRINTS = FIXTURES / "blueprints"
REPORTED_COST_CASES = FIXTURES / "reported-cost-cases.json"
RESPONSE_COST_READS = FIXTURES / "response-cost-reads.json"
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
                value_type="integer", constant_value=None):
    return {"display_name": "", "value_type": value_type, "unit": unit,
            "required_for_costing": required, "source_kind": source_kind,
            "source_path": list(path), "constant_value": constant_value}


#: Where the same two token counts sit in each kind of response: on a Python
#: library's object, and in the JSON a web API returns. A shell file reads
#: only the second, so the branches that read a response declare it there.
_A_SUPPLIERS_RESPONSE = {
    A_PYTHON_SHAPE: {"provider": "openai",
                     "input": ["usage", "input_tokens"],
                     "output": ["usage", "output_tokens"]},
    A_JSON_SHAPE: {"provider": "google",
                   "input": ["usageMetadata", "promptTokenCount"],
                   "output": ["usageMetadata", "candidatesTokenCount"]},
}


def _calculated_cost(routes, target=PYTHON, shape=A_PYTHON_SHAPE):
    """A kind of work with a ceiling and a required Grouping Field, and one
    Event Type costed from quantities: two read off the supplier's response,
    one the caller supplies."""
    response = _A_SUPPLIERS_RESPONSE[shape]
    routes._grouping_fields(("environment", "task"))
    routes._kinds({"key": KIND, "task_cogs_ceiling_micros": 5_000_000,
                   "required_grouping_fields": ["environment"]})
    routes._event_type(
        "chat.completion", provider=response["provider"], shape=shape,
        measurements={
            "input_tokens": {**INPUT_TOKENS, "source_path": response["input"]},
            "output_tokens": _a_quantity("provider_response",
                                         path=response["output"]),
            "searches": SEARCHES})
    return routes._resolve(task_type=KIND, event_types=["chat.completion"],
                           target=target)


def _reported_cost(routes, target=PYTHON):
    """An Event Type costed from the supplier's own figure, which the caller
    supplies as a decimal of the major unit."""
    routes._a_kind("web_research")
    routes._event_type(
        "web.search", costing_method="reported", provider="serpapi",
        measurements={"searches": SEARCHES},
        mapping={"source_kind": "caller_supplied",
                 "amount_representation": MAJOR, "currency": "usd"})
    return routes._resolve(task_type="web_research",
                           event_types=["web.search"], target=target)


#: Where a supplier's cost, and the currency it is in, sit in each kind of
#: response — spelled in each shape's own naming, so neither asks for advice.
_A_SUPPLIERS_COST = {
    A_PYTHON_SHAPE: {"provider": "openai",
                     "amount": ["billing", "amount_minor"],
                     "currency": ["billing", "currency"]},
    A_JSON_SHAPE: {"provider": "google",
                   "amount": ["billing", "amountMinor"],
                   "currency": ["billing", "currency"]},
}


def _response_cost(routes, target=PYTHON):
    """An Event Type costed from the supplier's own figure READ OFF ITS
    RESPONSE (#583), as a decimal of the major unit in a currency the
    declaration pins, beside a quantity read off the same JSON response. Every
    target reads JSON, so the branch is complete on both."""
    routes._a_kind("grounded_answer")
    routes._event_type(
        "grounded.search", costing_method="reported", provider="google",
        shape=A_JSON_SHAPE,
        measurements={"input_tokens": {
            **INPUT_TOKENS,
            "source_path": _A_SUPPLIERS_RESPONSE[A_JSON_SHAPE]["input"]}},
        mapping={"source_kind": "provider_response",
                 "amount_representation": MAJOR,
                 "source_path": ["usageMetadata", "totalCost"],
                 "currency": "usd"})
    return routes._resolve(task_type="grounded_answer",
                           event_types=["grounded.search"], target=target)


def _response_cost_read_currency(routes, target=PYTHON, shape=A_PYTHON_SHAPE):
    """The same, with the currency read off the response too: the mapping
    declares a `currency_path` and pins none, so the request's `currency` is
    a runtime value read by that path (#583 D2), and the amount is a count
    of that currency's minor unit."""
    response = _A_SUPPLIERS_COST[shape]
    routes._a_kind("grounded_answer")
    routes._event_type(
        "billed.search", costing_method="reported",
        provider=response["provider"], shape=shape, measurements={},
        mapping={"source_kind": "provider_response",
                 "amount_representation": MINOR,
                 "source_path": response["amount"],
                 "currency_path": response["currency"]})
    return routes._resolve(task_type="grounded_answer",
                           event_types=["billed.search"], target=target)


def _direct_task_events(routes, target=PYTHON):
    """Two Event Types recorded straight against the Task: no Subtask, no
    Grouping Field, no ceiling, nothing read off a response."""
    routes._a_kind("support_reply")
    routes._event_type("reply.sent", measurements={
        "replies": _a_quantity("caller_supplied", unit="reply")})
    routes._event_type("search.run", measurements={"searches": SEARCHES})
    return routes._resolve(task_type="support_reply",
                           event_types=["search.run", "reply.sent"],
                           target=target)


def _explicit_subtasks(routes, target=PYTHON):
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
                           subtask_types=[SUBTASK_KIND], target=target)


def _fixed_price(routes, target=PYTHON):
    """A kind of work sold whole, at one agreed price."""
    routes._kinds({"key": "report", "uncapped": True,
                   "pricing_mode": PRICING_MODE_FIXED})
    routes._event_type("reply.sent", measurements={
        "replies": _a_quantity("caller_supplied", unit="reply")})
    return routes._resolve(task_type="report", event_types=["reply.sent"],
                           target=target)


def _scaffold(routes, target=PYTHON):
    """A tenant that has declared nothing, and selected nothing."""
    return routes._resolve(target=target)


def _blocked(routes, target=PYTHON):
    """Every way a known structure can lack something it cannot run without:
    a constant this Code Builder cannot yet render, a derived quantity, and an
    Event Type never published. Asked for as shell, the first Event Type's
    shape is one more: a Python library's object, which a shell file cannot
    read. Beside them, a cost read off the supplier's JSON response, which
    blocked this Blueprint until #583 and is a complete call since — so the
    one Blueprint holds a complete call among blocked ones."""
    routes._a_kind()
    routes._event_type(
        "chat.completion", shape=A_PYTHON_SHAPE,
        measurements={
            "input_tokens": INPUT_TOKENS,
            "flat_fee": _a_quantity("constant", unit="call",
                                    constant_value="1"),
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
        event_types=["chat.completion", "web.search", "draft.only"],
        target=target)


def _constant(routes, target=PYTHON):
    """A constant quantity declared WITH its value (#571), beside one the
    caller supplies. The declaration is complete, and the call is blocked
    only because this Code Builder version cannot yet generate code that uses
    a constant's value — the code the ticket that renders it (#584) removes,
    when this fixture becomes a complete one."""
    routes._a_kind("flat_rate_call")
    routes._event_type("flat.call", measurements={
        "flat_fee": _a_quantity("constant", unit="call", required=False,
                                value_type="decimal", constant_value="2.5"),
        "searches": SEARCHES})
    return routes._resolve(task_type="flat_rate_call",
                           event_types=["flat.call"], target=target)


#: Declared names carrying each character a renderer could trip over. Every
#: one is admitted by the route that declares it — which is what makes this a
#: fixture of something a tenant can really hold.
ODD_EVENT_TYPE = "it's a $5 chat-completion"
ODD_QUANTITIES = (
    "it's", "$HOME", "$(whoami)", "back`tick", "back\\slash", 'dou"ble',
    "naïve–日本語", "cache-read", "cache read tokens", "per.cent%", "{braces}",
    "class")


def _odd_names(routes, target=PYTHON):
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
                           event_types=[ODD_EVENT_TYPE], target=target)


def _draft_preview(routes, target=PYTHON, shape=A_PYTHON_SHAPE):
    """What an admin is shown of configuration not yet published: resolved
    from the draft, stored nowhere, carrying no fingerprint."""
    routes._a_kind()
    routes._event_type(
        "chat.completion", shape=shape, publish=False,
        measurements={"input_tokens": {
            **INPUT_TOKENS,
            "source_path": _A_SUPPLIERS_RESPONSE[shape]["input"]}})
    return routes._resolve(task_type=KIND, event_types=["chat.completion"],
                           draft_preview=True, target=target)


def _as_shell(declare, **declared):
    """The same branch, asked for as a shell file."""
    return lambda routes: declare(routes, target=SHELL, **declared)


#: Every committed Blueprint, by file name, and what declares it.
BLUEPRINT_FIXTURES = {
    "calculated-cost": _calculated_cost,
    "reported-cost": _reported_cost,
    "response-cost": _response_cost,
    "response-cost-read-currency": _response_cost_read_currency,
    "direct-task-events": _direct_task_events,
    "explicit-subtasks": _explicit_subtasks,
    "fixed-price": _fixed_price,
    "scaffold": _scaffold,
    "blocked": _blocked,
    "constant": _constant,
    "odd-names": _odd_names,
    "draft-preview": _draft_preview,
    "shell-calculated-cost": _as_shell(_calculated_cost, shape=A_JSON_SHAPE),
    "shell-reported-cost": _as_shell(_reported_cost),
    "shell-response-cost": _as_shell(_response_cost),
    "shell-response-cost-read-currency": _as_shell(
        _response_cost_read_currency, shape=A_JSON_SHAPE),
    "shell-direct-task-events": _as_shell(_direct_task_events),
    "shell-explicit-subtasks": _as_shell(_explicit_subtasks),
    "shell-fixed-price": _as_shell(_fixed_price),
    "shell-scaffold": _as_shell(_scaffold),
    "shell-blocked": _as_shell(_blocked),
    "shell-constant": _as_shell(_constant),
    "shell-odd-names": _as_shell(_odd_names),
    "shell-draft-preview": _as_shell(_draft_preview, shape=A_JSON_SHAPE),
    # The Python branch's own declarations, asked for as shell: complete for
    # one target and blocked for the other, by the response shape alone.
    "shell-unreadable-shape": _as_shell(_calculated_cost),
}

#: What each one must be for the renderer's branches to be the ones named: a
#: fixture that drifted to another verdict would leave its snapshot green over
#: a branch nothing renders any more.
READINESS = {
    "calculated-cost": "complete",
    "reported-cost": "complete",
    "response-cost": "complete",
    "response-cost-read-currency": "complete",
    "direct-task-events": "complete",
    "explicit-subtasks": "complete",
    "fixed-price": "complete",
    "scaffold": "scaffold",
    "blocked": "blocked",
    "constant": "blocked",
    "odd-names": "complete",
    "draft-preview": "complete",
    "shell-calculated-cost": "complete",
    "shell-reported-cost": "complete",
    "shell-response-cost": "complete",
    "shell-response-cost-read-currency": "complete",
    "shell-direct-task-events": "complete",
    "shell-explicit-subtasks": "complete",
    "shell-fixed-price": "complete",
    "shell-scaffold": "scaffold",
    "shell-blocked": "blocked",
    "shell-constant": "blocked",
    "shell-odd-names": "complete",
    "shell-draft-preview": "complete",
    "shell-unreadable-shape": "blocked",
}

#: The prefix that says which target a fixture was resolved for.
_SHELL_PREFIX = "shell-"


@pytest.mark.django_db
@pytest.mark.parametrize("name", sorted(BLUEPRINT_FIXTURES))
def test_a_committed_blueprint_is_what_the_route_answers(name):
    routes = _Configured()
    routes.setup_method()

    blueprint = BLUEPRINT_FIXTURES[name](routes)

    assert blueprint["readiness"] == READINESS[name], blueprint["diagnostics"]
    # The name says which target the file was resolved for, and the renderer's
    # tests choose their branches by it.
    assert blueprint["target"] == (
        SHELL if name.startswith(_SHELL_PREFIX) else PYTHON)
    _held(BLUEPRINTS / f"{name}.json", blueprint)


def test_every_committed_blueprint_is_one_this_module_produces():
    """A Blueprint added by hand beside these would be a fixture nothing holds
    to the route."""
    committed = sorted(path.stem for path in BLUEPRINTS.glob("*.json"))

    assert committed == sorted(BLUEPRINT_FIXTURES)
    assert sorted(READINESS) == sorted(BLUEPRINT_FIXTURES)


def test_every_branch_is_committed_for_both_targets():
    """A branch added for one target and forgotten for the other would leave
    the second renderer held to less than the first."""
    python = sorted(name for name in BLUEPRINT_FIXTURES
                    if not name.startswith(_SHELL_PREFIX))
    shell = sorted(name[len(_SHELL_PREFIX):] for name in BLUEPRINT_FIXTURES
                   if name.startswith(_SHELL_PREFIX))

    assert len(python) >= 9
    assert shell == sorted(python + ["unreadable-shape"])


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
        "constant_measurement_not_renderable",
        "derived_measurement_unsupported", "event_type_not_published"]
    # Valid configuration this Code Builder version cannot yet render offers
    # nothing to change (#571); every other code names its fix.
    for name in ("blocked", "shell-blocked"):
        blocked = resolved(name)
        assert sorted(d["code"] for d in blocked["diagnostics"]
                      if d["remediation_request"] is None) == [
            "constant_measurement_not_renderable"]
        # The cost read off the response is a complete call among the
        # blocked ones (#583).
        (search,) = [call for call in blocked["calls"]
                     if literal({"calls": [call]}, "event_type") == [
                         "web.search"]]
        assert search["readiness"] == "complete"
    # A cost read off the response, on its own field, complete on both
    # targets (#583) — with the currency pinned, and with it read too.
    for name in ("response-cost", "shell-response-cost"):
        response_cost = resolved(name)
        assert response_cost["diagnostics"] == []
        assert literal(response_cost,
                       "provider_response_cost_micros.source_path") == [
            ["usageMetadata", "totalCost"]]
        assert literal(response_cost, "currency") == ["usd"]
        assert literal(response_cost,
                       "provider_cost_micros.amount_representation") == []
    for name, shape in (("response-cost-read-currency", A_PYTHON_SHAPE),
                        ("shell-response-cost-read-currency", A_JSON_SHAPE)):
        read_currency = resolved(name)
        assert read_currency["diagnostics"] == []
        assert literal(read_currency, "currency.source_path") == [
            _A_SUPPLIERS_COST[shape]["currency"]]
        assert literal(read_currency,
                       "event_type.response_shape_representation") == [
            "python_object" if shape == A_PYTHON_SHAPE else "json"]
    # A constant declared with its value is complete configuration: the one
    # thing between it and a runnable file is this Code Builder's version.
    for name in ("constant", "shell-constant"):
        constant = resolved(name)
        assert [d["code"] for d in constant["diagnostics"]] == [
            "constant_measurement_not_renderable"]
        (token,) = [token for token in tokens(constant)
                    if token["name"] == "measurements.flat_fee"]
        assert (token["configured"], token["value"]) == (False, None)
    preview = resolved("draft-preview")
    assert preview["configuration_fingerprint"] is None
    for name in ("odd-names", "shell-odd-names"):
        odd = resolved(name)
        assert sorted(literal(odd, "measurements")) == sorted(
            ODD_QUANTITIES + ("read off a hyphenated key",))
        assert literal(odd, "event_type") == [ODD_EVENT_TYPE]

    # A shell file uses no SDK, and reads a response only as JSON.
    read_as_shell = resolved("shell-calculated-cost")
    assert read_as_shell["sdk_major_version"] is None
    assert read_as_shell["diagnostics"] == []
    assert literal(read_as_shell,
                   "event_type.response_shape_representation") == ["json"]
    assert literal(resolved("shell-draft-preview"),
                   "event_type.response_shape_representation") == ["json"]
    assert resolved("shell-draft-preview")["configuration_fingerprint"] is None
    assert literal(resolved("shell-reported-cost"),
                   "provider_cost_micros.amount_representation") == [MAJOR]
    assert literal(resolved("shell-fixed-price"),
                   "task_type.pricing_mode") == [PRICING_MODE_FIXED]
    # The one thing between the Python branch and a shell file is the shape.
    unreadable = resolved("shell-unreadable-shape")
    assert [d["code"] for d in unreadable["diagnostics"]] == [
        "response_shape_not_readable_by_target"]
    assert literal(unreadable,
                   "event_type.response_shape_representation") == [
                       "python_object"]
    assert sorted({d["code"] for d in resolved("shell-blocked")["diagnostics"]
                   }) == [
        "constant_measurement_not_renderable",
        "derived_measurement_unsupported", "event_type_not_published",
        "response_shape_not_readable_by_target"]


# ---------------------------------------------------------------------------
# What Verify answers for the committed Blueprints (#581)
# ---------------------------------------------------------------------------

#: Where the console's mock reads them. The console owns the files; this
#: module is what writes them, so nothing there is an answer the platform did
#: not give.
VERIFICATIONS = (Path(__file__).resolve().parents[4] / "apps" / "ui" / "src"
                 / "features" / "developers" / "api" / "verifications")

#: A fingerprint no Blueprint was ever stored under.
_NEVER_STORED = "sha256:" + "0" * 64


def _record(event_type, **fields):
    return {"event_type": event_type, **fields}


#: Each committed answer: the Blueprint whose fingerprint is verified (or one
#: never stored), the request, and the status it must be answered with. The
#: requests are what the page can send — a sample for every Measurement it
#: shows, a supplier cost only where the call reports one and on the field the
#: call reports it on, and a sample for every Grouping Field a kind the run
#: starts requires — except the five a page cannot make and must still
#: render: the four refusals before a run, and a supplier cost sent on a call
#: that reports none, refused inside it.
VERIFIED = {
    # Every selected Event Type exercised, and its cost the supplier's own:
    # recorded and costed completely, so verified. The tenant declares no
    # price, so the price is unknown — which `verified` does not read.
    "reported-cost": ("reported-cost", {
        "records": [_record("web.search", measurements={"searches": 3},
                            provider_cost_micros=1_250_000)],
        "grouping_fields": {}}, 200),
    # The same for a cost read off the provider's response (#583 D3): the
    # sample is the cost already converted to micros, sent on the field that
    # says where it came from. What the generated code reads and converts is
    # not what Verify tests — running the generated files does.
    "response-cost": ("response-cost", {
        "records": [_record("grounded.search",
                            measurements={"input_tokens": 1200},
                            provider_response_cost_micros=4_200)],
        "grouping_fields": {}}, 200),
    # Costed from Cost Rates the tenant never declared: recorded, its cost
    # unresolved, so not verified, and the acknowledgement names the gap.
    "calculated-cost": ("calculated-cost", {
        "records": [_record("chat.completion", measurements={
            "input_tokens": 1200, "output_tokens": 300, "searches": 2})],
        "grouping_fields": {"environment": "staging"}}, 200),
    # The two required quantities left blank: the record names them missing.
    "calculated-cost-without-required-measurements": ("calculated-cost", {
        "records": [_record("chat.completion", measurements={"searches": 2})],
        "grouping_fields": {"environment": "staging"}}, 200),
    # One of two selected Event Types left out: a partial run, never verified.
    "direct-task-events-partial": ("direct-task-events", {
        "records": [_record("reply.sent", measurements={"replies": 1})],
        "grouping_fields": {}}, 200),
    # Recorded under the Subtask kind the Blueprint starts, with a sample for
    # both kinds' required Grouping Fields.
    "explicit-subtasks": ("explicit-subtasks", {
        "records": [_record("gemini.generate", subtask_type="summarise",
                            measurements={"prompt_tokens": 900,
                                          "candidate_tokens": 250})],
        "grouping_fields": {"environment": "staging", "phase": "draft"}}, 200),
    # A supplier cost on an Event Type costed from rates: refused inside the
    # run, which stops there and says where.
    "calculated-cost-refused-recording": ("calculated-cost", {
        "records": [_record("chat.completion", provider_cost_micros=5,
                            measurements={"input_tokens": 1200,
                                          "output_tokens": 300})],
        "grouping_fields": {"environment": "staging"}}, 200),
    # The refusals before anything runs, one of each.
    "not-found": (None, {
        "records": [_record("chat.completion",
                            measurements={"input_tokens": 1200})],
        "grouping_fields": {"environment": "staging"}}, 404),
    "event-type-not-available": ("blocked", {
        "records": [_record("draft.only", measurements={"searches": 1})],
        "grouping_fields": {}}, 422),
    "blocked": ("blocked", {
        "records": [_record("web.search", measurements={"searches": 1})],
        "grouping_fields": {}}, 409),
    "missing-grouping-field-sample": ("calculated-cost", {
        "records": [_record("chat.completion", measurements={
            "input_tokens": 1200, "output_tokens": 300})],
        "grouping_fields": {}}, 422),
}

_AN_ID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_AN_INSTANT = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?")

#: The one instant every instant of a run reads as.
VERIFIED_AT = "2026-09-01T12:30:00Z"


def _strings(node):
    """Every string an answer holds, at any depth."""
    if isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)
    elif isinstance(node, str):
        yield node


def _made_by_the_run(answer, sent_at, *committed):
    """What `_held_still` rewrites is only what the run made: each instant
    no earlier than the request, and each id one that no committed content
    names. Otherwise holding it still could hide a value that is the same on
    every run, and a change to it would be flattened away. Answers how many
    of each it checked, so a caller can tell a check from an absence."""
    known = "".join(json.dumps(content) for content in committed)
    instants = ids = 0
    for text in _strings(answer):
        if _AN_INSTANT.fullmatch(text):
            assert datetime.fromisoformat(text) >= sent_at, text
            instants += 1
        if _AN_ID.fullmatch(text):
            assert text not in known, text
            ids += 1
    return instants, ids


def _held_still(answer):
    """The answer with what is new on every run held still: each id renumbered
    in the order it first appears — so two places naming one record still name
    one — and every instant read as `VERIFIED_AT`."""
    ids = {}

    def still(node):
        if isinstance(node, dict):
            return {key: still(value) for key, value in node.items()}
        if isinstance(node, list):
            return [still(value) for value in node]
        if isinstance(node, str) and _AN_ID.fullmatch(node):
            return ids.setdefault(
                node, f"00000000-0000-4000-8000-{len(ids) + 1:012d}")
        if isinstance(node, str) and _AN_INSTANT.fullmatch(node):
            return VERIFIED_AT
        return node

    return still(answer)


@pytest.mark.django_db
@pytest.mark.parametrize("name", sorted(VERIFIED))
def test_a_committed_verification_is_what_the_route_answers(name):
    blueprint_name, request, status = VERIFIED[name]
    routes = _Configured()
    routes.setup_method()
    committed = {}
    if blueprint_name is None:
        fingerprint = _NEVER_STORED
    else:
        blueprint = BLUEPRINT_FIXTURES[blueprint_name](routes)
        committed = json.loads(
            (BLUEPRINTS / f"{blueprint_name}.json").read_text(encoding="utf-8"))
        # The fingerprint the console holds for this Blueprint is the one
        # verified: the mock finds the answer by it.
        fingerprint = blueprint["configuration_fingerprint"]
        assert fingerprint == committed["configuration_fingerprint"]

    sent_at = datetime.now(datetime_timezone.utc)
    response = routes._send(
        "post", f"/api/v1/code-builder/blueprints/{fingerprint}/verify",
        request)

    assert response.status_code == status, response.content
    checked = _made_by_the_run(response.json(), sent_at, request, committed)
    if status == 200:
        # A run starts work and records, so its answer holds both.
        assert all(checked), checked
    _held(VERIFICATIONS / f"{name}.json", {
        "blueprint": blueprint_name,
        "configuration_fingerprint": fingerprint,
        "request": request,
        "status": status,
        "answer": _held_still(response.json()),
    })


def test_every_committed_verification_is_one_this_module_produces():
    """An answer added by hand beside these would be one the platform never
    gave."""
    committed = sorted(path.stem for path in VERIFICATIONS.glob("*.json"))

    assert committed == sorted(VERIFIED)


def test_the_verifications_reach_every_state_the_page_renders():
    """The vacuity guard: each state the Verify stage renders is committed at
    least once — verified, a partial run, a gap, a refusal inside the run, and
    each refusal before it."""
    answers = {name: json.loads(
        (VERIFICATIONS / f"{name}.json").read_text(encoding="utf-8"))
        for name in VERIFIED}
    ran = [held["answer"] for held in answers.values() if held["status"] == 200]

    assert {answer["verified"] for answer in ran} == {True, False}
    assert any(answer["unexercised_event_types"] for answer in ran)
    assert any(answer["subtasks"] for answer in ran)
    assert any(answer["refusal"] for answer in ran)
    assert any(record["missing_required_measurement_keys"]
               for answer in ran for record in answer["records"])
    assert sorted({held["answer"]["code"] for held in answers.values()
                   if held["status"] != 200}) == [
        "conflict", "event_type_not_available", "not_found",
        "validation_error"]


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
    # Every way a number can be SPELLED. A shell file is handed text and has
    # no number type to lean on, so its reader is written out by hand — and
    # these are the spellings a hand-written reader gets wrong.
    (_string("+1.5"), MAJOR, "usd"),
    (_string(".5"), MAJOR, "usd"),
    (_string("5."), MAJOR, "usd"),
    (_string("-.5e-3"), MAJOR, "usd"),
    (_string("1e3"), MICROS, "usd"),
    (_string("0.1e1"), MICROS, "usd"),
    (_string("00012.50"), MINOR, "usd"),
    (_string("-0"), MAJOR, "usd"),
    (_string("-0.000"), MICROS, "usd"),
    (_string("0e99"), MAJOR, "usd"),
    (_string("0e-99"), MAJOR, "usd"),
    (_string("1e41"), MICROS, "usd"),
    (_string("10e-41"), MICROS, "usd"),
    (_string("1__0"), MICROS, "usd"),
    (_string("_1_"), MICROS, "usd"),
    (_string("\t12\n"), MICROS, "usd"),
    (_string("1 000"), MICROS, "usd"),
    (_string("1,000"), MICROS, "usd"),
    (_string("0x10"), MICROS, "usd"),
    (_string("--1"), MICROS, "usd"),
    (_string("1e"), MICROS, "usd"),
    (_string("1e+"), MICROS, "usd"),
    (_string("."), MICROS, "usd"),
    (_string("e5"), MICROS, "usd"),
    (_string("1.2.3"), MICROS, "usd"),
    (_string("-"), MICROS, "usd"),
    (_string("_"), MICROS, "usd"),
    (_string("inf"), MICROS, "usd"),
    (_string("-Infinity"), MICROS, "usd"),
    (_string("nan"), MICROS, "usd"),
    (_string("$1.50"), MAJOR, "usd"),
    (_string("1.50 usd"), MAJOR, "usd"),
    (_string("9223372036854775807"), MICROS, "usd"),
    (_string("9223372036854775808"), MICROS, "usd"),
    (_string("-9223372036854775807"), MICROS, "usd"),
    (_string("922337203685477.5807"), MINOR, "usd"),
    (_string("922337203685477.5808"), MINOR, "usd"),
    (_string("09223372036854775807"), MICROS, "usd"),
    (_string("1" + "0" * 30 + "e-30"), MICROS, "usd"),
    (_string("0." + "0" * 45 + "1e46"), MICROS, "usd"),
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

#: Where every response below holds its cost.
COST_PATH = ["cost", "total"]


def _at_the_cost(token):
    """A response holding `token`, written exactly so, at `COST_PATH`."""
    return '{"cost": {"total": ' + token + '}}'


#: A supplier's cost READ OFF ITS RESPONSE (#583): the JSON text the response
#: holds, what the cost is declared to represent, and its currency. What the
#: JSON says is half the question, as the type is above: Python's `json`
#: reads `1` as an integer and `"1"` as a string, and `1.0`, `1e0` and `1.25`
#: as binary floats, which `to_micros` refuses (#193 §D5). A generated file
#: answers each row exactly so on every target — a shell file included, which
#: holds no number type and must see the token as it was written. Every
#: response has the path in it: what is checked is the value at the path, and
#: a path that is not there is the verify script's to find. Every response
#: but the last rows is one Python's `json` reads — `NaN` and `Infinity`
#: among them, which JSON itself does not admit. Those last rows it cannot
#: read, wherever the fault sits, so a tenant's own code never hands them to
#: a generated module, and a shell file, handed the text, must not read them
#: either: jq reads every one.
READ_OFF_A_RESPONSE = [
    # The rows the owner's ruling names (comment 6056978888 on #583).
    (_at_the_cost("1"), MICROS, "usd"),
    (_at_the_cost('"1"'), MICROS, "usd"),
    (_at_the_cost('"1.25"'), MAJOR, "usd"),
    (_at_the_cost('"1.25"'), MINOR, "usd"),
    (_at_the_cost('"1.25"'), MICROS, "usd"),
    (_at_the_cost("1.0"), MAJOR, "usd"),
    (_at_the_cost("1e0"), MICROS, "usd"),
    (_at_the_cost("1.25"), MAJOR, "usd"),
    # Every other way JSON spells a number with a fraction or an exponent —
    # each one a binary float to Python, and each the integer 1 or 15 to a
    # jq that prints a number by its value.
    (_at_the_cost("1E0"), MICROS, "usd"),
    (_at_the_cost("1e+0"), MICROS, "usd"),
    (_at_the_cost("0.1e1"), MICROS, "usd"),
    (_at_the_cost("10e-1"), MICROS, "usd"),
    (_at_the_cost("1.5e1"), MICROS, "usd"),
    (_at_the_cost("1e2"), MICROS, "usd"),
    (_at_the_cost("1.000"), MICROS, "usd"),
    (_at_the_cost("-0.0"), MICROS, "usd"),
    # A zero cost is a cost (owner's ruling 5), and a negative one converts
    # as it does for a caller (the recording's bound is the server's).
    (_at_the_cost("0"), MICROS, "usd"),
    (_at_the_cost("-0"), MICROS, "usd"),
    (_at_the_cost('"0"'), MAJOR, "usd"),
    (_at_the_cost("-1"), MICROS, "usd"),
    (_at_the_cost("1"), MAJOR, "usd"),
    (_at_the_cost("1"), MINOR, "usd"),
    (_at_the_cost("7"), MINOR, "jpy"),
    # Where a double stops carrying an integer exactly: the largest
    # fifteen-digit one, the first sixteen-digit one, the last a double
    # holds exactly and the first it does not, and the column's own bound.
    # Each is read as written, never as the double a jq would make of it.
    (_at_the_cost("999999999999999"), MICROS, "usd"),
    (_at_the_cost("1000000000000000"), MICROS, "usd"),
    (_at_the_cost("9007199254740992"), MICROS, "usd"),
    (_at_the_cost("9007199254740993"), MICROS, "usd"),
    (_at_the_cost(str(MICROS_LIMIT)), MICROS, "usd"),
    (_at_the_cost(str(MICROS_LIMIT + 1)), MICROS, "usd"),
    (_at_the_cost("12345678901234567890123"), MICROS, "usd"),
    # A decimal string is the supplier's decimal, whatever it spells.
    (_at_the_cost('"0.0000001"'), MAJOR, "usd"),
    (_at_the_cost('" 1.5 "'), MAJOR, "usd"),
    (_at_the_cost('"1e3"'), MICROS, "usd"),
    (_at_the_cost('"9007199254740993"'), MICROS, "usd"),
    (_at_the_cost('""'), MICROS, "usd"),
    (_at_the_cost('"free"'), MICROS, "usd"),
    (_at_the_cost('"12\\\\"'), MICROS, "usd"),
    (_at_the_cost('"1\\u0000"'), MICROS, "usd"),
    # What is not an amount at all.
    (_at_the_cost("true"), MICROS, "usd"),
    (_at_the_cost("null"), MICROS, "usd"),
    (_at_the_cost("{}"), MICROS, "usd"),
    (_at_the_cost("[1]"), MICROS, "usd"),
    (_at_the_cost("NaN"), MICROS, "usd"),
    # The rest of the response, written to mislead a reader of its text:
    # escaped quotes and backslashes before the path, a key that looks like a
    # number, floats beside the cost, whitespace of every kind, a repeated key
    # (the last one is the value, to Python and to jq), and an escaped key.
    ('{"a\\"": 1.0, "cost": {"total": 7}}', MICROS, "usd"),
    ('{"x\\\\\\\\": "1.0", "cost": {"total": 8}}', MICROS, "usd"),
    ('{"1.0": {"total": 2.5}, "cost": {"items": [1e0, 2.5], "total": 9}}',
     MICROS, "usd"),
    ('{\r\n\t"cost" :\r\n\t{ "total" :\t12 }\r\n}\r\n', MICROS, "usd"),
    ('{"cost": {"total": "2", "total": 1.0}}', MICROS, "usd"),
    ('{"cost": {"total": 1.5, "total": 3}}', MICROS, "usd"),
    ('{"\\u0063ost": {"total": 42}}', MICROS, "usd"),
    ('{"t": true, "f": false, "n": null, "cost": {"total": 1e0}}',
     MICROS, "usd"),
    # What Python's `json` reads beside JSON, off the path, leaves the cost
    # to be read.
    ('{"x": NaN, "cost": {"total": 5}}', MICROS, "usd"),
    ('{"x": [Infinity, -Infinity], "cost": {"total": "5"}}', MICROS, "usd"),
    # What it does not read makes the whole response unreadable, wherever it
    # sits: a sign of `+`, leading zeros, a point with no digit on one side,
    # `nan` and `inf` spelled any other way, a NUL after a number or inside a
    # string, and a byte-order mark.
    *[('{"x": ' + token + ', "cost": {"total": 5}}', MICROS, "usd")
      for token in ("+1", "01", "-01", ".5", "-.5", "1.", "1.e5", "nan",
                    "-nan", "NAN", "nan1", "inf", "-inf", "infinity", "INF",
                    "+Infinity", "-NaN")],
    *[(_at_the_cost(token), MICROS, "usd")
      for token in ("+1", "01", ".5", "1.", "nan", "inf")],
    ('{"x": "a\x00b", "cost": {"total": 5}}', MICROS, "usd"),
    ('{"x": 1\x00, "cost": {"total": 5}}', MICROS, "usd"),
    (_at_the_cost("1\x00"), MICROS, "usd"),
    ('\ufeff{"cost": {"total": 5}}', MICROS, "usd"),
]


def _read_at_the_cost(document):
    """What Python's `json` puts at `COST_PATH`."""
    value = json.loads(document)
    for segment in COST_PATH:
        value = value[segment]
    return value


def _the_read(document, representation, currency):
    """What a cost read off `document` is answered: Python's `json` and then
    `to_micros`. A response `json` cannot read is refused as a RESPONSE: a
    tenant's own code fails to parse it before a generated module is handed
    anything, and a generated file reading the text must refuse it as well."""
    try:
        value = _read_at_the_cost(document)
    except ValueError:
        return {"refused": "response"}
    return _answered(to_micros, value, representation, currency)


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
    """Each amount is answered twice. `expected` is for the value the case
    stands for, with its type. `expected_as_text` is for the same amount
    handed over as its text, which is all a shell file can hold: there a
    decimal, an integer and a float of the same digits are one argument, so
    the answer is this platform's for the text. They differ exactly where
    the type was the reason — a binary float is refused, and its text is the
    decimal it spells.

    A cost read off a response is answered ONCE (#583): the response is the
    supplier's JSON, and what is at the path is what Python's `json` reads
    there, so a shell file reading the same text must answer the same."""
    produced = {
        "amounts": [
            {"amount": amount, "representation": representation,
             "currency": currency,
             "expected": _answered(to_micros, _the_amount(amount),
                                   representation, currency),
             "expected_as_text": _answered(to_micros, amount["text"],
                                           representation, currency)}
            for amount, representation, currency in AMOUNTS],
        "currencies": [
            {"declared": declared, "reported": reported,
             "expected": _answered(pin_currency, declared, reported)}
            for declared, reported in CURRENCIES],
        "read_off_a_response": [
            {"document": document, "path": COST_PATH,
             "representation": representation, "currency": currency,
             "expected": _the_read(document, representation, currency)}
            for document, representation, currency in READ_OFF_A_RESPONSE],
    }

    _held(REPORTED_COST_CASES, produced)


def _a_cost_read_at_the_cost(routes, representation, currency):
    """An Event Type that reads nothing off its response but the supplier's
    cost, at `COST_PATH`, as `representation`, in a currency it pins."""
    routes._a_kind("grounded_answer")
    routes._event_type(
        "grounded.search", costing_method="reported", provider="google",
        shape=A_JSON_SHAPE, measurements={},
        mapping={"source_kind": "provider_response",
                 "amount_representation": representation,
                 "source_path": list(COST_PATH), "currency": currency})


@pytest.mark.django_db
def test_the_blueprints_the_rows_are_read_through_are_what_the_route_answers():
    """The renderers are held to the rows above through a Blueprint the
    routes answer, one for each representation and currency the rows are
    read as and each target — not through a committed Blueprint varied in the
    test (ADR-0016 §5), since the routes produce these as readily. The one
    exception is a currency UBB does not hold, which the routes refuse to
    pin: that document the renderer's test derives, and says so."""
    produced = {}
    for representation, currency in sorted({
            (representation, currency)
            for _, representation, currency in READ_OFF_A_RESPONSE
            if currency in SUPPORTED_CURRENCIES}):
        routes = _Configured()
        routes.setup_method()
        _a_cost_read_at_the_cost(routes, representation, currency)
        for target in (PYTHON, SHELL):
            blueprint = routes._resolve(task_type="grounded_answer",
                                        event_types=["grounded.search"],
                                        target=target)
            assert blueprint["readiness"] == "complete", blueprint["diagnostics"]
            produced.setdefault(f"{representation} {currency}", {})[target] = (
                blueprint)

    # Every representation there is, so no row is read through a document
    # this test did not produce but for the currency the routes refuse.
    assert {key.split()[0] for key in produced} == {MICROS, MAJOR, MINOR}
    _held(RESPONSE_COST_READS, produced)


def test_a_cost_read_off_a_response_is_answered_as_ruled():
    """The rows the owner's ruling names, answered as it names them: an
    integer and a decimal string are read, every number written with a
    fraction or an exponent is a binary float and refused, a zero is a cost,
    and an integer past what a double carries is still carried exactly."""
    def answer(token, representation=MICROS):
        return _answered(to_micros, _read_at_the_cost(_at_the_cost(token)),
                         representation, "usd")

    assert answer("1") == {"answer": 1}
    assert answer('"1"') == {"answer": 1}
    assert answer('"1.25"', MAJOR) == {"answer": 1_250_000}
    for floating in ("1.0", "1e0", "1.25", "1E0", "0.1e1", "1.5e1"):
        assert answer(floating, MAJOR) == {"refused": "amount"}, floating
    assert answer("0") == answer('"0"') == answer("-0") == {"answer": 0}
    assert answer("999999999999999") == {"answer": 999_999_999_999_999}
    assert answer("9007199254740993") == {"answer": 9_007_199_254_740_993}
    # And every one of them is a row the renderers are held to.
    documents = {document for document, _, _ in READ_OFF_A_RESPONSE}
    for token in ("1", '"1"', '"1.25"', "1.0", "1e0", "1.25", "0", '"0"',
                  "999999999999999", "1000000000000000", "9007199254740993"):
        assert _at_the_cost(token) in documents, token


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
    assert {_the_read(*case).get("refused") for case in READ_OFF_A_RESPONSE
            } == {None, "amount", "currency", "response"}


def test_an_amount_as_text_is_answered_differently_only_where_the_type_was_why():
    """The second answer of each case is not a second rule. Handing an amount
    over as its text changes this platform's answer for a binary float and
    for nothing else in the table: a flag's text and a missing amount's are
    refused as they were, and every other case is the same value either way."""
    differ = sorted({
        amount["type"] for amount, representation, currency in AMOUNTS
        if _answered(to_micros, _the_amount(amount), representation, currency)
        != _answered(to_micros, amount["text"], representation, currency)})

    assert differ == ["float"]
