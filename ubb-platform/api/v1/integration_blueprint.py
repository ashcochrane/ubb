"""Resolving an Integration Blueprint: what a tenant's integration must MEAN.

A developer selects a target, a kind of work, the Event Types that happen
inside it and — only if their integration creates them — the Subtask kinds.
Everything else is looked up, never asked for again: asking twice makes a
second place the answer can be given, and the two then disagree (#156 §1).

**The server decides meaning; a renderer decides expression** (#184 §1). What
this module answers is a document of calls, each a list of TOKENS with the
class that says where the token's value comes from, a readiness verdict per
call and for the whole, and the diagnostics that explain a verdict. It emits no
code, names no import and formats nothing.

**Why the composition layer.** Resolution reads kinds of work and Grouping
Fields (kernel, through their read contracts), the Event Type catalogue
(kernel), and the rules that cost and price an event (metering). ADR-001 rule 4
lets this layer read any product, so it adds no channel and no `queries.py`
(#184 §2).

**Every literal says where it was read from.** A value UBB filled in carries
the declaration it came from, so the document is a reading of the registries
and never a second place a fact is held (ADR-0006 §4). What it carries of an
Event Type is what that Event Type last PUBLISHED, which the registry's own
routes stop serving the moment a draft edit lands — so for those facts this
document is the only place a consumer can read them.

**It reads and it stores one thing.** For a resolution from PUBLISHED
configuration the caller keeps what this returns, as an immutable snapshot
addressed by a hash (`apps.platform.code_builder`). Nothing in this module
writes a row, and no path through it declares, edits or publishes
configuration or performs the request a diagnostic offers — for an admin
exactly as for anybody else.

WHAT THE FINGERPRINT IS THE HASH OF
-----------------------------------
The NORMATIVE resolved contract, and nothing presentational (owner ruling of
2026-10-02). `resolve` returns it as `identity`, and the store hashes exactly
that:

* the selection;
* the Blueprint's machine-readable resolution — the versions needed to read
  it, the target, every call and token, each verdict, and each diagnostic's
  code and the declaration it is about;
* the configuration it was resolved from, with the publication each Event
  Type's facts came from. A republication is therefore a new fingerprint,
  deliberately: the generated file's header says which publication it read.

What is kept beside it and NOT hashed is `presentation`: the ready-to-copy
request a diagnostic offers. It is built from the API's own routes and request
shapes, so it can change with no change to what the tenant configured or to
what the code must mean — a registry route gaining a field must not make every
blocked integration look like a different one.

Nothing volatile is in the identity: no row id, no row timestamp, no moment of
resolution, no wording. And no ORDER that means nothing: the selection, a
kind's required Grouping Fields, a tenant's products and the rules in force
are each put in a canonical order before they are hashed, so declaring the
same things in another order is the same fingerprint. The order of `calls` is
the lifecycle's, and is meant.

HOW A TOKEN IS ADDRESSED
------------------------
An argument is ONE token, and its `name` says where on the call it sits. A
name is one, two or three segments joined by dots:

* **`<field>`** — a published field of the call's request (`task_type`,
  `customer_id`), or the credential every call carries (`api_key`). For a
  field that holds an object of declared keys (`grouping_fields`,
  `measurements`) a token named for the field is one KEY of it, carrying the
  declared key as its literal — one such token per entry.
* **`<field>.<key>`** — the VALUE under a declared key of such a field. A known
  key beside a runtime value is the ordinary case, and one token cannot be
  both classes.
* **`<field>.<element>`** and **`<field>.<key>.<element>`** — a declared fact
  about the value it is named under, spelled as the declaration's own
  published field: `task_type.pricing_mode`, `event_type.costing_method`,
  `measurements.<key>.source_path`, `provider_cost_micros.amount_representation`.
  One element is UBB's fact rather than the tenant's and is named for its
  registry concept: `event_type.response_shape_representation`.

A key is ONE segment whatever it contains: a dot or a percent sign inside a
declared key is percent-encoded in the name, so a name always splits on its
dots, and a key that happens to end like an element cannot be taken for one.
The encoding has one implementation, with its inverse beside it:
`apps.platform.code_builder.token_names`. Nothing here spells it.

A consumer never needs the encoding. A key's own token carries the key
unencoded, as its literal, and the tokens named under that key FOLLOW IT
DIRECTLY, sharing one `<field>.<segment>` prefix — so a renderer pairs them by
position and reads the prefix off the name it was handed.

The declared facts are `platform_known` like any literal: resolved, with the
declaration they came from. A renderer may respell one or branch on it, and
never asks the developer for it again.

⚠ A literal is untyped JSON, so a closed concept's value travelling as one —
a pricing mode, a costing method, a quantity's value type, an amount
representation, a response shape's representation — carries no marker on the
contract. Each is a declared value, marked on the route that declares it
where one does.
"""
import keyword
from typing import Callable, NamedTuple
from urllib.parse import quote

from django.db.models import Q
from django.utils import timezone

from api.v1 import event_type_endpoints, metering_endpoints, task_endpoints
from api.v1.schemas import (
    EventTypeIn, EventTypeUpdateIn, MeasurementIn, ReportedCostMappingIn)
from apps.metering.pricing.models import (
    CostBook, PricingBook, TenantDefaultMarkup)
from apps.metering.pricing.services.book_service import rules_in_force_at
from apps.platform.code_builder import snapshots, token_names
from apps.platform.code_builder.withheld import (
    API_KEY, environment_variable, is_withheld)
from apps.platform.event_types.models import (
    REPORTED_COST_PARAMETER, EventType)
from apps.platform.event_types.publication import (
    draft_declaration, last_published_declaration)
from apps.platform.event_types.source_paths import (
    SHAPE_REPRESENTATIONS, advisories)
from apps.platform.grouping_fields.models import SLOTS
from apps.platform.grouping_fields.queries import declared_grouping_fields
from apps.platform.tenants.services.sandbox_service import (
    copied_to_a_sandbox)
