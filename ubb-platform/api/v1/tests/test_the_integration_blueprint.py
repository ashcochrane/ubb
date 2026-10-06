"""The Integration Blueprint, through its two routes (#576, #184 §2-§4, §7, §8,
§11, §13 steps 1-3).

A tenant developer sends a selection — a target, a kind of work, the Event
Types that happen inside it, and optionally the Subtask kinds it creates — and
gets back what the integration code must MEAN: every call, every token of
every call with the class that says where its value comes from, how ready each
call is, and what stands in the way. Resolving from published configuration
also stores the resolved content, and the Blueprint carries that content's
hash.

**Everything here goes through the tenant's own routes.** Configuration is
declared and published through the registries' routes, the Blueprint is asked
for and read back through its own two, and every assertion is over a response
body or over what the database holds afterwards. Nothing imports the resolver:
a consumer cannot, and a test that could would be free to agree with a mistake
the response does not show.

**Where a fixture writes a row directly it says so, at the write.** Each is
something no route in this module's reach produces: a state the tables admit
and the registries refuse (a kind requiring a Grouping Field nobody declared,
a Grouping Field retired), a value no route sets to something a test can know
(a tenant's secrets, a key's role, the instant of a publication), and the
rules and markup a metering-only tenant has no route to declare.
"""
import json
import re
import uuid
from pathlib import Path

import pytest
from django.apps import apps as django_apps
from django.test import Client
from django.utils import timezone

from api.v1.api import api
from apps.platform.code_builder import token_names
from apps.platform.code_builder.models import BlueprintSnapshot
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox
from apps.platform.tenants.tasks import (
    CONFIG_MODEL_LABELS, reset_sandbox_tenant_sync)

from ._helpers import (
    A_JSON_SHAPE, A_PYTHON_SHAPE, BLUEPRINTS, EVENT, INPUT_TOKENS, KIND,
    SEARCHES, SUBTASK_KIND, BlueprintRoutes as _Routes, a_tenant)

#: The committed contract, which is what a consumer holds. Two of the checks
#: below are about it rather than about a response: which inputs the request
#: publishes, and which operations exist for a call to name.
CONTRACT = json.loads(
    (Path(__file__).resolve().parents[4] / "openapi" / "v1.json")
    .read_text(encoding="utf-8"))

START = "api_v1_task_endpoints_start_task"
RECORD = "api_v1_metering_endpoints_record_usage"
CLOSE = "api_v1_task_endpoints_close_task"

A_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")

def _operations():
    """`{operationId: (METHOD, path, operation)}` for the committed contract."""
    found = {}
    for path, methods in CONTRACT["paths"].items():
        for method, operation in methods.items():
            if isinstance(operation, dict) and "operationId" in operation:
                found[operation["operationId"]] = (method.upper(), path,
                                                   operation)
    return found


def _schema(name):
    return CONTRACT["components"]["schemas"][name]


def _request_schema(operation):
    """The schema of an operation's body, or `None` for one that takes none."""
    body = operation.get("requestBody")
    if not body:
        return None
    ref = body["content"]["application/json"]["schema"]["$ref"]
    return _schema(ref.rsplit("/", 1)[1])


def _request_properties(operation):
    """The body properties an operation publishes, or an empty set for none."""
    schema = _request_schema(operation)
    return set(schema["properties"]) if schema else set()


def _unpublished_keys(body, schema, at="body"):
    """Every key of `body` its schema does not publish, at any depth.

    Follows a list of objects into the schema of its rows, so a skeleton that
    spells a row's field wrongly is found as readily as one that spells a
    top-level field wrongly.
    """
    found = []
    for key, value in body.items():
        published = schema["properties"].get(key)
        if published is None:
            found.append(f"{at}.{key}")
            continue
        rows = published.get("items", {}).get("$ref")
        if rows and isinstance(value, list):
            for row in value:
                found += _unpublished_keys(
                    row, _schema(rows.rsplit("/", 1)[1]), f"{at}.{key}[]")
    return found


def _every_row():
    """Every row of every table, by model label — the whole database.

    Derived from the app registry rather than listed, so a table added after
    this was written is in the comparison on the day it exists.
    """
    return {
        model._meta.label: sorted(
            (json.dumps(row, sort_keys=True, default=str)
             for row in model._base_manager.values()))
        for model in django_apps.get_models()
        if model._meta.managed and not model._meta.proxy
    }


def _tables_that_differ(before, after):
    return sorted(label for label in before.keys() | after.keys()
                  if before.get(label) != after.get(label))


# -- reading a Blueprint the way a consumer does ---------------------------

def _named(call, name):
    return [argument for argument in call["arguments"]
            if argument["name"] == name]


def _one(call, name, binding_class=None):
    found = [argument for argument in _named(call, name)
             if binding_class in (None, argument["binding_class"])]
    assert len(found) == 1, (name, binding_class, call["arguments"])
    return found[0]


def _literal(call, name):
    """The one literal a call carries under `name`, or `None` for none."""
    found = [argument["value"] for argument in _named(call, name)
             if argument["binding_class"] == "platform_known"]
    return found[0] if len(found) == 1 else None


def _calls(blueprint, operation):
    return [call for call in blueprint["calls"]
            if call["operation_id"] == operation]


def _the_start(blueprint):
    """The start of the Task itself: the one that names no parent."""
    found = [call for call in _calls(blueprint, START)
             if not _named(call, "parent_task_id")]
    assert len(found) == 1, blueprint["calls"]
    return found[0]


def _the_subtask_start(blueprint, kind=SUBTASK_KIND):
    found = [call for call in _calls(blueprint, START)
             if _named(call, "parent_task_id")
             and _literal(call, "task_type") == kind]
    assert len(found) == 1, blueprint["calls"]
    return found[0]


def _the_record(blueprint, event_type=EVENT):
    found = [call for call in _calls(blueprint, RECORD)
             if _literal(call, "event_type") == event_type]
    assert len(found) == 1, blueprint["calls"]
    return found[0]


def _codes(blueprint, severity=None):
    return sorted(diagnostic["code"] for diagnostic in blueprint["diagnostics"]
                  if severity in (None, diagnostic["severity"]))


def _diagnostic(blueprint, code):
    found = [diagnostic for diagnostic in blueprint["diagnostics"]
             if diagnostic["code"] == code]
    assert len(found) == 1, (code, blueprint["diagnostics"])
    return found[0]


# ---------------------------------------------------------------------------
# What is asked, and what is inferred
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTheSelectionIsTheOnlyInput(_Routes):
    def test_the_request_publishes_the_selection_and_nothing_else(self):
        """The three universal inputs, the explicit Subtask branch, and the
        switch that asks for a draft preview. Read off the committed contract,
        which is the only place a consumer learns what it may send."""
        _, _, operation = _operations()[
            "api_v1_code_builder_endpoints_resolve_blueprint"]

        assert _request_properties(operation) == {
            "target", "task_type", "event_types", "subtask_types",
            "draft_preview"}

    def test_a_key_the_request_does_not_publish_is_not_an_input(self):
        """Sent beside a real selection, it changes nothing about the answer —
        including the fingerprint, which is the hash of everything resolved."""
        self._complete_configuration()
        asked = self._complete()

        with_a_stray = self._complete(
            measurements=["token_count"], source_path=["usage", "tokens"],
            task_cogs_ceiling_micros=1)

        assert with_a_stray == asked

    def test_where_no_mapping_resolves_the_blueprint_asks_and_takes_no_path(
            self):
        """The fifth question is put to the developer, not answered here: an
        Event Type reading a supplier's response against no declared shape is
        blocked, and what the diagnostic carries is the request that declares
        one at the surface that owns it."""
        self._a_kind()
        self._event_type(shape="")

        blueprint = self._complete()

        asked = _diagnostic(blueprint, "response_shape_not_declared")
        assert asked["severity"] == "blocking"
        assert (asked["object_kind"], asked["key"], asked["field"]) == (
            "event_type", EVENT, "source_shape_id")
        assert asked["remediation_request"]["operation_id"] == (
            "api_v1_event_type_endpoints_revise_event_type")
        assert _the_record(blueprint)["readiness"] == "blocked"

    def test_a_target_outside_the_two_is_refused(self):
        self._complete_configuration()

        refused = self._send("post", BLUEPRINTS,
                             {"target": "typescript_sdk", "task_type": KIND,
                              "event_types": [EVENT]})

        assert refused.status_code == 422, refused.content
        assert refused.json()["code"] == "validation_error"
        assert BlueprintSnapshot.objects.count() == 0

    @pytest.mark.parametrize("field", ["event_types", "subtask_types"])
    def test_a_selection_naming_more_than_fifty_is_refused(self, field):
        """The resolution reads several rows per name at the Read floor, so
        the bound is what keeps it a cheap question. Fifty is accepted."""
        self._complete_configuration()
        names = [f"name.{position}" for position in range(51)]

        refused = self._send("post", BLUEPRINTS,
                             {"target": "python_sdk", field: names})
        accepted = self._send("post", BLUEPRINTS,
                              {"target": "python_sdk", field: names[:50]})

        assert refused.status_code == 422, refused.content
        assert refused.json()["code"] == "validation_error"
        assert accepted.status_code == 200, accepted.content
        # Fifty DISTINCT names: a selection is a set, so naming one twice
        # does not count twice.
        repeated = self._send("post", BLUEPRINTS, {
            "target": "python_sdk", field: [*names[:50], names[0]]})
        assert repeated.status_code == 200, repeated.content
        # And the number a caller is told is the number that is enforced.
        _, _, operation = _operations()[
            "api_v1_code_builder_endpoints_resolve_blueprint"]
        assert "more than 50 " in operation["description"]

    def test_every_literal_says_which_declaration_it_came_from(self):
        """Nothing UBB filled in arrives unexplained: a configured literal
        names the object it was read from."""
        self._complete_configuration()

        blueprint = self._complete(subtask_types=[SUBTASK_KIND])

        literals = [argument for call in blueprint["calls"]
                    for argument in call["arguments"]
                    if argument["binding_class"] == "platform_known"]
        assert len(literals) >= 8, literals
        for literal in literals:
            assert literal["configured"] is True, literal
            assert literal["provenance"]["object_kind"], literal
            assert literal["provenance"]["key"], literal

    def test_an_event_types_facts_carry_the_publication_they_came_from(self):
        published = self._complete_configuration()

        record = _the_record(self._complete())

        from_the_event_type = _one(record, "event_type")["provenance"]
        assert from_the_event_type == {
            "object_kind": "event_type", "key": EVENT,
            "published_revision": published["published_revision"],
            "published_at": published["published_at"]}
        assert published["published_revision"] == 1
        assert published["published_at"]
        # The quantities beneath it came from the same publication.
        for name in ("measurements", "measurements.input_tokens",
                     "measurements.searches"):
            for argument in _named(record, name):
                assert argument["provenance"] == from_the_event_type, argument

    def test_a_kind_of_work_carries_no_date(self):
        """A kind has no publish record to date it by; what tells a held file
        from a current one is the fingerprint."""
        self._complete_configuration()

        blueprint = self._complete(subtask_types=[SUBTASK_KIND])

        assert _one(_the_start(blueprint), "task_type")["provenance"] == {
            "object_kind": "task_type", "key": KIND,
            "published_revision": None, "published_at": None}
        assert _one(_the_subtask_start(blueprint),
                    "task_type")["provenance"] == {
            "object_kind": "subtask_type", "key": SUBTASK_KIND,
            "published_revision": None, "published_at": None}

    def test_a_kind_of_work_says_how_it_is_sold_and_what_it_may_spend(self):
        """Neither is sent on a start; both are what the kind declares, beside
        the call that starts the work. A ceiling is a figure or the
        declaration that there is none — never a figure of nothing."""
        self._complete_configuration()

        blueprint = self._complete(subtask_types=[SUBTASK_KIND])
        capped, uncapped = _the_start(blueprint), _the_subtask_start(blueprint)

        from_the_kind = _one(capped, "task_type")["provenance"]
        assert _one(capped, "task_type.pricing_mode")["value"] == (
            "event_priced")
        assert _one(capped, "task_type.uncapped")["value"] is False
        assert _one(capped, "task_type.task_cogs_ceiling_micros")[
            "value"] == 5_000_000
        for name in ("task_type.pricing_mode", "task_type.uncapped",
                     "task_type.task_cogs_ceiling_micros"):
            assert _one(capped, name)["provenance"] == from_the_kind
            assert _one(capped, name)["binding_class"] == "platform_known"
        assert _one(uncapped, "task_type.uncapped")["value"] is True
        assert _named(uncapped, "task_type.task_cogs_ceiling_micros") == []

    def test_an_event_type_says_what_it_published_about_itself(self):
        """How it is costed, and of each quantity what kind of number it is,
        what it counts and whether a cost needs it."""
        self._complete_configuration()

        record = _the_record(self._complete())

        from_the_event_type = _one(record, "event_type")["provenance"]
        declared = {
            "event_type.costing_method": "calculated",
            "measurements.input_tokens.value_type": "integer",
            "measurements.input_tokens.unit": "token",
            "measurements.input_tokens.required_for_costing": True,
            "measurements.searches.unit": "search",
            "measurements.searches.required_for_costing": False,
        }
        for name, value in declared.items():
            fact = _one(record, name)
            assert fact["value"] == value, name
            assert fact["binding_class"] == "platform_known", name
            assert fact["provenance"] == from_the_event_type, name

    def test_a_revised_event_types_facts_are_the_published_ones(self):
        """The Event Type's own route serves the draft once an edit lands, so
        this document is the only place the published facts can be read."""
        self._complete_configuration()
        self._call("put", f"/api/v1/event-types/{EVENT}/measurements/"
                          "input_tokens",
                   {**INPUT_TOKENS, "unit": "character",
                    "required_for_costing": False})
        live = self._call("get", f"/api/v1/event-types/{EVENT}")
        assert {m["code"]: m["unit"] for m in live["measurements"]}[
            "input_tokens"] == "character"

        record = _the_record(self._complete())

        assert _one(record, "measurements.input_tokens.unit")[
            "value"] == "token"
        assert _one(record, "measurements.input_tokens.required_for_costing")[
            "value"] is True

    def test_the_response_shape_and_what_it_is_travel_with_the_paths(self):
        """Which shape the paths are written against, and whether that shape
        is a JSON document or a Python object — UBB's own declaration about
        the shape, which is what decides how a path is walked."""
        self._a_kind()
        self._event_type("from.an.object", shape=A_PYTHON_SHAPE)
        self._event_type("from.json", shape=A_JSON_SHAPE)
        self._event_type("from.a.wrapper", shape="custom", label="wrapper")
        self._event_type("reads.nothing",
                         measurements={"searches": SEARCHES})

        blueprint = self._complete(event_types=[
            "from.an.object", "from.json", "from.a.wrapper", "reads.nothing"])

        def shape_of(event_type):
            record = _the_record(blueprint, event_type)
            return [(a["name"], a["value"]) for a in record["arguments"]
                    if "shape" in a["name"]]

        assert shape_of("from.an.object") == [
            ("event_type.source_shape_id", A_PYTHON_SHAPE),
            ("event_type.response_shape_representation", "python_object")]
        assert shape_of("from.json") == [
            ("event_type.source_shape_id", A_JSON_SHAPE),
            ("event_type.response_shape_representation", "json")]
        # A wrapper declares no representation, so none is claimed for it.
        assert shape_of("from.a.wrapper") == [
            ("event_type.source_shape_id", "custom")]
        # Nothing is read off the response, so its shape says nothing.
        assert shape_of("reads.nothing") == []

    def test_the_supplier_is_the_event_types_own(self):
        self._complete_configuration()

        supplier = _one(_the_record(self._complete()), "provider")

        assert (supplier["binding_class"], supplier["value"]) == (
            "platform_known", "openai")
        assert supplier["provenance"]["object_kind"] == "provider"
        assert supplier["provenance"]["key"] == "openai"

    def test_an_event_type_with_no_supplier_sends_none(self):
        self._a_kind()
        self._event_type()

        assert _named(_the_record(self._complete()), "provider") == []

    def test_the_document_says_which_shape_it_is_and_what_it_was_resolved_for(
            self):
        self._complete_configuration()

        for_python = self._complete()
        for_shell = self._complete(target="shell_http")

        for blueprint, target, sdk in ((for_python, "python_sdk", 3),
                                       (for_shell, "shell_http", None)):
            assert blueprint["schema_version"] == 1
            assert blueprint["renderer_contract_version"] == 1
            assert blueprint["target"] == target
            assert blueprint["sdk_major_version"] == sdk

    def test_the_same_selection_in_another_order_is_the_same_blueprint(self):
        """A selection is a set. Two pages sending the same Event Types in a
        different order must not hold two fingerprints for one integration."""
        self._complete_configuration()
        self._event_type("embedding.create")

        one = self._complete(event_types=[EVENT, "embedding.create"])
        other = self._complete(event_types=["embedding.create", EVENT, EVENT])

        assert other == one
        assert BlueprintSnapshot.objects.count() == 1