from apps.platform.work.queries import task_type_policy
from core.problems import Problem
from core.vocabulary import (
    BINDING_CLASS_PLATFORM_KNOWN,
    BINDING_CLASS_RUNTIME_BOUND,
    BINDING_CLASS_SECRET_REFERENCE,
    CODE_TARGET_PYTHON_SDK,
    CODE_TARGET_SHELL_HTTP,
    CODE_TARGET_VALUES,
    CONFIGURATION_OBJECT_KIND_EVENT_TYPE,
    CONFIGURATION_OBJECT_KIND_GROUPING_FIELD,
    CONFIGURATION_OBJECT_KIND_MEASUREMENT,
    CONFIGURATION_OBJECT_KIND_PROVIDER,
    CONFIGURATION_OBJECT_KIND_REPORTED_COST_MAPPING,
    CONFIGURATION_OBJECT_KIND_SUBTASK_TYPE,
    CONFIGURATION_OBJECT_KIND_TASK_TYPE,
    COSTING_METHOD_REPORTED,
    DECLARATION_STATUS_PUBLISHED,
    DIAGNOSTIC_CODE_CONSTANT_MEASUREMENT_NOT_RENDERABLE,
    DIAGNOSTIC_CODE_DERIVED_MEASUREMENT_UNSUPPORTED,
    DIAGNOSTIC_CODE_EVENT_TYPE_NOT_DECLARED,
    DIAGNOSTIC_CODE_EVENT_TYPE_NOT_PUBLISHED,
    DIAGNOSTIC_CODE_EVENT_TYPE_NOT_SELECTED,
    DIAGNOSTIC_CODE_EVENT_TYPE_REVISED_SINCE_PUBLICATION,
    DIAGNOSTIC_CODE_REPORTED_COST_MAPPING_MISSING,
    DIAGNOSTIC_CODE_REPORTED_COST_PROVIDER_RESPONSE_NOT_RENDERABLE,
    DIAGNOSTIC_CODE_REQUIRED_GROUPING_FIELD_NOT_DECLARED,
    DIAGNOSTIC_CODE_REQUIRED_GROUPING_FIELD_RETIRED,
    DIAGNOSTIC_CODE_REQUIRED_GROUPING_FIELD_WRONG_SCOPE,
    DIAGNOSTIC_CODE_RESPONSE_SHAPE_NOT_DECLARED,
    DIAGNOSTIC_CODE_RESPONSE_SHAPE_NOT_READABLE_BY_TARGET,
    DIAGNOSTIC_CODE_SOURCE_PATH_CONVENTION_MISMATCH,
    DIAGNOSTIC_CODE_TASK_TYPE_NOT_DECLARED,
    DIAGNOSTIC_CODE_TASK_TYPE_NOT_SELECTED,
    DIAGNOSTIC_CODE_TASK_TYPE_RETIRED,
    DIAGNOSTIC_SEVERITY_ADVISORY,
    DIAGNOSTIC_SEVERITY_BLOCKING,
    GROUPING_FIELD_SCOPE_SUBTASK,
    GROUPING_FIELD_SCOPE_TASK,
    INTEGRATION_READINESS_BLOCKED,
    INTEGRATION_READINESS_COMPLETE,
    INTEGRATION_READINESS_SCAFFOLD,
    RESPONSE_SHAPE_REPRESENTATION_JSON,
    RESPONSE_SHAPE_REPRESENTATION_PYTHON_OBJECT,
    SOURCE_KIND_CALLER_SUPPLIED,
    SOURCE_KIND_CONSTANT,
    SOURCE_KIND_DERIVED,
    SOURCE_KIND_PROVIDER_RESPONSE,
    TASK_TYPE_KIND_SUBTASK,
    TASK_TYPE_KIND_TASK,
)

#: Which shape this document is, so a consumer can parse it.
SCHEMA_VERSION = 1

#: Which renderer contract the document was resolved for. A different question
#: from the one above and never the same number by design (#148's split): the
#: first changes when a field does, this one when what a renderer is promised
#: about a field's meaning does.
RENDERER_CONTRACT_VERSION = 1

#: The SDK major the Python target is generated against (owner item 3,
#: 2026-09-25). Stated only for that target: a shell file uses no SDK, and a
#: number there would be a version of nothing.
#: `tests/contracts/test_the_blueprint_targets_the_sdk_that_ships.py` holds the
#: number to the SDK's own version.
SDK_MAJOR_VERSION = {CODE_TARGET_PYTHON_SDK: 3, CODE_TARGET_SHELL_HTTP: None}

#: Which response representations each target can read (owner item 6). A shell
#: file holds text, so it reads the JSON a web API returns and nothing else;
#: Python can hold either. A shape that declares no representation — a tenant's
#: own wrapper — is in neither set, so no target reads it until a renderer
#: defines how to traverse one.
READABLE_REPRESENTATIONS = {
    CODE_TARGET_PYTHON_SDK: frozenset({
        RESPONSE_SHAPE_REPRESENTATION_JSON,
        RESPONSE_SHAPE_REPRESENTATION_PYTHON_OBJECT}),
    CODE_TARGET_SHELL_HTTP: frozenset({RESPONSE_SHAPE_REPRESENTATION_JSON}),
}

#: Where, in a snapshot's identity, the Blueprint's normative half is — beside
#: the selection it answers and the configuration it was resolved from.
BLUEPRINT = "blueprint"

#: How many distinct Event Types, and how many distinct Subtask kinds, one
#: selection may name. The resolution is a READ-floor call that reads several
#: rows per name, so the bound is what keeps an expensive read safe at that
#: floor.
MAXIMUM_SELECTED = 50

#: Least ready first. An integration is as ready as its least ready call, so
#: a verdict is the earliest of these any call reached.
_LEAST_READY_FIRST = (INTEGRATION_READINESS_SCAFFOLD,
                      INTEGRATION_READINESS_BLOCKED,
                      INTEGRATION_READINESS_COMPLETE)


class _Effect(NamedTuple):
    """What reporting one diagnostic code does."""
    severity: str
    #: The readiness a call can be no better than once this is reported, or
    #: `None` for an advisory, which lowers nothing.
    caps_the_call_at: str | None


_STRUCTURAL = _Effect(DIAGNOSTIC_SEVERITY_BLOCKING,
                      INTEGRATION_READINESS_SCAFFOLD)
_BLOCKING = _Effect(DIAGNOSTIC_SEVERITY_BLOCKING,
                    INTEGRATION_READINESS_BLOCKED)
_ADVISORY = _Effect(DIAGNOSTIC_SEVERITY_ADVISORY, None)