# ---------------------------------------------------------------------------
# The three binding classes, token by token
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestEachTokenHasItsOwnClass(_Routes):
    def test_a_known_key_sits_beside_a_runtime_value_on_one_call(self):
        """The Grouping Field's key is the tenant's own declaration and is a
        literal; the value under it is known only when the work starts and is
        a required parameter. One call, one wire field, two classes."""
        self._complete_configuration()

        start = _the_start(self._complete())

        key = _one(start, "grouping_fields")
        value = _one(start, "grouping_fields.environment")
        assert (key["binding_class"], key["value"]) == (
            "platform_known", "environment")
        assert key["parameter_name"] is None
        assert key["provenance"] == {
            "object_kind": "grouping_field", "key": "environment",
            "published_revision": None, "published_at": None}
        assert (value["binding_class"], value["parameter_name"]) == (
            "runtime_bound", "environment")
        assert value["value"] is None
        # Required because the kind of work declares it.
        assert value["provenance"]["object_kind"] == "task_type"
        assert value["provenance"]["key"] == KIND

    def test_a_quantity_read_from_the_response_is_a_runtime_root_and_a_known_path(
            self):
        self._complete_configuration()

        record = _the_record(self._complete())

        assert "input_tokens" in [a["value"] for a in
                                  _named(record, "measurements")]
        root = _one(record, "measurements.input_tokens")
        assert (root["binding_class"], root["parameter_name"]) == (
            "runtime_bound", "response")
        path = _one(record, "measurements.input_tokens.source_path")
        assert (path["binding_class"], path["value"]) == (
            "platform_known", ["usage", "input_tokens"])

    def test_a_quantity_the_caller_supplies_is_a_required_parameter(self):
        self._complete_configuration()

        record = _the_record(self._complete())

        supplied = _one(record, "measurements.searches")
        assert (supplied["binding_class"], supplied["parameter_name"]) == (
            "runtime_bound", "searches")
        assert _named(record, "measurements.searches.source_path") == []

    def test_a_cost_the_caller_supplies_is_the_required_parameter_reported_cost(
            self):
        self._a_kind()
        self._event_type(
            costing_method="reported", measurements={},
            mapping={"source_kind": "caller_supplied",
                     "amount_representation": "major_units_decimal",
                     "currency": "usd"})

        blueprint = self._complete()
        record = _the_record(blueprint)

        cost = _one(record, "provider_cost_micros")
        assert (cost["binding_class"], cost["parameter_name"]) == (
            "runtime_bound", "reported_cost")
        assert _one(record, "provider_cost_micros.amount_representation")[
            "value"] == "major_units_decimal"
        currency = _one(record, "currency")
        assert (currency["binding_class"], currency["value"]) == (
            "platform_known", "usd")
        assert blueprint["readiness"] == "complete"

    def test_the_credential_is_a_reference_and_nothing_else_is(self):
        """Every call authenticates, and what it carries is the NAME of an
        environment variable. The host is not on the withhold list, so no
        token of any call is a second secret reference."""
        self._complete_configuration()

        blueprint = self._complete(subtask_types=[SUBTASK_KIND])

        assert len(blueprint["calls"]) >= 4
        for call in blueprint["calls"]:
            credential = _one(call, "api_key")
            assert credential["binding_class"] == "secret_reference"
            assert credential["environment_variable"] == "UBB_API_KEY"
            assert credential["value"] is None
            assert credential["parameter_name"] is None
            references = [argument for argument in call["arguments"]
                          if argument["binding_class"] == "secret_reference"
                          or argument["environment_variable"] is not None]
            assert references == [credential]

    def test_each_class_fills_its_own_field_and_no_other(self):
        self._complete_configuration()

        blueprint = self._complete(subtask_types=[SUBTASK_KIND])

        seen = set()
        for call in blueprint["calls"]:
            for argument in call["arguments"]:
                seen.add(argument["binding_class"])
                filled = {field for field in (
                    "value", "parameter_name", "environment_variable")
                    if argument[field] is not None}
                assert filled == {{"platform_known": "value",
                                   "runtime_bound": "parameter_name",
                                   "secret_reference": "environment_variable"}[
                    argument["binding_class"]]}, argument
        assert seen == {"platform_known", "runtime_bound", "secret_reference"}

    def test_a_scoped_value_lands_at_the_call_its_scope_names(self):
        """Task-scoped on the Task's start, Subtask-scoped on the Subtask's,
        and neither on the record call."""
        self._complete_configuration()

        blueprint = self._complete(subtask_types=[SUBTASK_KIND])

        def fields_of(call):
            return [a["value"] for a in _named(call, "grouping_fields")]

        assert fields_of(_the_start(blueprint)) == ["environment"]
        assert fields_of(_the_subtask_start(blueprint)) == ["phase"]
        assert fields_of(_the_record(blueprint)) == []

    def test_the_lifecycle_is_start_then_subtask_then_record_then_close(self):
        self._complete_configuration()

        blueprint = self._complete(subtask_types=[SUBTASK_KIND])

        assert [call["operation_id"] for call in blueprint["calls"]] == [
            START, START, RECORD, CLOSE]
        close = _calls(blueprint, CLOSE)[0]
        assert _one(close, "task_id")["binding_class"] == "runtime_bound"
        assert _one(close, "outcome")["binding_class"] == "runtime_bound"
        # A record attaches to whichever unit of work the caller names, so
        # events directly on the Task need no Subtask to exist.
        assert _one(_the_record(blueprint),
                    "task_id")["binding_class"] == "runtime_bound"

    def test_a_declared_name_that_is_not_an_identifier_keeps_its_spelling(self):
        """The literal is the tenant's own word, untouched. Only the parameter
        a generated file asks for is made spellable."""
        self._a_kind()
        self._event_type(measurements={
            "cache-read tokens": SEARCHES, "cache_read_tokens": SEARCHES})

        record = _the_record(self._complete())

        assert sorted(a["value"] for a in _named(record, "measurements")) == [
            "cache-read tokens", "cache_read_tokens"]
        parameters = [_one(record, f"measurements.{code}")["parameter_name"]
                      for code in ("cache-read tokens", "cache_read_tokens")]
        assert len(set(parameters)) == 2, parameters
        for parameter in parameters:
            assert parameter.isidentifier(), parameter

    def test_a_key_is_one_segment_of_a_name_whatever_it_contains(self):
        """A quantity named `tokens`, read by a path, and another named
        `tokens.source_path`, supplied by the caller. Left as they are the
        second quantity's value would take the name of the first one's path.
        A dot inside a key is encoded, so each token has a name of its own
        and every name splits on its dots into at most three segments."""
        dotted, already_encoded = "tokens.source_path", "tokens%2Esource_path"
        outside_ascii = "入力.トークン 100%"
        self._a_kind()
        self._event_type(measurements={
            "tokens": INPUT_TOKENS, dotted: SEARCHES,
            already_encoded: SEARCHES, outside_ascii: SEARCHES})

        record = _the_record(self._complete())

        # The keys travel as declared.
        assert sorted(a["value"] for a in _named(record, "measurements")) == [
            "tokens", already_encoded, dotted, outside_ascii]
        # A key outside ASCII is itself in its segment, but for the two
        # characters the encoding is about.
        assert _one(record, "measurements.入力%2Eトークン 100%25")[
            "binding_class"] == "runtime_bound"
        path = _one(record, "measurements.tokens.source_path")
        assert (path["binding_class"], path["value"]) == (
            "platform_known", ["usage", "input_tokens"])
        supplied = _one(record, "measurements.tokens%2Esource_path")
        assert supplied["binding_class"] == "runtime_bound"
        # The sign the encoding uses is encoded too, so a key that already
        # looks encoded is not taken for the key it looks like.
        assert _one(record, "measurements.tokens%252Esource_path")[
            "binding_class"] == "runtime_bound"
        assert (supplied["parameter_name"]
                != _one(record, "measurements.tokens%252Esource_path")[
                    "parameter_name"])
        names = [argument["name"] for argument in record["arguments"]]
        assert all(len(name.split(".")) <= 3 for name in names), names
        # No two tokens of one class share a name.
        classed = [(a["name"], a["binding_class"], str(a["value"]))
                   for a in record["arguments"] if a["name"] != "measurements"]
        assert len(classed) == len(set(classed))

    def test_the_tokens_under_a_key_follow_its_own_token_directly(self):
        """So a consumer pairs them by position and never needs the encoding:
        after a key's own token comes everything named under that key, under
        one prefix, and nothing of another key. The prefix decodes to the key
        — by the one decoder — which is what makes the pairing the right one
        and not merely a consistent one."""
        self._grouping_fields(("environment", "task"), ("region", "task"))
        self._a_kind(required_grouping_fields=["region", "environment"])
        self._event_type(measurements={
            "tokens": INPUT_TOKENS, "tokens.source_path": SEARCHES,
            "入力.トークン 100%": SEARCHES, "calls": {
                **SEARCHES, "source_kind": "derived"}})

        blueprint = self._complete()

        paired = 0
        for call in blueprint["calls"]:
            arguments = call["arguments"]
            keyed = {a["name"] for a in arguments
                     if a["name"] in ("grouping_fields", "measurements")}
            claimed = set()
            for position, argument in enumerate(arguments):
                if argument["name"] not in keyed:
                    continue
                field, key = argument["name"], argument["value"]
                under = []
                for following in arguments[position + 1:]:
                    if (following["name"] == field
                            or not following["name"].startswith(field + ".")):
                        break
                    under.append(following["name"])
                assert under, (field, key)
                prefixes = {".".join(name.split(".")[:2]) for name in under}
                assert len(prefixes) == 1, (key, under)
                (prefix,) = prefixes
                assert token_names.key_of(prefix.split(".")[1]) == key
                claimed.update(under)
                paired += 1
            # And no token of a keyed field is left belonging to no key.
            assert {a["name"] for a in arguments
                    if a["name"].split(".")[0] in keyed
                    and "." in a["name"]} == claimed
        assert paired == 6

    def test_a_declared_name_never_takes_a_parameter_the_call_already_has(
            self):
        """A quantity named for the response object, for the supplied cost,
        for another argument of the call, or for a word the language keeps:
        each gets a parameter of its own that is none of those."""
        import keyword
        awkward = ["response", "reported_cost", "customer_id", "class"]
        self._a_kind()
        self._event_type(
            costing_method="reported",
            measurements={**{code: SEARCHES for code in awkward},
                          "input_tokens": INPUT_TOKENS},
            mapping={"source_kind": "caller_supplied",
                     "amount_representation": "micros", "currency": "usd"})

        record = _the_record(self._complete())

        asked_for = [argument["parameter_name"]
                     for argument in record["arguments"]
                     if argument["binding_class"] == "runtime_bound"]
        declared = [_one(record, f"measurements.{code}")["parameter_name"]
                    for code in awkward]
        # One parameter each, except the response object, which every quantity
        # read off the response shares.
        assert sorted(asked_for) == sorted(set(asked_for)), asked_for
        assert not set(declared) & {"response", "reported_cost",
                                    "customer_id", "idempotency_key",
                                    "task_id"}
        for parameter in declared:
            assert parameter.isidentifier(), parameter
            assert not keyword.iskeyword(parameter), parameter
        assert sorted(a["value"] for a in
                      _named(record, "measurements")) == sorted(
            [*awkward, "input_tokens"])