#: Every code, and what it does. A code's severity is a fact about the code
#: and never about the occasion, which is why it is looked up here rather than
#: chosen where the code is reported.
#:
#: The first four are STRUCTURAL: the selection itself is missing a kind of
#: work or an Event Type, so the call teaches the lifecycle's shape and cannot
#: run. Everything else that is not advice BLOCKS: the structure is known and
#: the call lacks something it cannot run without (#184 §8).
EFFECTS = {
    DIAGNOSTIC_CODE_TASK_TYPE_NOT_SELECTED: _STRUCTURAL,
    DIAGNOSTIC_CODE_TASK_TYPE_NOT_DECLARED: _STRUCTURAL,
    DIAGNOSTIC_CODE_EVENT_TYPE_NOT_SELECTED: _STRUCTURAL,
    DIAGNOSTIC_CODE_EVENT_TYPE_NOT_DECLARED: _STRUCTURAL,
    DIAGNOSTIC_CODE_TASK_TYPE_RETIRED: _BLOCKING,
    DIAGNOSTIC_CODE_REQUIRED_GROUPING_FIELD_NOT_DECLARED: _BLOCKING,
    DIAGNOSTIC_CODE_REQUIRED_GROUPING_FIELD_RETIRED: _BLOCKING,
    DIAGNOSTIC_CODE_REQUIRED_GROUPING_FIELD_WRONG_SCOPE: _BLOCKING,
    DIAGNOSTIC_CODE_EVENT_TYPE_NOT_PUBLISHED: _BLOCKING,
    DIAGNOSTIC_CODE_REPORTED_COST_MAPPING_MISSING: _BLOCKING,
    # Valid configuration this Code Builder version cannot yet render: a cost
    # read off a supplier's response has its own transport since #570, and
    # generated code does not yet read it. Lifted by the ticket that renders
    # the read (#583); the member leaves the registry with it.
    DIAGNOSTIC_CODE_REPORTED_COST_PROVIDER_RESPONSE_NOT_RENDERABLE: _BLOCKING,
    DIAGNOSTIC_CODE_CONSTANT_MEASUREMENT_NOT_RENDERABLE: _BLOCKING,
    DIAGNOSTIC_CODE_DERIVED_MEASUREMENT_UNSUPPORTED: _BLOCKING,
    DIAGNOSTIC_CODE_RESPONSE_SHAPE_NOT_DECLARED: _BLOCKING,
    DIAGNOSTIC_CODE_RESPONSE_SHAPE_NOT_READABLE_BY_TARGET: _BLOCKING,
    DIAGNOSTIC_CODE_EVENT_TYPE_REVISED_SINCE_PUBLICATION: _ADVISORY,
    DIAGNOSTIC_CODE_SOURCE_PATH_CONVENTION_MISMATCH: _ADVISORY,
}

#: Which object a kind of work is, by the altitude it was declared for. Two
#: values, because a kind's identity is its altitude and its key together.
_KIND_OBJECT = {
    TASK_TYPE_KIND_TASK: CONFIGURATION_OBJECT_KIND_TASK_TYPE,
    TASK_TYPE_KIND_SUBTASK: CONFIGURATION_OBJECT_KIND_SUBTASK_TYPE,
}

#: The scope a required Grouping Field must have to be supplied at a start of
#: each altitude. A start accepts a value only at the field's own scope
#: (`RiskService.resolve_start_policy`), so a kind requiring a field of any
#: other scope can never start.
_SCOPE_OF_A_START = {
    TASK_TYPE_KIND_TASK: GROUPING_FIELD_SCOPE_TASK,
    TASK_TYPE_KIND_SUBTASK: GROUPING_FIELD_SCOPE_SUBTASK,
}

#: The parameter a quantity read off the supplier's response is read FROM: the
#: response object itself, which only the tenant's code ever holds.
RESPONSE_PARAMETER = "response"


# ---------------------------------------------------------------------------
# The operations a Blueprint names
# ---------------------------------------------------------------------------

def _operation_id(view):
    """The operationId the contract publishes for a route's handler.

    Read off the handler rather than spelled, so a renamed handler moves the
    name here with it. The Blueprint's own tests hold every one of these to
    `openapi/v1.json`, which is what makes it a real operation rather than a
    string that happens to look like one.
    """
    return f"{view.__module__.replace('.', '_')}_{view.__name__}"


START_TASK = _operation_id(task_endpoints.start_task)
RECORD_USAGE = _operation_id(metering_endpoints.record_usage)
CLOSE_TASK = _operation_id(task_endpoints.close_task)


class _Remediation(NamedTuple):
    """One request a diagnostic may offer: the operation, and its body."""
    view: object
    method: str
    #: The published path, with the object's key as its only parameters.
    path: str
    #: The body for an object's key: the operation's published fields with
    #: nothing filled in but that key, or `None` for an operation taking none.
    body: Callable


def _no_body(key):
    return None


def _the_fields_of(schema):
    """A body of `schema`'s published fields, every one empty — except `key`,
    where the operation takes the object's key in its body rather than its
    route."""
    names = tuple(schema.model_fields)

    def body(key):
        skeleton = dict.fromkeys(names)
        if "key" in skeleton:
            skeleton["key"] = key
        return skeleton
    return body


#: The Grouping Field registry takes a list of declarations under one field.
#: Its row is spelled here rather than read off the route's request schema,
#: which a later rename moves: a Blueprint binds to the published field names
#: and to no schema of that registry.
_GROUPING_FIELDS = "grouping_fields"
_GROUPING_FIELD_ROW = ("key", "slot", "scope", "max_cardinality")


def _one_grouping_field(key):
    return {_GROUPING_FIELDS: [{**dict.fromkeys(_GROUPING_FIELD_ROW),
                                "key": key}]}


_DECLARE_EVENT_TYPE = _Remediation(
    event_type_endpoints.declare_event_type, "POST",
    "/api/v1/event-types", _the_fields_of(EventTypeIn))
_REVISE_EVENT_TYPE = _Remediation(
    event_type_endpoints.revise_event_type, "PATCH",
    "/api/v1/event-types/{key}", _the_fields_of(EventTypeUpdateIn))
_PUBLISH_EVENT_TYPE = _Remediation(
    event_type_endpoints.publish_event_type, "POST",
    "/api/v1/event-types/{key}/publish", _no_body)
_DECLARE_MEASUREMENT = _Remediation(
    event_type_endpoints.declare_measurement, "PUT",
    "/api/v1/event-types/{key}/measurements/{code}",
    _the_fields_of(MeasurementIn))
_DECLARE_MAPPING = _Remediation(
    event_type_endpoints.declare_reported_cost_mapping, "PUT",
    "/api/v1/event-types/{key}/reported-cost-mapping",
    _the_fields_of(ReportedCostMappingIn))
_DECLARE_GROUPING_FIELD = _Remediation(
    metering_endpoints.declare_grouping_fields, "PUT",
    "/api/v1/metering/grouping-fields", _one_grouping_field)


def _remediation_request(remediation, *, key, code=None):
    """The request that fixes a diagnostic, ready to copy and never performed.

    It names the object by its key and nothing else of the tenant's. The key
    goes where the operation takes it — in the route, or in the body for an
    operation that declares a new object — and every other field of the body
    is left empty. No secret is reachable from here: the function is handed
    keys and field names.
    """
    in_the_route = {"key": key} if code is None else {"key": key, "code": code}
    return {
        "method": remediation.method,
        "route": remediation.path.format(**{
            name: quote(value, safe="")
            for name, value in in_the_route.items()}),
        "operation_id": _operation_id(remediation.view),
        "body": remediation.body(key),
    }


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

def binding_class_of(token, *, resolvable):
    """The class of one token, by the three ordered questions (#184 §4).

    1. Can UBB resolve it now, from this tenant's own published configuration?
       No — it is `runtime_bound`.
    2. Yes: is it on the withhold list? Then it is a `secret_reference`.
    3. Otherwise it is `platform_known`.

    The order is the rule. A withheld token is one UBB could resolve and
    refuses to, so the second question is only ever asked of a value the first
    one admitted.
    """
    if not resolvable:
        return BINDING_CLASS_RUNTIME_BOUND
    if is_withheld(token):
        return BINDING_CLASS_SECRET_REFERENCE
    return BINDING_CLASS_PLATFORM_KNOWN


def _token(name, *, binding_class, value=None, parameter_name=None,
           environment=None, configured=True, provenance=None):
    return {"name": name, "binding_class": binding_class, "value": value,
            "parameter_name": parameter_name,
            "environment_variable": environment, "configured": configured,
            "provenance": provenance}


def _known(name, value, provenance):
    """A literal: resolved now, from a declaration `provenance` names."""
    return _token(name, binding_class=binding_class_of(name, resolvable=True),
                  value=value, provenance=provenance)


def _unconfigured(name):
    """A value UBB would know if the tenant had configured it.

    It keeps its class and says it is not configured — a state of the class,
    never a fourth one. No value is made up for it and it points at no
    declaration, because there is none.
    """
    return _token(name, binding_class=binding_class_of(name, resolvable=True),
                  configured=False)


def _runtime(name, parameter_name, provenance=None):
    """A value only the tenant's code holds, as the parameter it must pass."""
    return _token(name, binding_class=binding_class_of(name, resolvable=False),
                  parameter_name=parameter_name, provenance=provenance)


def _credential():
    """The tenant's API key: a value UBB withholds, as the variable's NAME."""
    return _token(API_KEY,
                  binding_class=binding_class_of(API_KEY, resolvable=True),
                  environment=environment_variable(API_KEY))


def _provenance(object_kind, key, publication=None):
    """Which declaration a value was read from.

    An Event Type's facts also say which publication, in the names the Event
    Type's own route serves. A kind of work and a Grouping Field have no
    publish record, and a draft preview resolves from no publication, so
    those carry neither — a held file is told from a current one by the
    fingerprint (ADR-0012).
    """
    return {
        "object_kind": object_kind, "key": key,
        "published_revision": (publication.published_revision
                               if publication else None),
        "published_at": (publication.published_at.isoformat()
                         if publication else None),
    }


class _Parameters:
    """The parameter names one call asks for, each spellable and each once.

    A declared key is the tenant's own word and may be anything; the parameter
    a generated file asks for has to be an identifier. The literal keeps the
    word exactly, and only the parameter is respelled — deterministically, so
    the same declaration always asks for the same parameter.
    """

    def __init__(self, *taken):
        self._taken = set(taken)

    def reserve(self, *names):
        """Names this call asks for by a fixed spelling, whether or not this
        resolution emits them — so a declared key spelled the same way is
        given another parameter rather than sharing one."""
        self._taken.update(names)

    def named_for(self, key):
        spelled = "".join(character if character.isalnum() and
                          character.isascii() else "_" for character in key)
        if not spelled or spelled[0].isdigit() or keyword.iskeyword(spelled):
            spelled = f"value_{spelled}"
        candidate, suffix = spelled, 2
        while candidate in self._taken:
            candidate, suffix = f"{spelled}_{suffix}", suffix + 1
        self._taken.add(candidate)
        return candidate


# ---------------------------------------------------------------------------
# One resolution
# ---------------------------------------------------------------------------

class _Call:
    """One generated call site: its operation, its tokens and its verdict."""

    def __init__(self, operation_id, *fixed_parameters):
        self.operation_id = operation_id
        self.arguments = [_credential()]
        self.readiness = INTEGRATION_READINESS_COMPLETE
        self.parameters = _Parameters(*fixed_parameters)
        for parameter in fixed_parameters:
            self.arguments.append(_runtime(parameter, parameter))

    def add(self, *tokens):
        self.arguments.extend(tokens)

    def cap_at(self, readiness):
        self.readiness = min(self.readiness, readiness,
                             key=_LEAST_READY_FIRST.index)

    def as_published(self):
        return {"operation_id": self.operation_id,
                "readiness": self.readiness, "arguments": self.arguments}


class _Resolution:
    """The calls and the diagnostics of one Blueprint, as they accumulate."""

    def __init__(self, tenant, target, draft_preview):
        self.tenant = tenant
        self.target = target
        self.draft_preview = draft_preview
        self.calls = []
        self.diagnostics = []

    def call(self, operation_id, *fixed_parameters):
        call = _Call(operation_id, *fixed_parameters)
        self.calls.append(call)
        return call

    def report(self, call, code, object_kind, key, *, field=None,
               remediation_request=None):
        """Record one diagnostic, and lower the call it is about.

        Coded, addressed and wordless: the console words a code from its label
        key, and nothing a tenant typed is carried as prose.
        """
        effect = EFFECTS[code]
        if effect.caps_the_call_at is not None:
            call.cap_at(effect.caps_the_call_at)
        self.diagnostics.append({
            "severity": effect.severity, "code": code,
            "object_kind": object_kind, "key": key, "field": field,
            "remediation_request": remediation_request})

    def readiness(self):
        return min((call.readiness for call in self.calls),
                   key=_LEAST_READY_FIRST.index)