# ---------------------------------------------------------------------------
# No secret, anywhere
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestNoSecretReachesABlueprintOrASnapshot(_Routes):
    def _secrets(self):
        """Known values in every secret-shaped column the tenant has. Written
        to the rows: no route sets any of them to a value a test can know."""
        secrets = {"widget_secret": "whsec-KNOWN-widget-secret",
                   "stripe_connected_account_id": "acct_KNOWNconnected",
                   "stripe_customer_id": "cus_KNOWNcustomer"}
        Tenant.objects.filter(pk=self.tenant.pk).update(**secrets)
        key = TenantApiKey.objects.filter(tenant=self.tenant).first()
        return [*secrets.values(), self.raw_key, key.key_hash]

    def test_no_secret_value_is_in_any_body_or_any_stored_row(self):
        self._complete_configuration()
        self._event_type("draft.only", publish=False)
        secrets = self._secrets()

        published = self._send("post", BLUEPRINTS, {
            "target": "python_sdk", "task_type": KIND,
            "event_types": [EVENT, "draft.only"],
            "subtask_types": [SUBTASK_KIND]})
        preview = self._send("post", BLUEPRINTS, {
            "target": "shell_http", "task_type": KIND,
            "event_types": [EVENT, "draft.only"], "draft_preview": True})
        fingerprint = published.json()["configuration_fingerprint"]
        read_back = self._send("get", f"{BLUEPRINTS}/{fingerprint}")

        bodies = [response.content.decode()
                  for response in (published, preview, read_back)]
        rows = [json.dumps(row, default=str)
                for row in BlueprintSnapshot._base_manager.values()]
        assert len(rows) == 1 and all(r.status_code == 200 for r in (
            published, preview, read_back))
        for secret in secrets:
            for text in (*bodies, *rows):
                assert secret not in text, secret

    def test_the_search_can_find_a_secret_that_is_there(self):
        """The control: the same search, over the tenant's own row, finds
        every value it is looking for. Without it the check above would pass
        as happily over values that were never set."""
        secrets = self._secrets()
        held = json.dumps(
            [*Tenant._base_manager.filter(pk=self.tenant.pk).values(),
             *TenantApiKey._base_manager.filter(tenant=self.tenant).values()],
            default=str)

        assert all(secret in held or secret == self.raw_key
                   for secret in secrets)
        assert sum(secret in held for secret in secrets) == 4


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestReadinessMeansWhatItIsPinnedToMean(_Routes):
    def test_complete_is_everything_resolving_from_published_configuration(
            self):
        self._complete_configuration()

        blueprint = self._complete(subtask_types=[SUBTASK_KIND])

        assert blueprint["readiness"] == "complete"
        assert {call["readiness"] for call in blueprint["calls"]} == {
            "complete"}
        assert blueprint["diagnostics"] == []
        assert A_FINGERPRINT.match(blueprint["configuration_fingerprint"])

    def test_a_brand_new_tenant_gets_a_scaffold_and_no_invented_vocabulary(
            self):
        """Nothing selected and nothing declared: the lifecycle's shape, with
        the two structural values present as unconfigured literals and no
        name anywhere that the tenant did not declare."""
        blueprint = self._resolve()

        assert blueprint["readiness"] == "scaffold"
        assert [call["operation_id"] for call in blueprint["calls"]] == [
            START, RECORD, CLOSE]
        kind = _one(_the_start(blueprint), "task_type")
        event_type = _one(_calls(blueprint, RECORD)[0], "event_type")
        for unconfigured in (kind, event_type):
            assert unconfigured["binding_class"] == "platform_known"
            assert unconfigured["configured"] is False
            assert unconfigured["value"] is None
            assert unconfigured["provenance"] is None
        assert _codes(blueprint) == ["event_type_not_selected",
                                     "task_type_not_selected"]
        assert _codes(blueprint, "blocking") == _codes(blueprint)
        literals = [a["value"] for call in blueprint["calls"]
                    for a in call["arguments"] if a["value"] is not None]
        assert literals == []

    def test_no_kind_selected_is_a_scaffold_though_the_event_type_is_ready(
            self):
        self._complete_configuration()

        blueprint = self._resolve(event_types=[EVENT])

        assert _the_start(blueprint)["readiness"] == "scaffold"
        assert _the_record(blueprint)["readiness"] == "complete"
        assert blueprint["readiness"] == "scaffold"
        assert _codes(blueprint) == ["task_type_not_selected"]

    def test_a_selected_kind_nobody_declared_is_a_scaffold(self):
        self._complete_configuration()

        blueprint = self._complete(task_type="not_a_kind")

        assert _the_start(blueprint)["readiness"] == "scaffold"
        missing = _diagnostic(blueprint, "task_type_not_declared")
        assert (missing["object_kind"], missing["key"]) == (
            "task_type", "not_a_kind")
        kind = _one(_the_start(blueprint), "task_type")
        assert (kind["configured"], kind["value"]) == (False, None)
        assert blueprint["readiness"] == "scaffold"

    def test_a_selected_event_type_nobody_declared_is_a_scaffold(self):
        self._complete_configuration()

        blueprint = self._complete(event_types=["not.declared"])

        record = _calls(blueprint, RECORD)[0]
        assert record["readiness"] == "scaffold"
        assert _one(record, "event_type")["configured"] is False
        missing = _diagnostic(blueprint, "event_type_not_declared")
        assert (missing["object_kind"], missing["key"]) == (
            "event_type", "not.declared")
        assert blueprint["readiness"] == "scaffold"

    def test_a_selected_subtask_kind_must_be_declared_at_the_subtask_altitude(
            self):
        """One word may name a kind at either altitude, and they are different
        declarations: a Task kind's key selected as a Subtask is not
        declared."""
        self._complete_configuration()

        blueprint = self._complete(subtask_types=[KIND])

        missing = _diagnostic(blueprint, "task_type_not_declared")
        assert (missing["object_kind"], missing["key"]) == (
            "subtask_type", KIND)
        assert blueprint["readiness"] == "scaffold"

    def test_the_integration_is_as_ready_as_its_least_ready_call(self):
        """One blocked Event Type neither hides the working calls nor lets the
        whole claim to be complete."""
        self._complete_configuration()
        self._event_type("draft.only", publish=False)

        blueprint = self._complete(event_types=[EVENT, "draft.only"])

        assert _the_record(blueprint)["readiness"] == "complete"
        assert _the_start(blueprint)["readiness"] == "complete"
        assert _the_record(blueprint, "draft.only")["readiness"] == "blocked"
        assert blueprint["readiness"] == "blocked"

    def test_a_scaffold_call_outranks_a_blocked_one(self):
        self._complete_configuration()
        self._event_type("draft.only", publish=False)

        blueprint = self._resolve(event_types=["draft.only"])

        assert sorted(call["readiness"] for call in blueprint["calls"]) == [
            "blocked", "complete", "scaffold"]
        assert blueprint["readiness"] == "scaffold"

    def test_a_retired_kind_blocks_the_start(self):
        self._complete_configuration()
        self._kinds({"key": KIND, "task_cogs_ceiling_micros": 5_000_000,
                     "required_grouping_fields": ["environment"],
                     "retired": True})

        blueprint = self._complete()

        assert _the_start(blueprint)["readiness"] == "blocked"
        retired = _diagnostic(blueprint, "task_type_retired")
        assert (retired["severity"], retired["object_kind"],
                retired["key"], retired["field"]) == (
            "blocking", "task_type", KIND, "retired")
        # The console has a screen for a kind of work, so the diagnostic names
        # the object and carries no request.
        assert retired["remediation_request"] is None

    def test_a_required_grouping_field_at_the_wrong_scope_blocks_the_start(
            self):
        """A start accepts a value only at the field's own scope and refuses a
        kind's required field that is missing, so a Task kind requiring an
        event-scoped field can never start."""
        self._grouping_fields(("region", "event"))
        self._a_kind(required_grouping_fields=["region"])
        self._event_type()

        blueprint = self._complete()

        assert _the_start(blueprint)["readiness"] == "blocked"
        wrong = _diagnostic(blueprint, "required_grouping_field_wrong_scope")
        assert (wrong["object_kind"], wrong["key"], wrong["field"]) == (
            "task_type", KIND, "required_grouping_fields")
        assert _named(_the_start(blueprint), "grouping_fields.region") == []

    def test_a_required_grouping_field_that_is_retired_blocks_the_start(self):
        """A retired field accepts no value it has not already seen, so a kind
        that requires one starts only by accident. The fix is the kind's:
        nothing un-retires a field."""
        self._grouping_fields(("environment", "task"))
        self._a_kind(required_grouping_fields=["environment"])
        self._event_type()
        self._retire("environment")

        blueprint = self._complete()

        retired = _diagnostic(blueprint, "required_grouping_field_retired")
        assert (retired["severity"], retired["object_kind"], retired["key"],
                retired["field"]) == ("blocking", "task_type", KIND,
                                      "required_grouping_fields")
        assert _the_start(blueprint)["readiness"] == "blocked"
        assert _named(_the_start(blueprint),
                      "grouping_fields.environment") == []

    def test_a_required_grouping_field_nobody_declared_blocks_the_start(self):
        """No route can produce this — the registry refuses a kind requiring
        an undeclared field — but the column is a list of keys, so the tables
        admit it."""
        self._a_kind()
        self._event_type()
        self._require_without_declaring(KIND, "ghost")

        blueprint = self._complete()

        missing = _diagnostic(blueprint,
                              "required_grouping_field_not_declared")
        assert (missing["object_kind"], missing["key"]) == (
            "grouping_field", "ghost")
        assert _the_start(blueprint)["readiness"] == "blocked"

    def test_an_advisory_leaves_the_integration_complete(self):
        """A path that looks inconsistent with its declared shape is advice.
        UBB says so and changes nothing — including the path it emits."""
        self._a_kind()
        self._event_type(shape=A_JSON_SHAPE, measurements={"input_tokens": {
            **INPUT_TOKENS,
            "source_path": ["usage_metadata", "prompt_token_count"]}})

        blueprint = self._complete(target="shell_http")

        assert blueprint["readiness"] == "complete"
        assert _the_record(blueprint)["readiness"] == "complete"
        advice = _diagnostic(blueprint, "source_path_convention_mismatch")
        assert (advice["severity"], advice["object_kind"], advice["key"],
                advice["field"]) == ("advisory", "measurement",
                                     f"{EVENT}:input_tokens", "source_path")
        assert _one(_the_record(blueprint),
                    "measurements.input_tokens.source_path")["value"] == [
            "usage_metadata", "prompt_token_count"]

    def test_a_missing_mandatory_declaration_blocks_where_an_advisory_does_not(
            self):
        """The same Event Type, with the one thing a `reported` cost cannot do
        without taken away. Declared and never published under draft preview,
        which is the only place an unmapped `reported` declaration is
        reachable: publication refuses one."""
        self._a_kind()
        self._event_type(costing_method="reported", measurements={},
                         publish=False)

        blueprint = self._complete(draft_preview=True)

        assert blueprint["readiness"] == "blocked"
        missing = _diagnostic(blueprint, "reported_cost_mapping_missing")
        assert (missing["severity"], missing["object_kind"],
                missing["key"]) == ("blocking", "reported_cost_mapping",
                                    EVENT)
        assert _named(_the_record(blueprint), "provider_cost_micros") == []


# ---------------------------------------------------------------------------
# The response shape, against the target
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAShapeTheTargetCannotReadIsBlocked(_Routes):
    def _shaped(self, shape, label=""):
        self._a_kind()
        self._event_type(shape=shape, label=label)

    @pytest.mark.parametrize("shape, target, readiness", [
        (A_PYTHON_SHAPE, "python_sdk", "complete"),
        (A_PYTHON_SHAPE, "shell_http", "blocked"),
        ("google.genai.python.v1", "python_sdk", "complete"),
        ("google.genai.python.v1", "shell_http", "blocked"),
        (A_JSON_SHAPE, "python_sdk", "complete"),
        (A_JSON_SHAPE, "shell_http", "complete"),
    ])
    def test_the_built_in_matrix(self, shape, target, readiness):
        self._shaped(shape)

        blueprint = self._complete(target=target)

        assert _the_record(blueprint)["readiness"] == readiness
        assert blueprint["readiness"] == readiness
        expected = ([] if readiness == "complete"
                    else ["response_shape_not_readable_by_target"])
        assert _codes(blueprint, "blocking") == expected

    @pytest.mark.parametrize("target", ["python_sdk", "shell_http"])
    def test_a_custom_shape_is_blocked_on_every_target(self, target):
        """No renderer defines how to traverse a tenant's own wrapper yet, and
        an advisory alone never makes one complete."""
        self._shaped("custom", label="acme-wrapper-v2")

        blueprint = self._complete(target=target)

        assert blueprint["readiness"] == "blocked"
        unreadable = _diagnostic(blueprint,
                                 "response_shape_not_readable_by_target")
        assert (unreadable["severity"], unreadable["object_kind"],
                unreadable["key"], unreadable["field"]) == (
            "blocking", "event_type", EVENT, "source_shape_id")

    def test_a_shape_matters_only_where_something_reads_the_response(self):
        """Every quantity supplied by the caller: nothing is read off the
        supplier's response, so what shape it has decides nothing."""
        self._a_kind()
        self._event_type(shape=A_PYTHON_SHAPE,
                         measurements={"searches": SEARCHES})

        blueprint = self._complete(target="shell_http")

        assert blueprint["readiness"] == "complete"
        assert blueprint["diagnostics"] == []