def _the_selection(target, event_types, subtask_types):
    """The selection as it is resolved: a SET, in key order, or a refusal.

    The Event Types and the Subtask kinds are resolved in key order whatever
    order they were sent in and however often one was named, so one
    integration has one fingerprint.

    The refusals are held in code. The marker that enumerates `target` on the
    contract is applied when the document is exported and refuses nothing
    here.
    """
    if target not in CODE_TARGET_VALUES:
        raise Problem(
            "validation_error",
            f"{target!r} is not a target: the targets are "
            f"{', '.join(sorted(CODE_TARGET_VALUES))}")
    selected = {"event_types": sorted(set(event_types)),
                "subtask_types": sorted(set(subtask_types))}
    for name, keys in selected.items():
        if len(keys) > MAXIMUM_SELECTED:
            raise Problem(
                "validation_error",
                f"{name} names {len(keys)} distinct entries; one selection "
                f"may name at most {MAXIMUM_SELECTED}")
    return selected["event_types"], selected["subtask_types"]


class Resolved(NamedTuple):
    """One resolution: the Blueprint, and the two halves to keep for it."""
    #: The Blueprint as it is answered, without its fingerprint — the
    #: fingerprint is the hash of `identity`, which holds the Blueprint's
    #: normative half, so it cannot also be inside it.
    document: dict
    #: What the fingerprint is the hash of. `None` for a draft preview: a
    #: preview is not resolved from published configuration, so there is
    #: nothing it may be stored or verified as.
    identity: dict | None
    #: What is kept beside the identity and not hashed. `None` with it.
    presentation: dict | None


#: Where, in the presentation half, the request each diagnostic offers is
#: kept — one per diagnostic, in the diagnostics' own order.
REMEDIATION_REQUESTS = "remediation_requests"

#: The one field of a diagnostic that is presentation rather than identity.
_REMEDIATION_REQUEST = "remediation_request"


def as_answered(content):
    """The Blueprint a stored snapshot was answered as, without its
    fingerprint: the normative half, with each diagnostic given back the
    request it offered."""
    blueprint = content[snapshots.IDENTITY][BLUEPRINT]
    requests = content[snapshots.PRESENTATION][REMEDIATION_REQUESTS]
    return {**blueprint, "diagnostics": [
        {**diagnostic, _REMEDIATION_REQUEST: request}
        for diagnostic, request in zip(blueprint["diagnostics"], requests,
                                       strict=True)]}


def resolve(tenant, *, target, task_type=None, event_types=(),
            subtask_types=(), draft_preview=False):
    """The Blueprint for one selection, and what to keep for it."""
    event_types, subtask_types = _the_selection(target, event_types,
                                                subtask_types)
    resolution = _Resolution(tenant, target, draft_preview)
    declared_fields = {field["key"]: field
                       for field in declared_grouping_fields(tenant.id)}

    kinds = [_start(resolution, TASK_TYPE_KIND_TASK, task_type,
                    declared_fields)]
    kinds += [_start(resolution, TASK_TYPE_KIND_SUBTASK, key, declared_fields)
              for key in subtask_types]

    resolved_event_types = [_record(resolution, key) for key in event_types]
    if not event_types:
        _record_nothing_selected(resolution)

    # Every token of a close is the caller's own, so there is nothing to
    # resolve for it: which unit of work, and what became of it.
    resolution.call(CLOSE_TASK, "task_id", "outcome")

    document = {
        "schema_version": SCHEMA_VERSION,
        "renderer_contract_version": RENDERER_CONTRACT_VERSION,
        "target": target,
        "sdk_major_version": SDK_MAJOR_VERSION[target],
        "readiness": resolution.readiness(),
        "calls": [call.as_published() for call in resolution.calls],
        "diagnostics": resolution.diagnostics,
    }
    if draft_preview:
        return Resolved(document, None, None)

    identity = {
        "selection": {"target": target, "task_type": task_type,
                      "event_types": event_types,
                      "subtask_types": subtask_types},
        # The Blueprint without what its diagnostics OFFER. A diagnostic's
        # code and the declaration it is about are part of what was resolved;
        # the request that would fix it is how the API spells the fix.
        BLUEPRINT: {**document, "diagnostics": [
            {name: value for name, value in diagnostic.items()
             if name != _REMEDIATION_REQUEST}
            for diagnostic in resolution.diagnostics]},
        "configuration": _configuration(
            tenant, kinds,
            [resolved for resolved in resolved_event_types
             if resolved is not None],
            declared_fields),
    }
    presentation = {REMEDIATION_REQUESTS: [
        diagnostic[_REMEDIATION_REQUEST]
        for diagnostic in resolution.diagnostics]}
    return Resolved(document, identity, presentation)


# ---------------------------------------------------------------------------
# A start: the kind of work, and the Grouping Fields it requires
# ---------------------------------------------------------------------------