# ---------------------------------------------------------------------------
# What UBB cannot carry yet is blocked, and nothing is made up
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestNoValueIsInvented(_Routes):
    def test_a_constant_with_its_value_is_blocked_only_until_it_can_render(
            self):
        """The declaration is complete — a constant is declared with its
        value (#571) — and this Code Builder version cannot yet generate code
        that uses it. So the call is blocked by the code that says exactly
        that and by nothing else of the quantity's own, the value reaches
        neither the Blueprint nor the snapshot it is stored as (#584 carries
        it), and no request is offered: there is nothing in the declaration
        to change."""
        self._a_kind()
        self._event_type(measurements={"calls": {
            **SEARCHES, "value_type": "decimal", "unit": "call",
            "source_kind": "constant", "constant_value": "271828.5"}})

        blueprint = self._complete()
        record = _the_record(blueprint)

        constant = _one(record, "measurements.calls")
        assert constant["binding_class"] == "platform_known"
        assert constant["configured"] is False
        assert constant["value"] is None
        assert record["readiness"] == "blocked"
        about_the_constant = [d for d in blueprint["diagnostics"]
                              if d["key"] == f"{EVENT}:calls"]
        assert about_the_constant == [{
            "severity": "blocking",
            "code": "constant_measurement_not_renderable",
            "object_kind": "measurement", "key": f"{EVENT}:calls",
            "field": "source_kind", "remediation_request": None}]
        assert "271828" not in json.dumps(blueprint)
        (stored,) = BlueprintSnapshot.objects.filter(tenant=self.tenant)
        assert "271828" not in json.dumps(stored.content)

    def test_a_derived_quantity_is_always_blocked(self):
        self._a_kind()
        self._event_type(measurements={"total": {
            **SEARCHES, "source_kind": "derived"}})

        blueprint = self._complete()
        record = _the_record(blueprint)

        assert record["readiness"] == "blocked"
        assert [a["value"] for a in _named(record, "measurements")] == [
            "total"]
        assert _named(record, "measurements.total") == []
        blocker = _diagnostic(blueprint, "derived_measurement_unsupported")
        assert (blocker["severity"], blocker["key"]) == (
            "blocking", f"{EVENT}:total")

    def test_a_cost_read_from_the_response_is_blocked_and_fills_no_field(self):
        """There is no truthful request field for a cost UBB's caller read off
        its supplier's response, so the call carries none — least of all the
        one whose contract means the caller supplied it."""
        self._a_kind()
        self._event_type(
            costing_method="reported", measurements={},
            mapping={"source_kind": "provider_response",
                     "amount_representation": "major_units_decimal",
                     "source_path": ["usage", "total_cost"],
                     "currency": "usd"})

        blueprint = self._complete()
        record = _the_record(blueprint)

        assert record["readiness"] == "blocked"
        assert not [argument for argument in record["arguments"]
                    if argument["name"].startswith("provider_cost_micros")
                    or argument["name"] == "currency"]
        blocker = _diagnostic(
            blueprint, "reported_cost_provider_response_unsupported")
        assert (blocker["severity"], blocker["object_kind"], blocker["key"],
                blocker["field"]) == (
            "blocking", "reported_cost_mapping", EVENT, "source_kind")


# ---------------------------------------------------------------------------
# Published by default
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAnEventTypeResolvesFromItsLastPublication(_Routes):
    def test_a_revised_event_type_resolves_from_what_it_last_published(self):
        published = self._complete_configuration()
        before = self._complete()
        self._call("put", f"/api/v1/event-types/{EVENT}/measurements/"
                          "input_tokens",
                   {**INPUT_TOKENS, "source_path": ["usage", "prompt_tokens"]})
        live = self._call("get", f"/api/v1/event-types/{EVENT}")
        assert live["declaration_status"] == "draft"

        after = self._complete()
        record = _the_record(after)

        # The path is the published one, not the draft's.
        assert _one(record, "measurements.input_tokens.source_path")[
            "value"] == ["usage", "input_tokens"]
        assert _one(record, "event_type")["provenance"][
            "published_revision"] == published["published_revision"]
        assert after["readiness"] == "complete"
        # And the developer is told a draft is waiting, without it lowering
        # anything.
        advice = _diagnostic(after, "event_type_revised_since_publication")
        assert (advice["severity"], advice["object_kind"], advice["key"],
                advice["field"]) == ("advisory", "event_type", EVENT,
                                     "declaration_status")
        assert before["diagnostics"] == []

    def test_an_event_type_never_published_is_blocked(self):
        self._a_kind()
        self._event_type(publish=False)

        blueprint = self._complete()
        record = _the_record(blueprint)

        assert record["readiness"] == "blocked"
        unpublished = _diagnostic(blueprint, "event_type_not_published")
        assert (unpublished["severity"], unpublished["object_kind"],
                unpublished["key"]) == ("blocking", "event_type", EVENT)
        assert unpublished["remediation_request"]["operation_id"] == (
            "api_v1_event_type_endpoints_publish_event_type")
        # The key is the tenant's own and is known; nothing beneath it is.
        assert _one(record, "event_type")["value"] == EVENT
        assert _named(record, "measurements") == []

    def test_an_event_type_whose_publication_kept_no_copy_is_blocked(self):
        """Published before a publication kept its content, and revised since:
        the row counts a publication and holds none to resolve from. What
        decides is whether a publication can be READ, never the count.
        Written to the row — no route produces it on this commit."""
        from apps.platform.event_types.models import EventType
        self._a_kind()
        self._event_type()
        EventType.objects.filter(tenant=self.tenant, key=EVENT).update(
            published_declaration=None, declaration_status="draft")
        assert self._call(
            "get", f"/api/v1/event-types/{EVENT}")["published_revision"] == 1

        blueprint = self._complete()

        assert _the_record(blueprint)["readiness"] == "blocked"
        assert _codes(blueprint) == ["event_type_not_published"]


# ---------------------------------------------------------------------------
# Every call names a real operation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestEveryCallNamesARealOperation(_Routes):
    def test_every_operation_id_is_in_the_committed_contract(self):
        """The set is derived from the document, so an operation renamed or
        removed there turns this red rather than passing against a list."""
        operations = _operations()
        assert len(operations) >= 100, "the contract was not read"
        self._complete_configuration()
        self._event_type("draft.only", publish=False)

        blueprints = [
            self._resolve(),
            self._complete(subtask_types=[SUBTASK_KIND]),
            self._complete(target="shell_http",
                           event_types=[EVENT, "draft.only"]),
        ]

        named = [call["operation_id"] for blueprint in blueprints
                 for call in blueprint["calls"]]
        assert len(named) >= 10
        for operation_id in named:
            assert operation_id.startswith("api_v1_"), operation_id
            assert operation_id in operations, operation_id

    def test_every_bare_argument_is_a_field_its_operation_publishes(self):
        """A key the route does not publish is dropped by it in silence and
        still answered 200, so a call filling one would look as if it worked.
        The credential is the one token that is not a body field."""
        operations = _operations()
        self._complete_configuration()
        self._event_type(
            "billed.by.supplier", costing_method="reported", measurements={},
            mapping={"source_kind": "caller_supplied",
                     "amount_representation": "micros", "currency": "usd"})

        blueprint = self._complete(
            event_types=[EVENT, "billed.by.supplier"],
            subtask_types=[SUBTASK_KIND])
        assert _named(_the_record(blueprint, "billed.by.supplier"),
                      "provider_cost_micros")

        checked = 0
        for call in blueprint["calls"]:
            _, path, operation = operations[call["operation_id"]]
            published = _request_properties(operation) | set(
                re.findall(r"{(\w+)}", path))
            for argument in call["arguments"]:
                if argument["name"] == "api_key":
                    continue
                checked += 1
                assert argument["name"].split(".")[0] in published, (
                    call["operation_id"], argument["name"])
        assert checked >= 20


class TestTheBlueprintBindsToNoOtherRegistrysSchema:
    def test_its_schemas_refer_only_to_each_other(self):
        """Read off the committed contract rather than off the Python: every
        schema either route reaches, followed to the end, is the Blueprint's
        own or the one error dialect. So renaming a registry's schema — the
        Grouping Field registry's are due one — moves nothing here."""
        reached, queue = set(), []
        for name in ("api_v1_code_builder_endpoints_resolve_blueprint",
                     "api_v1_code_builder_endpoints_get_blueprint"):
            queue.append(_operations()[name][2])
        while queue:
            node = queue.pop()
            if isinstance(node, dict):
                ref = node.get("$ref")
                if ref:
                    name = ref.rsplit("/", 1)[1]
                    if name not in reached:
                        reached.add(name)
                        queue.append(_schema(name))
                queue.extend(node.values())
            elif isinstance(node, list):
                queue.extend(node)

        assert reached == {
            "IntegrationBlueprintSelectionIn", "ResolvedIntegrationBlueprint",
            "IntegrationBlueprintCall", "IntegrationBlueprintArgument",
            "IntegrationBlueprintProvenance", "IntegrationBlueprintDiagnostic",
            "IntegrationBlueprintRemediationRequest", "ProblemOut"}


# ---------------------------------------------------------------------------
# The stored snapshot
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestResolvingStoresTheSnapshotAndNothingElse(_Routes):
    def test_the_same_content_is_the_same_fingerprint_and_one_row(self):
        self._complete_configuration()

        first = self._complete()
        second = self._complete()

        assert second == first
        assert A_FINGERPRINT.match(first["configuration_fingerprint"])
        assert BlueprintSnapshot.objects.filter(
            tenant=self.tenant,
            configuration_fingerprint=first["configuration_fingerprint"],
        ).count() == 1
        assert BlueprintSnapshot.objects.count() == 1

    def test_no_table_but_the_snapshots_changes(self):
        """Every row of every table, before and after. The list of tables is
        the app registry's, so it is not a list of the ones this ticket
        thought of."""
        self._complete_configuration()
        self._event_type("draft.only", publish=False)
        before = _every_row()
        # The comparison is over real configuration, not empty tables.
        for label in ("event_types.EventType", "event_types.Measurement",
                      "event_types.Provider", "work.TaskType",
                      "grouping_fields.GroupingField", "tenants.Tenant",
                      "tenants.TenantApiKey", "audit.AuditRecord"):
            assert before[label], label
        assert CONFIG_MODEL_LABELS <= set(before)

        self._complete(event_types=[EVENT, "draft.only"],
                       subtask_types=[SUBTASK_KIND])
        self._complete(target="shell_http")
        self._resolve()

        after = _every_row()
        assert _tables_that_differ(before, after) == [
            "code_builder.BlueprintSnapshot"]
        assert len(after["code_builder.BlueprintSnapshot"]) == 3

    def test_another_tenant_with_the_same_configuration_has_the_same_fingerprint_and_its_own_row(
            self):
        self._complete_configuration()
        mine = self._complete()["configuration_fingerprint"]
        other = type(self)()
        other.setup_method()
        other._complete_configuration()
        # Published a moment later, so the two publications are dated apart;
        # the same instant on both is what makes the content the same.
        from apps.platform.event_types.models import EventType
        mine_row = EventType.objects.get(tenant=self.tenant, key=EVENT)
        theirs_row = EventType.objects.get(tenant=other.tenant, key=EVENT)
        EventType.objects.filter(pk=theirs_row.pk).update(
            published_at=mine_row.published_at)

        theirs = other._complete()["configuration_fingerprint"]

        assert theirs == mine
        assert BlueprintSnapshot.objects.filter(
            configuration_fingerprint=mine).count() == 2

    def test_a_changed_kind_of_work_is_a_new_fingerprint(self):
        """A kind carries no date, so the fingerprint is what says a held file
        has gone stale — including for a fact no call spells, like how long
        the kind may go quiet."""
        self._complete_configuration()
        before = self._complete()

        self._kinds({"key": KIND, "task_cogs_ceiling_micros": 5_000_000,
                     "silence_window_seconds": 1200,
                     "required_grouping_fields": ["environment"]})
        after = self._complete()

        assert (after["configuration_fingerprint"]
                != before["configuration_fingerprint"])
        assert after["calls"] == before["calls"]
        assert BlueprintSnapshot.objects.count() == 2

    def test_a_republication_is_a_new_fingerprint_though_the_declaration_is_the_same(
            self):
        """Revise, revert, publish: the declaration is what it was and the
        revision has moved. The stored content names the publication it was
        resolved from — a generated file's header states it — so the
        fingerprint moves with the revision rather than hiding it."""
        self._complete_configuration()
        before = self._complete()
        route = f"/api/v1/event-types/{EVENT}/measurements/input_tokens"

        self._call("put", route, {**INPUT_TOKENS, "unit": "character"})
        self._call("put", route, INPUT_TOKENS)
        republished = self._publish()
        after = self._complete()

        assert republished["published_revision"] == 2
        assert _one(_the_record(after), "event_type")["provenance"][
            "published_revision"] == 2
        assert (after["configuration_fingerprint"]
                != before["configuration_fingerprint"])

    def test_the_snapshot_holds_what_a_sandbox_would_need(self):
        """The kinds with what they may spend and how they are sold, the
        Event Type as published, the required Grouping Fields, the rules that
        cost and price the selected quantities, the markup, and the tenant
        fields a sandbox is provisioned from. The agreed price of a kind sold
        whole is not here; nothing declares one yet."""
        from apps.metering.pricing.models import CostBook, Rate
        from apps.metering.pricing.models import TenantDefaultMarkup
        from apps.platform.event_types.models import Measurement
        self._complete_configuration()
        # Rules have no route in this module's reach that a metering-only
        # tenant may call, so the cost rule and the markup are written to
        # their rows.
        book = CostBook.objects.create(
            tenant=self.tenant, key="openai", provider_key="openai",
            currency="usd", is_default=True)
        Rate.objects.create(
            tenant=self.tenant, cost_book=book, provider="openai",
            measurement=Measurement.objects.get(
                event_type__tenant=self.tenant, code="input_tokens"),
            rate_per_unit_micros=3_000_000, unit_quantity=1_000_000)
        TenantDefaultMarkup.objects.create(
            tenant=self.tenant, markup_micro_percent=25_000_000)

        self._complete(subtask_types=[SUBTASK_KIND])

        configuration = BlueprintSnapshot.objects.get().content["identity"][
            "configuration"]
        assert configuration["task_type"]["task_cogs_ceiling_micros"] == (
            5_000_000)
        assert configuration["task_type"]["pricing_mode"] == "event_priced"
        assert [kind["key"] for kind in
                configuration["subtask_types"]] == [SUBTASK_KIND]
        assert configuration["subtask_types"][0]["uncapped"] is True
        assert sorted(field["key"] for field in
                      configuration["grouping_fields"]) == [
            "environment", "phase"]
        event_type = configuration["event_types"][0]
        assert event_type["key"] == EVENT
        assert event_type["provider_key"] == "openai"
        assert [m["code"] for m in event_type["measurements"]] == [
            "input_tokens", "searches"]
        assert [(rule["measurement_code"], rule["rate_per_unit_micros"])
                for rule in configuration["cost_rates"]] == [
            ("input_tokens", 3_000_000)]
        assert configuration["cost_rates"][0]["book"]["key"] == "openai"
        assert configuration["pricing_rules"] == []
        assert configuration["default_markup_micro_percent"] == 25_000_000
        assert configuration["tenant"] == {
            "products": ["metering"], "billing_mode": self.tenant.billing_mode,
            "default_currency": "usd"}


@pytest.mark.django_db
class TestTheFingerprintIsOfTheResolvedContractAndNothingElse(_Routes):
    """The hash boundary (owner ruling of 2026-10-02): the fingerprint is a
    stable identity of the normative resolved contract, and not a hash of
    every byte that happened to be serialised.

    Read off the stored row and off repeated resolutions. What IS meant to
    move it — a republication, a changed kind — is held by the class above;
    this is everything that must NOT."""

    def _a_blocked_configuration(self):
        """A Blueprint whose diagnostics offer requests, so the half that is
        not hashed has something in it."""
        self._complete_configuration()
        self._event_type("draft.only", publish=False)
        self._event_type("unshaped", shape="")
        return {"event_types": [EVENT, "draft.only", "unshaped", "missing"],
                "subtask_types": [SUBTASK_KIND]}

    def _identity(self):
        return BlueprintSnapshot.objects.get().content["identity"]

    def test_it_is_the_hash_of_the_identity_half_of_the_stored_row(self):
        """Checked by somebody holding only the row: canonical JSON of the
        identity, hashed — and not of the row's whole content."""
        import hashlib
        fingerprint = self._complete(**self._a_blocked_configuration())[
            "configuration_fingerprint"]

        content = BlueprintSnapshot.objects.get().content

        def hashed(value):
            return "sha256:" + hashlib.sha256(json.dumps(
                value, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False).encode("utf-8")).hexdigest()

        assert set(content) == {"identity", "presentation"}
        assert fingerprint == hashed(content["identity"])
        assert fingerprint != hashed(content)
        assert set(content["identity"]) == {"selection", "blueprint",
                                            "configuration"}

    def test_the_request_a_diagnostic_offers_is_kept_and_is_not_hashed(self):
        """It is how the API spells a fix, built from the API's own routes and
        request shapes. It is returned as it was answered and is no part of
        what the integration means."""
        resolved = self._complete(**self._a_blocked_configuration())
        offered = [d["remediation_request"] for d in resolved["diagnostics"]]
        assert len([request for request in offered if request]) >= 3

        content = BlueprintSnapshot.objects.get().content

        assert content["presentation"] == {"remediation_requests": offered}
        identity = json.dumps(content["identity"])
        assert "remediation_request" not in identity
        for request in filter(None, offered):
            assert request["route"] not in identity, request
            assert request["operation_id"] not in identity, request
        # What a diagnostic SAYS is identity: its code and what it is about.
        assert [(d["code"], d["object_kind"], d["key"], d["field"])
                for d in content["identity"]["blueprint"]["diagnostics"]] == [
            (d["code"], d["object_kind"], d["key"], d["field"])
            for d in resolved["diagnostics"]]

    def test_a_request_spelled_another_way_is_the_same_fingerprint(
            self, monkeypatch):
        """⚠ THE ONE TEST HERE THAT REACHES PAST THE API, and it has to: what
        it varies is how the API itself spells a fix, which no request can
        change. The spelling is replaced, the same selection is resolved
        again, and the fingerprint and the stored row are what they were."""
        from api.v1 import integration_blueprint
        selection = self._a_blocked_configuration()
        before = self._complete(**selection)

        monkeypatch.setattr(
            integration_blueprint, "_remediation_request",
            lambda remediation, **keys: {
                "method": "POST", "route": "/somewhere/else",
                "operation_id": "another_operation", "body": {"new": None}})
        after = self._complete(**selection)

        # The control: the spelling really did change in what was answered.
        assert "/somewhere/else" in json.dumps(after["diagnostics"])
        assert "/somewhere/else" not in json.dumps(before["diagnostics"])
        assert (after["configuration_fingerprint"]
                == before["configuration_fingerprint"])
        assert BlueprintSnapshot.objects.count() == 1
        # First wins: what is read back is the Blueprint as first answered.
        assert self._call(
            "get", f"{BLUEPRINTS}/{before['configuration_fingerprint']}"
        ) == before

    def test_the_order_a_kind_lists_its_requirements_in_is_not_part_of_it(
            self):
        self._grouping_fields(("environment", "task"), ("region", "task"))
        self._a_kind(required_grouping_fields=["region", "environment"])
        self._event_type()
        one = self._complete()

        self._a_kind(required_grouping_fields=["environment", "region"])
        other = self._complete()

        assert other == one
        assert BlueprintSnapshot.objects.count() == 1
        assert [a["value"] for a in
                _named(_the_start(one), "grouping_fields")] == [
            "environment", "region"]

    def test_the_order_a_tenant_lists_its_products_in_is_not_part_of_it(self):
        """Written to the row, both times: the list is validated as a set and
        stored as written, and no route in this module's reach reorders it."""
        self._complete_configuration()
        Tenant.objects.filter(pk=self.tenant.pk).update(
            products=["referrals", "metering"])
        one = self._complete()["configuration_fingerprint"]

        Tenant.objects.filter(pk=self.tenant.pk).update(
            products=["metering", "referrals"])
        other = self._complete()["configuration_fingerprint"]

        assert other == one
        assert self._identity()["configuration"]["tenant"]["products"] == [
            "metering", "referrals"]

    def test_the_rules_are_in_the_order_of_what_they_say(self):
        """A set of rules has no order of its own. Written to their rows in
        the reverse of the order they sort in, they are hashed in the order
        of their content — so two tenants holding the same rules, entered in
        a different order, hold the same fingerprint."""
        from apps.metering.pricing.models import CostBook, Rate
        from apps.platform.event_types.models import Measurement
        self._complete_configuration()
        quantity = Measurement.objects.get(
            event_type__tenant=self.tenant, code="input_tokens")
        for key, amount in (("zeta", 9), ("alpha", 7), ("mid", 8)):
            book = CostBook.objects.create(
                tenant=self.tenant, key=key, provider_key="openai",
                currency="usd")
            for rate in (amount * 2, amount):
                Rate.objects.create(
                    tenant=self.tenant, cost_book=book, provider="openai",
                    measurement=quantity, task_type=f"kind_{rate}",
                    rate_per_unit_micros=rate)

        self._complete()

        rules = self._identity()["configuration"]["cost_rates"]

        def canonical(rule):
            return json.dumps(rule, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False)

        assert len(rules) == 6
        assert rules == sorted(rules, key=canonical)
        assert [rule["book"]["key"] for rule in rules] == [
            "alpha", "alpha", "mid", "mid", "zeta", "zeta"]

    def test_nothing_volatile_is_in_it(self):
        """No row's id, no row's timestamp, no moment of resolution, and no
        tenant. The only instants are the ones that ARE configuration: when
        an Event Type was published, and when a rule opens and closes."""
        from apps.metering.pricing.models import CostBook, Rate
        from apps.platform.event_types.models import Measurement
        selection = self._a_blocked_configuration()
        book = CostBook.objects.create(
            tenant=self.tenant, key="openai", provider_key="openai",
            currency="usd", is_default=True)
        Rate.objects.create(
            tenant=self.tenant, cost_book=book, provider="openai",
            measurement=Measurement.objects.get(
                event_type__tenant=self.tenant, event_type__key=EVENT,
                code="input_tokens"),
            rate_per_unit_micros=3_000_000)
        self._complete(**selection)
        identity = self._identity()
        text = json.dumps(identity)

        # Every UUID any row is keyed by. (Django's own tables are keyed by
        # small integers, which a search of the text would find in any
        # amount.)
        every_row_id = {
            str(key)
            for model in django_apps.get_models()
            if model._meta.managed and not model._meta.proxy
            for key in model._base_manager.values_list("pk", flat=True)
            if isinstance(key, uuid.UUID)}
        assert len(every_row_id) >= 15
        assert not re.search(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            text)
        assert [row_id for row_id in every_row_id if row_id in text] == []

        an_instant = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
        instants, keys = [], set()

        def walk(node, under=None):
            if isinstance(node, dict):
                for key, value in node.items():
                    keys.add(key)
                    walk(value, key)
            elif isinstance(node, list):
                for value in node:
                    walk(value, under)
            elif isinstance(node, str) and an_instant.match(node):
                instants.append(under)

        walk(identity)
        assert not keys & {"id", "created_at", "updated_at", "tenant_id",
                           "resolved_at", "lineage_id"}
        assert set(instants) == {"published_at", "valid_from"}
        assert len(instants) >= 3

    def test_resolving_again_later_is_the_same_fingerprint(self):
        """The moment of resolution is not in it: nothing changed, time
        passed, and the answer is the same answer."""
        from datetime import timedelta
        from unittest import mock
        self._complete_configuration()
        now = timezone.now()
        one = self._complete()

        with mock.patch("django.utils.timezone.now",
                        return_value=now + timedelta(days=30)):
            other = self._complete()

        assert other == one
        assert BlueprintSnapshot.objects.count() == 1