def _start(resolution, altitude, key, declared_fields):
    """The call that starts work of one kind. Returns the kind as resolved, or
    `None` where the selection names none that is declared.

    A Subtask is started by the same operation as a Task and told apart by
    naming its parent, so the altitude decides one token and which scope a
    required Grouping Field must have.
    """
    fixed = ["customer_id", "idempotency_key"]
    if altitude == TASK_TYPE_KIND_SUBTASK:
        fixed.append("parent_task_id")
    call = resolution.call(START_TASK, *fixed)
    object_kind = _KIND_OBJECT[altitude]

    policy = (task_type_policy(resolution.tenant.id, key, altitude)
              if key else None)
    if policy is None:
        call.add(_unconfigured("task_type"))
        resolution.report(
            call,
            DIAGNOSTIC_CODE_TASK_TYPE_NOT_DECLARED if key
            else DIAGNOSTIC_CODE_TASK_TYPE_NOT_SELECTED,
            object_kind, key or None)
        return None

    declared_by_the_kind = _provenance(object_kind, key)
    call.add(_known("task_type", key, declared_by_the_kind),
             # How this kind of work is sold, and what it may spend: a figure,
             # or the declaration that it has none. Neither is sent on a start
             # — the kind applies both — and both are what a reader of the
             # generated file is owed beside the call that starts the work.
             _known("task_type.pricing_mode", policy["pricing_mode"],
                    declared_by_the_kind),
             _known("task_type.uncapped", policy["uncapped"],
                    declared_by_the_kind))
    if not policy["uncapped"]:
        call.add(_known("task_type.task_cogs_ceiling_micros",
                        policy["task_cogs_ceiling_micros"],
                        declared_by_the_kind))
    if policy["retired"]:
        resolution.report(call, DIAGNOSTIC_CODE_TASK_TYPE_RETIRED,
                          object_kind, key, field="retired")

    # In key order, and each once. The order a kind lists its requirements in
    # means nothing, so it must not reach the tokens or the fingerprint.
    requires = sorted(set(policy["required_grouping_fields"]))
    for required in requires:
        field = declared_fields.get(required)
        if field is None:
            resolution.report(
                call, DIAGNOSTIC_CODE_REQUIRED_GROUPING_FIELD_NOT_DECLARED,
                CONFIGURATION_OBJECT_KIND_GROUPING_FIELD, required,
                remediation_request=_remediation_request(
                    _DECLARE_GROUPING_FIELD, key=required))
            continue
        # The two below are fixed where the requirement is declared: a field's
        # scope never changes and nothing un-retires one, so what a tenant can
        # change is which fields this kind of work requires.
        if field["scope"] != _SCOPE_OF_A_START[altitude]:
            resolution.report(
                call, DIAGNOSTIC_CODE_REQUIRED_GROUPING_FIELD_WRONG_SCOPE,
                object_kind, key, field="required_grouping_fields")
            continue
        if field["retired"]:
            resolution.report(
                call, DIAGNOSTIC_CODE_REQUIRED_GROUPING_FIELD_RETIRED,
                object_kind, key, field="required_grouping_fields")
            continue
        call.add(
            _known(_GROUPING_FIELDS, required, _provenance(
                CONFIGURATION_OBJECT_KIND_GROUPING_FIELD, required)),
            # Required because this kind of work declares it — which is the
            # declaration the value's presence comes from.
            _runtime(token_names.name(_GROUPING_FIELDS, required),
                     call.parameters.named_for(required),
                     declared_by_the_kind))
    return {"kind": altitude, **policy, "required_grouping_fields": requires}


# ---------------------------------------------------------------------------
# A record: one Event Type, from what it last published
# ---------------------------------------------------------------------------

def _record_nothing_selected(resolution):
    call = _record_call(resolution)
    call.add(_unconfigured("event_type"))
    resolution.report(call, DIAGNOSTIC_CODE_EVENT_TYPE_NOT_SELECTED,
                      CONFIGURATION_OBJECT_KIND_EVENT_TYPE, None)


def _record_call(resolution):
    call = resolution.call(RECORD_USAGE, "customer_id", "idempotency_key",
                           "task_id")
    call.parameters.reserve(RESPONSE_PARAMETER, REPORTED_COST_PARAMETER)
    return call


def _record(resolution, key):
    """The call that records one Event Type. Returns what it resolved from,
    with the supplier beside it, or `None` where nothing could be.

    **Published by default.** The declaration is the one the Event Type last
    PUBLISHED, whatever has been edited since: a deployed integration was
    generated against a publication, and the draft is somebody's work in
    progress. What decides "nothing published" is the read answering `None` —
    never the revision count, which a row can carry with no publication left
    to read.

    A draft preview reads the draft instead, through the catalogue's own read
    for one, and claims no publication for what it resolves.
    """
    tenant = resolution.tenant
    call = _record_call(resolution)
    live = (EventType.objects.filter(tenant=tenant, key=key)
            .values("declaration_status", "provider__key").first())
    if live is None:
        call.add(_unconfigured("event_type"))
        resolution.report(
            call, DIAGNOSTIC_CODE_EVENT_TYPE_NOT_DECLARED,
            CONFIGURATION_OBJECT_KIND_EVENT_TYPE, key,
            remediation_request=_remediation_request(
                _DECLARE_EVENT_TYPE, key=key))
        return None

    if resolution.draft_preview:
        declaration, publication = draft_declaration(tenant=tenant,
                                                     key=key), None
    else:
        declaration = publication = last_published_declaration(tenant=tenant,
                                                               key=key)
    declared_by = _provenance(CONFIGURATION_OBJECT_KIND_EVENT_TYPE, key,
                              publication)
    # The key is the tenant's own declared word whether or not anything is
    # published under it. Everything BENEATH it is resolved from a
    # publication or not at all.
    call.add(_known("event_type", key, declared_by))
    publish = _remediation_request(_PUBLISH_EVENT_TYPE, key=key)
    if declaration is None:
        resolution.report(call, DIAGNOSTIC_CODE_EVENT_TYPE_NOT_PUBLISHED,
                          CONFIGURATION_OBJECT_KIND_EVENT_TYPE, key,
                          field="declaration_status",
                          remediation_request=publish)
        return None
    if (not resolution.draft_preview
            and live["declaration_status"] != DECLARATION_STATUS_PUBLISHED):
        resolution.report(
            call, DIAGNOSTIC_CODE_EVENT_TYPE_REVISED_SINCE_PUBLICATION,
            CONFIGURATION_OBJECT_KIND_EVENT_TYPE, key,
            field="declaration_status", remediation_request=publish)

    call.add(_known("event_type.costing_method", declaration.costing_method,
                    declared_by))
    # The supplier is not pinned by a publication — it may be corrected
    # without one — so it is the catalogue's current answer.
    supplier = live["provider__key"]
    if supplier:
        call.add(_known("provider", supplier, _provenance(
            CONFIGURATION_OBJECT_KIND_PROVIDER, supplier)))

    reads_the_response = _quantities(resolution, call, declaration,
                                     declared_by)
    reads_the_response |= _reported_cost(resolution, call, declaration,
                                         declared_by)
    if reads_the_response:
        _response_shape(resolution, call, declaration, declared_by)
    return {"declaration": declaration, "provider_key": supplier or None}