@pytest.mark.django_db
class TestABlueprintIsReadBackByItsFingerprint(_Routes):
    def test_the_stored_blueprint_is_the_one_that_was_resolved(self):
        self._complete_configuration()
        self._event_type("draft.only", publish=False)
        resolved = self._complete(event_types=[EVENT, "draft.only"],
                                  subtask_types=[SUBTASK_KIND])

        read_back = self._call(
            "get", f"{BLUEPRINTS}/{resolved['configuration_fingerprint']}",
            key=self._a_read_key())

        assert read_back == resolved
        assert read_back["diagnostics"], "nothing but the easy case was read"

    def test_it_is_what_was_resolved_whatever_has_changed_since(self):
        self._complete_configuration()
        resolved = self._complete()
        self._kinds({"key": KIND, "uncapped": True, "retired": True})

        read_back = self._call(
            "get", f"{BLUEPRINTS}/{resolved['configuration_fingerprint']}")

        assert read_back == resolved
        assert self._complete()["readiness"] == "blocked"

    @pytest.mark.parametrize("fingerprint", [
        "sha256:" + "0" * 64,
        "sha256:" + "0" * 63,
        "not-a-fingerprint",
        "SHA256:" + "A" * 64,
    ])
    def test_an_unknown_fingerprint_is_not_found(self, fingerprint):
        self._complete_configuration()
        self._complete()

        refused = self._send("get", f"{BLUEPRINTS}/{fingerprint}")

        assert refused.status_code == 404, refused.content
        assert refused.json()["code"] == "not_found"

    def test_another_tenants_fingerprint_is_not_found(self):
        self._complete_configuration()
        fingerprint = self._complete()["configuration_fingerprint"]
        _, somebody_elses_key = a_tenant("Other")

        refused = self._send("get", f"{BLUEPRINTS}/{fingerprint}",
                             key=somebody_elses_key)

        assert refused.status_code == 404, refused.content

    def test_a_pruned_fingerprint_is_not_found(self):
        self._complete_configuration()
        fingerprint = self._complete()["configuration_fingerprint"]
        BlueprintSnapshot.objects.all().delete()

        refused = self._send("get", f"{BLUEPRINTS}/{fingerprint}")

        assert refused.status_code == 404, refused.content
        assert refused.json()["code"] == "not_found"


# ---------------------------------------------------------------------------
# Draft preview
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestADraftPreviewIsForAnAdminAndLeavesNothingBehind(_Routes):
    def test_a_read_key_resolves_and_reads_but_may_not_preview_a_draft(self):
        self._complete_configuration()
        read_key = self._a_read_key()

        resolved = self._send("post", BLUEPRINTS, {
            "target": "python_sdk", "task_type": KIND,
            "event_types": [EVENT]}, key=read_key)
        refused = self._send("post", BLUEPRINTS, {
            "target": "python_sdk", "task_type": KIND,
            "event_types": [EVENT], "draft_preview": True}, key=read_key)

        assert resolved.status_code == 200, resolved.content
        assert refused.status_code == 403, refused.content
        assert refused.json()["code"] == "forbidden"
        assert BlueprintSnapshot.objects.count() == 1

    def test_it_resolves_the_draft_stores_nothing_and_has_no_fingerprint(self):
        self._complete_configuration()
        self._call("put", f"/api/v1/event-types/{EVENT}/measurements/"
                          "input_tokens",
                   {**INPUT_TOKENS, "source_path": ["usage", "prompt_tokens"]})
        before = _every_row()

        preview = self._complete(draft_preview=True)

        assert preview["configuration_fingerprint"] is None
        assert _tables_that_differ(before, _every_row()) == []
        record = _the_record(preview)
        # The draft's path, and no publication claimed for it.
        assert _one(record, "measurements.input_tokens.source_path")[
            "value"] == ["usage", "prompt_tokens"]
        assert _one(record, "event_type")["provenance"] == {
            "object_kind": "event_type", "key": EVENT,
            "published_revision": None, "published_at": None}
        assert preview["readiness"] == "complete"
        assert preview["diagnostics"] == []

    def test_it_resolves_an_event_type_that_was_never_published(self):
        self._a_kind()
        self._event_type(publish=False)

        preview = self._complete(draft_preview=True)

        assert preview["readiness"] == "complete"
        assert self._complete()["readiness"] == "blocked"


# ---------------------------------------------------------------------------
# Read-and-generate, even for an admin
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTheBuilderChangesNoConfiguration(_Routes):
    def test_the_builder_has_three_operations_and_none_is_a_configuration_write(
            self):
        """The whole surface, off the live API: one resolution, one read and
        one verification. There is no fourth operation for a write to be —
        and the verification's writes are to a tenant made for it and rolled
        back with it, which `test_verifying_a_blueprint.py` holds as a count
        of every table."""
        builder = sorted(
            (method, path)
            for prefix, router in api._routers
            if prefix.strip("/") == "code-builder"
            for path, view in router.path_operations.items()
            for operation in view.operations
            for method in operation.methods)

        assert builder == [("GET", "/blueprints/{configuration_fingerprint}"),
                           ("POST", "/blueprints"),
                           ("POST",
                            "/blueprints/{configuration_fingerprint}/verify")]

    def test_an_admin_resolving_a_blueprint_full_of_fixes_applies_none_of_them(
            self):
        """Every diagnostic here carries a request that would change
        configuration. An admin key asks, in both modes, and every
        configuration table is exactly as it was: nothing is declared,
        edited or published, and no request is executed."""
        self._a_kind()
        self._event_type("draft.only", publish=False)
        self._event_type("unshaped", shape="")
        self._event_type("constant", measurements={
            "calls": {**SEARCHES, "source_kind": "constant",
                      "constant_value": "1"},
            "total": {**SEARCHES, "source_kind": "derived"}})
        before = _every_row()

        published = self._complete(
            event_types=["draft.only", "unshaped", "constant", "missing"])
        preview = self._complete(
            event_types=["draft.only", "unshaped", "constant", "missing"],
            draft_preview=True)

        offered = [d["remediation_request"]["operation_id"]
                   for blueprint in (published, preview)
                   for d in blueprint["diagnostics"]
                   if d["remediation_request"]]
        assert len(set(offered)) >= 4, offered
        assert _tables_that_differ(before, _every_row()) == [
            "code_builder.BlueprintSnapshot"]
        assert self._call(
            "get", "/api/v1/event-types/draft.only")[
            "declaration_status"] == "draft"
        assert self._send(
            "get", "/api/v1/event-types/missing").status_code == 404