def _quantities(resolution, call, declaration, declared_by):
    """The tokens of each declared quantity. Returns whether any is read off
    the supplier's response."""
    key = declaration.key
    reads_the_response = False
    for quantity in declaration.measurements:
        member = token_names.name("measurements", quantity.code)

        def fact(element, code=quantity.code):
            return token_names.name("measurements", code, element)

        address = f"{key}:{quantity.code}"
        declare = _remediation_request(_DECLARE_MEASUREMENT, key=key,
                                       code=quantity.code)
        # The key's own token first, then everything named under it, with
        # nothing of another key between: that adjacency is what lets a
        # consumer pair them without the encoding.
        call.add(
            _known("measurements", quantity.code, declared_by),
            # What kind of number it is, what it counts and whether a cost
            # needs it — as published, which a revised Event Type's own route
            # no longer shows.
            _known(fact("value_type"), quantity.value_type, declared_by),
            _known(fact("unit"), quantity.unit, declared_by),
            _known(fact("required_for_costing"),
                   quantity.required_for_costing, declared_by))
        if quantity.source_kind == SOURCE_KIND_PROVIDER_RESPONSE:
            reads_the_response = True
            path = list(quantity.source_path)
            call.add(_runtime(member, RESPONSE_PARAMETER, declared_by),
                     _known(fact("source_path"), path, declared_by))
            if advisories(declaration.source_shape_id, path):
                resolution.report(
                    call, DIAGNOSTIC_CODE_SOURCE_PATH_CONVENTION_MISMATCH,
                    CONFIGURATION_OBJECT_KIND_MEASUREMENT, address,
                    field="source_path", remediation_request=declare)
        elif quantity.source_kind == SOURCE_KIND_CALLER_SUPPLIED:
            call.add(_runtime(member,
                              call.parameters.named_for(quantity.code),
                              declared_by))
        elif quantity.source_kind == SOURCE_KIND_CONSTANT:
            # A constant is declared with its value (#571), so the declaration
            # is complete — and this Code Builder version cannot yet generate
            # code that uses the value. So the value is NOT carried: the token
            # stays unconfigured, and the call is blocked by a code naming
            # exactly that, which the ticket that renders constants (#584)
            # removes. No remediation request, deliberately: the console words
            # one as the change an admin makes, and nothing in a valid
            # declaration is the thing to change.
            call.add(_unconfigured(member))
            resolution.report(
                call, DIAGNOSTIC_CODE_CONSTANT_MEASUREMENT_NOT_RENDERABLE,
                CONFIGURATION_OBJECT_KIND_MEASUREMENT, address,
                field="source_kind")
        elif quantity.source_kind == SOURCE_KIND_DERIVED:
            # Nothing designs how a derived quantity is computed, so no token
            # stands for its value at all.
            resolution.report(
                call, DIAGNOSTIC_CODE_DERIVED_MEASUREMENT_UNSUPPORTED,
                CONFIGURATION_OBJECT_KIND_MEASUREMENT, address,
                field="source_kind", remediation_request=declare)
        else:
            raise ValueError(
                f"{quantity.source_kind!r} is not a source kind this "
                f"resolution knows how to bind")
    return reads_the_response


def _reported_cost(resolution, call, declaration, declared_by):
    """The supplier's own cost figure, where the Event Type is costed from
    one. Returns whether it is read off the supplier's response."""
    if declaration.costing_method != COSTING_METHOD_REPORTED:
        return False
    key = declaration.key
    mapping = declaration.reported_cost_mapping
    declare = _remediation_request(_DECLARE_MAPPING, key=key)
    if mapping is None:
        resolution.report(
            call, DIAGNOSTIC_CODE_REPORTED_COST_MAPPING_MISSING,
            CONFIGURATION_OBJECT_KIND_REPORTED_COST_MAPPING, key,
            remediation_request=declare)
        return False
    if mapping.source_kind == SOURCE_KIND_PROVIDER_RESPONSE:
        # The mapping is valid platform configuration, and a cost read off the
        # supplier's response has a truthful request field of its own since
        # #570 (`provider_response_cost_micros`) — but this Code Builder
        # version cannot yet generate the read and the conversion, so the call
        # is blocked by a code naming exactly that, which the ticket that
        # renders the read (#583) removes. It fills no cost field rather than
        # the caller-supplied one, whose contract means the caller supplied the
        # figure. No remediation request, deliberately: the console words one
        # as the change an admin makes, and nothing in a valid declaration is
        # the thing to change (as for a constant's value, #571).
        resolution.report(
            call, DIAGNOSTIC_CODE_REPORTED_COST_PROVIDER_RESPONSE_NOT_RENDERABLE,
            CONFIGURATION_OBJECT_KIND_REPORTED_COST_MAPPING, key,
            field="source_kind")
        return True
    if mapping.source_kind != SOURCE_KIND_CALLER_SUPPLIED:
        raise ValueError(
            f"{mapping.source_kind!r} is not a source kind a reported cost "
            f"may be declared with")
    call.add(
        _runtime("provider_cost_micros", REPORTED_COST_PARAMETER, declared_by),
        _known("provider_cost_micros.amount_representation",
               mapping.amount_representation, declared_by))
    if mapping.currency:
        call.add(_known("currency", mapping.currency, declared_by))
    return False


def _response_shape(resolution, call, declaration, declared_by):
    """Which shape the declared paths are written against, what that shape
    is, and whether this target can read it. Asked only where something is
    read off the response."""
    key = declaration.key
    revise = _remediation_request(_REVISE_EVENT_TYPE, key=key)
    shape = declaration.source_shape_id
    if not shape:
        resolution.report(call, DIAGNOSTIC_CODE_RESPONSE_SHAPE_NOT_DECLARED,
                          CONFIGURATION_OBJECT_KIND_EVENT_TYPE, key,
                          field="source_shape_id", remediation_request=revise)
        return
    call.add(_known("event_type.source_shape_id", shape, declared_by))
    representation = SHAPE_REPRESENTATIONS.get(shape)
    if representation is not None:
        # UBB's fact about the shape rather than the tenant's about their
        # Event Type: a JSON document or a Python object, which is what
        # decides how a path is walked. Absent for a shape that declares
        # none, which is what the diagnostic below then says.
        call.add(_known("event_type.response_shape_representation",
                        representation, declared_by))
    if representation not in READABLE_REPRESENTATIONS[resolution.target]:
        resolution.report(
            call, DIAGNOSTIC_CODE_RESPONSE_SHAPE_NOT_READABLE_BY_TARGET,
            CONFIGURATION_OBJECT_KIND_EVENT_TYPE, key,
            field="source_shape_id", remediation_request=revise)