# ---------------------------------------------------------------------------
# Remediation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestARemediationRequestNamesTheFixAndCarriesNothingElse(_Routes):
    #: The kinds of object the console has no screen for, which is where a
    #: diagnostic carries a request instead of naming a page.
    WITHOUT_A_SCREEN = {"event_type", "measurement", "reported_cost_mapping",
                        "grouping_field"}
    #: The codes that name what this Code Builder cannot yet generate rather
    #: than anything wrong with the configuration (#571). No request is
    #: offered for one: the console words a request as the change an admin
    #: makes, and a valid declaration is not the thing to change.
    NOTHING_TO_CHANGE = {"constant_measurement_not_renderable"}

    def _every_remediation(self):
        """One Blueprint per situation, between them offering a request for
        every kind of object that has no screen."""
        self._grouping_fields(("environment", "task"))
        self._a_kind(required_grouping_fields=["environment"])
        self._require_without_declaring(KIND, "environment", "ghost")
        self._retire("environment")
        self._event_type("draft.only", publish=False, provider="acme-ai")
        self._event_type("unshaped", shape="")
        self._event_type("wrapped", shape="custom", label="acme-wrapper-v2")
        self._event_type("constant", measurements={
            "calls": {**SEARCHES, "source_kind": "constant",
                      "constant_value": "1"},
            "total": {**SEARCHES, "source_kind": "derived"}})
        self._event_type("billed.by.supplier", costing_method="reported",
                         measurements={},
                         mapping={"source_kind": "provider_response",
                                  "amount_representation": "minor_units",
                                  "source_path": ["amount_charged"],
                                  "currency": "usd"})
        self._event_type("unmapped", costing_method="reported",
                         measurements={}, publish=False)
        self._event_type("advised", shape=A_JSON_SHAPE, measurements={
            "input_tokens": {**INPUT_TOKENS,
                             "source_path": ["usage_metadata",
                                             "prompt_token_count"]}})
        self._call("put", "/api/v1/event-types/advised/measurements/extra",
                   SEARCHES)
        selection = ["draft.only", "unshaped", "wrapped", "constant",
                     "billed.by.supplier", "unmapped", "advised",
                     "missing.entirely"]
        published = self._complete(event_types=selection)
        preview = self._complete(event_types=selection, draft_preview=True)
        return [diagnostic for blueprint in (published, preview)
                for diagnostic in blueprint["diagnostics"]]

    def test_an_object_with_no_screen_carries_a_request_and_one_with_a_screen_does_not(
            self):
        diagnostics = self._every_remediation()

        carrying = {d["object_kind"] for d in diagnostics
                    if d["remediation_request"]}
        bare = {d["object_kind"] for d in diagnostics
                if not d["remediation_request"]
                and d["code"] not in self.NOTHING_TO_CHANGE}
        assert carrying == self.WITHOUT_A_SCREEN
        assert bare <= {"task_type", "subtask_type"}
        assert [d["remediation_request"] for d in diagnostics
                if d["code"] in self.NOTHING_TO_CHANGE] == [None, None]
        assert {d["code"] for d in diagnostics} >= {
            "event_type_not_declared", "event_type_not_published",
            "event_type_revised_since_publication",
            "reported_cost_mapping_missing",
            "reported_cost_provider_response_unsupported",
            "constant_measurement_not_renderable",
            "derived_measurement_unsupported",
            "response_shape_not_declared",
            "response_shape_not_readable_by_target",
            "source_path_convention_mismatch",
            "required_grouping_field_not_declared",
            "required_grouping_field_retired"}

    def test_every_published_code_is_one_a_resolution_reports(self):
        """The contract's whole set, against what resolutions actually answer
        with: no code is published that nothing produces, and each has one
        severity wherever it appears. The set is read off the committed
        contract, so a code added there and reported nowhere turns this red."""
        published = set(_schema("IntegrationBlueprintDiagnostic")[
            "properties"]["code"]["enum"])
        assert len(published) >= 15, "the contract's set was not read"
        diagnostics = self._every_remediation()
        self._grouping_fields(("environment", "task"), ("region", "event"))
        self._kinds({"key": "wrongly_scoped", "uncapped": True,
                     "required_grouping_fields": ["region"]},
                    {"key": "withdrawn", "uncapped": True, "retired": True})
        for selection in ({}, {"task_type": "nobody_declared_this"},
                          {"task_type": "wrongly_scoped"},
                          {"task_type": "withdrawn"}):
            diagnostics += self._resolve(**selection)["diagnostics"]

        severities = {}
        for diagnostic in diagnostics:
            severities.setdefault(diagnostic["code"], set()).add(
                diagnostic["severity"])

        assert set(severities) == published
        assert all(len(found) == 1 for found in severities.values()), (
            severities)
        assert {code for code, found in severities.items()
                if found == {"advisory"}} == {
            "event_type_revised_since_publication",
            "source_path_convention_mismatch"}

    def test_each_request_is_a_real_operation_addressed_to_the_object(self):
        """Method, route and operation agree with the committed contract, and
        the route is the operation's own path with the object's key in it."""
        operations = _operations()
        requests = [(d, d["remediation_request"])
                    for d in self._every_remediation()
                    if d["remediation_request"]]
        assert len(requests) >= 12

        for diagnostic, request in requests:
            assert set(request) == {"method", "route", "operation_id",
                                    "body"}, request
            method, path, _ = operations[request["operation_id"]]
            assert request["method"] == method, request
            pattern = "^" + re.sub(r"\\{\w+\\}", "[^/]+",
                                   re.escape(path)) + "$"
            assert re.match(pattern, request["route"]), (request, path)

    def test_a_request_that_declares_an_object_carries_its_key_in_the_body(
            self):
        """Where the operation takes the key in its body rather than its
        route, a body with the key left empty would be a request to declare
        nothing in particular."""
        by_code = {d["code"]: d["remediation_request"]
                   for d in self._every_remediation()}

        declare = by_code["event_type_not_declared"]
        assert declare["route"] == "/api/v1/event-types"
        assert declare["body"]["key"] == "missing.entirely"
        assert [value for name, value in declare["body"].items()
                if name != "key"] == [None] * (len(declare["body"]) - 1)
        field = by_code["required_grouping_field_not_declared"]
        assert field["route"] == "/api/v1/metering/grouping-fields"
        assert field["body"] == {"grouping_fields": [
            {"key": "ghost", "slot": None, "scope": None,
             "max_cardinality": None}]}
        # And where the route carries the key, the body does not repeat it.
        revise = by_code["response_shape_not_declared"]
        assert revise["route"] == "/api/v1/event-types/unshaped"
        assert set(revise["body"].values()) == {None}

    def test_each_body_is_a_skeleton_of_fields_the_operation_publishes(self):
        """Published field names with nothing filled in but the object's own
        key. A name the route does not publish would be dropped in silence."""
        operations = _operations()
        checked, rows_followed = 0, 0
        for diagnostic in self._every_remediation():
            request = diagnostic["remediation_request"]
            if not request:
                continue
            _, _, operation = operations[request["operation_id"]]
            schema = _request_schema(operation)
            if request["body"] is None:
                assert schema is None, request
                continue
            checked += 1
            rows_followed += any(isinstance(value, list)
                                 for value in request["body"].values())
            assert _unpublished_keys(request["body"], schema) == [], request
            assert request["body"], request
        assert checked >= 6
        assert rows_followed, "no body with rows was followed into its rows"

    def test_no_request_carries_a_secret_or_a_tenant_value_beyond_the_key(
            self):
        """Every leaf of every body is empty or is part of the object's key,
        and the route names nothing but that key. The supplier's key, the
        declared shape, the paths and the amounts are all the tenant's and
        none of them travels."""
        Tenant.objects.filter(pk=self.tenant.pk).update(
            widget_secret="whsec-KNOWN-widget-secret")
        tenant_values = {"acme-ai", "acme-wrapper-v2", "custom", A_JSON_SHAPE,
                         "prompt_token_count", "usage_metadata", "usd",
                         "minor_units", "amount_charged", "search",
                         "caller_supplied", "provider_response",
                         "whsec-KNOWN-widget-secret", self.raw_key}

        def leaves(node):
            if isinstance(node, dict):
                for value in node.values():
                    yield from leaves(value)
            elif isinstance(node, list):
                for value in node:
                    yield from leaves(value)
            else:
                yield node

        checked = set()
        for diagnostic in self._every_remediation():
            request = diagnostic["remediation_request"]
            if not request:
                continue
            checked.add(diagnostic["object_kind"])
            key_parts = set(diagnostic["key"].split(":"))
            filled = [leaf for leaf in leaves(request["body"])
                      if leaf is not None]
            assert set(filled) <= key_parts, (diagnostic, filled)
            # The route and the filled leaves are everywhere a value could
            # be; the body's field NAMES are the contract's, not the tenant's.
            carried = " ".join([request["route"], *map(str, filled)])
            for value in tenant_values - key_parts:
                assert value not in carried, (value, request)
        assert checked == self.WITHOUT_A_SCREEN


# ---------------------------------------------------------------------------
# A reset of a sandbox takes its snapshots with it
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestASandboxResetWipesTheSnapshots(_Routes):
    def setup_method(self):
        """A sandbox, configured and resolved through its own test key — the
        rows a reset meets are the ones a route produced."""
        self.live = Tenant.objects.create(name="Live", products=["metering"])
        self.tenant = get_or_create_sandbox(self.live)
        _, self.raw_key = TenantApiKey.create_key(self.live, is_test=True)
        self.client = Client()

    @pytest.mark.parametrize("keep_config", [True, False])
    def test_a_reset_removes_them_whether_or_not_it_keeps_configuration(
            self, keep_config):
        """A snapshot is a derived fixture and not configuration, so it is not
        among what a reset keeps: its fingerprint then answers as a pruned one
        does, and the developer resolves again."""
        self._grouping_fields(("environment", "task"), ("phase", "subtask"))
        self._kinds(
            {"key": KIND, "task_cogs_ceiling_micros": 5_000_000,
             "required_grouping_fields": ["environment"]},
            {"key": SUBTASK_KIND, "kind": "subtask", "uncapped": True,
             "required_grouping_fields": ["phase"]})
        # ⚠ NO SUPPLIER ON THE EVENT TYPE, AND THAT IS A WORKAROUND. A reset
        # that wipes configuration is refused outright for any Event Type that
        # names one — the generic sweep reaches the supplier first and the
        # Event Type holds it with PROTECT (#593). That break is the reset's,
        # predates this module and is not about a snapshot, so the fixture
        # steps round it rather than assert through it.
        self._event_type(
            measurements={"input_tokens": INPUT_TOKENS, "searches": SEARCHES})
        fingerprint = self._complete(
            subtask_types=[SUBTASK_KIND])["configuration_fingerprint"]
        assert "code_builder.BlueprintSnapshot" not in CONFIG_MODEL_LABELS

        result = reset_sandbox_tenant_sync(self.tenant.id,
                                           keep_config=keep_config)

        assert result["status"] == "completed"
        assert result["deleted"]["code_builder.BlueprintSnapshot"] == 1
        assert BlueprintSnapshot.objects.count() == 0
        assert self._send(
            "get", f"{BLUEPRINTS}/{fingerprint}").status_code == 404