# ---------------------------------------------------------------------------
# What a later sandbox needs: the configuration beside the Blueprint
# ---------------------------------------------------------------------------

def _configuration(tenant, kinds, event_types, declared_fields):
    """Everything a sandbox must hold to run the Blueprint's lifecycle as this
    tenant's configuration would (#184 §13 step 2).

    Part of the identity and hashed with the Blueprint, so a fact no call
    spells — a window a kind declares, the rule that costs a quantity — still
    moves the fingerprint when it changes. Plain declared values only: no row
    id and no row timestamp, and every list whose order means nothing in a
    canonical order.

    ⚠ WHAT IS NOT HERE: the agreed price of a kind of work sold whole. Nothing
    declares one yet; the ticket that consumes that declaration adds it.
    """
    task, *subtasks = kinds
    declared_kinds = [kind for kind in kinds if kind is not None]
    required = sorted({key for kind in declared_kinds
                       for key in kind["required_grouping_fields"]
                       if key in declared_fields})
    codes = sorted({quantity.code for resolved in event_types
                    for quantity in resolved["declaration"].measurements})
    keys = sorted(resolved["declaration"].key for resolved in event_types)
    provisioned = copied_to_a_sandbox(tenant)
    return {
        "task_type": task,
        "subtask_types": [kind for kind in subtasks if kind is not None],
        "grouping_fields": [declared_fields[key] for key in required],
        "event_types": [_event_type_content(resolved)
                        for resolved in event_types],
        "cost_rates": _rules(
            CostBook.objects.filter(tenant=tenant), codes, keys,
            lambda book: {"key": book.key, "is_default": book.is_default,
                          "provider_key": book.provider_key,
                          "currency": book.currency}),
        # A Pricing Book may be one customer's own. Those are left out: a
        # sandbox runs the lifecycle for a customer of its own, who has none.
        "pricing_rules": _rules(
            PricingBook.objects.filter(tenant=tenant, customer__isnull=True),
            codes, keys,
            lambda book: {"key": book.key, "is_default": book.is_default}),
        "default_markup_micro_percent": (
            TenantDefaultMarkup.objects.filter(tenant=tenant)
            .values_list("markup_micro_percent", flat=True).first()),
        # What a sandbox is provisioned from, by the provisioning's own list:
        # an allowlist, so a column added to the tenant is not kept here by
        # default — and none of the three is a secret. The products are a set
        # the row happens to hold as a list, so they are put in order.
        "tenant": {**provisioned, "products": sorted(provisioned["products"])},
    }


def _event_type_content(resolved):
    declaration = resolved["declaration"]
    mapping = declaration.reported_cost_mapping
    return {
        "key": declaration.key,
        "costing_method": declaration.costing_method,
        "source_shape_id": declaration.source_shape_id,
        "source_shape_label": declaration.source_shape_label,
        "published_revision": declaration.published_revision,
        "published_at": declaration.published_at.isoformat(),
        "provider_key": resolved["provider_key"],
        "measurements": [_quantity_content(quantity)
                         for quantity in declaration.measurements],
        "reported_cost_mapping": (None if mapping is None else {
            **mapping._asdict(),
            "source_path": list(mapping.source_path),
            "currency_path": list(mapping.currency_path)}),
    }


#: What the published declaration holds that the configuration does NOT keep
#: yet. A constant's value is published with its declaration (#571), and this
#: Code Builder version does not render it: the call it belongs to is blocked
#: and its token unconfigured. So no value is kept beside the Blueprint either
#: — the ticket that renders a constant (#584) adds it to the token and to the
#: configuration in one commit, which is when the value itself joins what a
#: fingerprint hashes. (A changed value moves the fingerprint already, but only
#: by the republication it takes: the revision is hashed, the value is not.)
_NOT_KEPT_YET = frozenset({"constant_value"})


def _quantity_content(quantity):
    """One published quantity, as the configuration keeps it."""
    return {**{name: value for name, value in quantity._asdict().items()
               if name not in _NOT_KEPT_YET},
            "source_path": list(quantity.source_path)}


def _rules(books, codes, event_type_keys, book_content):
    """The tenant-wide rules in force, in each of `books`, that can cost or
    price a selected quantity.

    In force by the book service's own reading of a rule's window, so this
    and resolution cannot come to disagree about a rule opening or closing at
    the instant asked. A customer's own rule is left out for the reason their
    own book is, and a rule pinned to another Event Type because no selected
    call can match it.

    ⚠ The instant is NOW, so a rule scheduled to open or close moves the
    content — and the fingerprint — when its moment passes, with no write to
    configuration. That is the content being true of what is in force.
    """
    now = timezone.now()
    content = []
    for book in books:
        described = book_content(book)
        rules = (rules_in_force_at(book, now)
                 .filter(customer__isnull=True, measurement__code__in=codes)
                 .filter(Q(event_type="") | Q(event_type__in=event_type_keys))
                 .select_related("measurement"))
        content += [_rule_content(rule, described) for rule in rules]
    # Ordered by what each rule SAYS, never by the row it sits in: a set of
    # rules has no order of its own, and any column short of the whole rule
    # would leave two rules tied and their order to the row ids.
    content.sort(key=snapshots.canonical)
    return content


def _rule_content(rule, book):
    return {
        "book": book,
        "measurement_code": rule.measurement.code,
        "provider": rule.provider,
        "event_type": rule.event_type,
        "task_type": rule.task_type,
        "subtask_type": rule.subtask_type,
        "grouping_fields": {slot: getattr(rule, slot) for slot in SLOTS
                            if getattr(rule, slot)},
        "pricing_method": rule.pricing_method,
        "rate_structure": rule.rate_structure,
        "rate_per_unit_micros": rule.rate_per_unit_micros,
        "unit_quantity": rule.unit_quantity,
        "fixed_micros": rule.fixed_micros,
        "currency": rule.currency,
        "valid_from": rule.valid_from.isoformat(),
        "valid_to": rule.valid_to.isoformat() if rule.valid_to else None,
    }
