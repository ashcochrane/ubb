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
(#184 §2). Nothing here restates a registry fact as a second source of truth
(ADR-0006 §4): a literal carries the declaration it was read from, and a
reader who wants the declaration reads it from the route that owns it.

**It reads and it stores one thing.** For a resolution from PUBLISHED
configuration the caller keeps the content this returns, as an immutable
snapshot addressed by its own hash (`apps.platform.code_builder`). Nothing in
this module writes a row, and no path through it declares, edits or publishes
configuration or performs the request a diagnostic offers — for an admin
exactly as for anybody else.

HOW A TOKEN IS ADDRESSED
------------------------
An argument is ONE token, and its `name` says where on the call it sits:

* a published field of the call's request (`task_type`, `customer_id`), or the
  credential every call carries (`api_key`);
* for a field that is an object of declared keys (`grouping_fields`,
  `measurements`), TWO tokens per entry — the KEY, named for the field and
  carrying the declared key as its literal, and the VALUE under it, named
  `<field>.<key>`. A known key beside a runtime value is the ordinary case,
  and one token cannot be both;
* a declared element that says how a runtime value becomes the field's value,
  named for the value it qualifies and the declaration's own published field:
  `measurements.<key>.source_path` is the path a quantity is read by, and
  `provider_cost_micros.amount_representation` is what a supplied cost's
  number represents.

A published field name never contains a dot, so a consumer builds these names
from a key it already holds and never has to take one apart.

⚠ A literal is untyped JSON, so a closed concept's value travelling as one —
`amount_representation` does — carries no marker on the contract. It is the
declaration's own value, published and marked on the route that declares it.
"""
import keyword
from typing import NamedTuple
from urllib.parse import quote

from django.db.models import Q
from django.utils import timezone

from api.v1 import event_type_endpoints, metering_endpoints, task_endpoints
from api.v1.schemas import (
    EventTypeIn, EventTypeUpdateIn, MeasurementIn, ReportedCostMappingIn)
from apps.metering.pricing.models import Rate, TenantDefaultMarkup
from apps.platform.code_builder.withheld import (
    API_KEY, environment_variable, is_withheld)
from apps.platform.event_types.models import (
    REPORTED_COST_PARAMETER, EventType, Measurement, ReportedCostMapping)
from apps.platform.event_types.publication import (
    PublishedDeclaration, PublishedMeasurement, PublishedReportedCostMapping,
    last_published_declaration)
from apps.platform.event_types.source_paths import (
    REPRESENTATION_JSON, REPRESENTATION_PYTHON_OBJECT, SHAPE_REPRESENTATIONS,
    advisories)
from apps.platform.grouping_fields.models import SLOTS
from apps.platform.grouping_fields.queries import declared_grouping_fields
from apps.platform.tenants.services.sandbox_service import (
    COPIED_TO_A_SANDBOX)
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
    DIAGNOSTIC_CODE_CONSTANT_VALUE_NOT_DECLARED,
    DIAGNOSTIC_CODE_DERIVED_MEASUREMENT_UNSUPPORTED,
    DIAGNOSTIC_CODE_EVENT_TYPE_NOT_DECLARED,
    DIAGNOSTIC_CODE_EVENT_TYPE_NOT_PUBLISHED,
    DIAGNOSTIC_CODE_EVENT_TYPE_NOT_SELECTED,
    DIAGNOSTIC_CODE_EVENT_TYPE_REVISED_SINCE_PUBLICATION,
    DIAGNOSTIC_CODE_REPORTED_COST_MAPPING_MISSING,
    DIAGNOSTIC_CODE_REPORTED_COST_PROVIDER_RESPONSE_UNSUPPORTED,
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
SDK_MAJOR_VERSION = {CODE_TARGET_PYTHON_SDK: 3, CODE_TARGET_SHELL_HTTP: None}

#: Which response representations each target can read (owner item 6). A shell
#: file holds text, so it reads the JSON a web API returns and nothing else;
#: Python can hold either. A shape that declares no representation — a tenant's
#: own wrapper — is in neither set, so no target reads it until a renderer
#: defines how to traverse one.
READABLE_REPRESENTATIONS = {
    CODE_TARGET_PYTHON_SDK: frozenset({REPRESENTATION_JSON,
                                       REPRESENTATION_PYTHON_OBJECT}),
    CODE_TARGET_SHELL_HTTP: frozenset({REPRESENTATION_JSON}),
}

#: Where, in the content kept under a fingerprint, the Blueprint itself is —
#: beside the selection it answers and the configuration it was resolved
#: from. Named because the route that reads one back reads it by this.
BLUEPRINT = "blueprint"

#: How many Event Types, and how many Subtask kinds, one selection may name.
#: The resolution is a READ-floor call that reads several rows per name, so
#: the bound is what keeps an expensive read safe at that floor.
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
    # Lifted by the ticket that consumes a truthful transport for a cost read
    # off a supplier's response; the member leaves the registry with it.
    DIAGNOSTIC_CODE_REPORTED_COST_PROVIDER_RESPONSE_UNSUPPORTED: _BLOCKING,
    DIAGNOSTIC_CODE_CONSTANT_VALUE_NOT_DECLARED: _BLOCKING,
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

#: The parameter a quantity or a cost read off the supplier's response is read
#: FROM: the response object itself, which only the tenant's code ever holds.
RESPONSE_PARAMETER = "response"


# ---------------------------------------------------------------------------
# The operations a Blueprint names
# ---------------------------------------------------------------------------

def _operation_id(view):
    """The operationId the contract publishes for a route's handler.

    Read off the handler rather than spelled, so a renamed handler moves the
    name here with it. The contract test holds every one of these to
    `openapi/v1.json`, which is what makes it a real operation rather than a
    string that happens to look like one.
    """
    return f"{view.__module__.replace('.', '_')}_{view.__name__}"


START_TASK = _operation_id(task_endpoints.start_task)
RECORD_USAGE = _operation_id(metering_endpoints.record_usage)
CLOSE_TASK = _operation_id(task_endpoints.close_task)


class _Remediation(NamedTuple):
    """One request a diagnostic may offer: the operation, and its body's shape."""
    view: object
    method: str
    #: The published path, with the object's key as its only parameters.
    path: str
    #: The body's published fields, or `None` for an operation taking no body.
    fields: tuple | None


def _fields_of(schema):
    return tuple(schema.model_fields)


_DECLARE_EVENT_TYPE = _Remediation(
    event_type_endpoints.declare_event_type, "POST",
    "/api/v1/event-types", _fields_of(EventTypeIn))
_REVISE_EVENT_TYPE = _Remediation(
    event_type_endpoints.revise_event_type, "PATCH",
    "/api/v1/event-types/{key}", _fields_of(EventTypeUpdateIn))
_PUBLISH_EVENT_TYPE = _Remediation(
    event_type_endpoints.publish_event_type, "POST",
    "/api/v1/event-types/{key}/publish", None)
_DECLARE_MEASUREMENT = _Remediation(
    event_type_endpoints.declare_measurement, "PUT",
    "/api/v1/event-types/{key}/measurements/{code}",
    _fields_of(MeasurementIn))
_DECLARE_MAPPING = _Remediation(
    event_type_endpoints.declare_reported_cost_mapping, "PUT",
    "/api/v1/event-types/{key}/reported-cost-mapping",
    _fields_of(ReportedCostMappingIn))
#: The Grouping Field registry takes a list of declarations under one field.
#: Its row is spelled here rather than read off the route's request schema,
#: which a later rename moves: a Blueprint binds to the published field names
#: and to no schema of that registry.
_GROUPING_FIELDS = "grouping_fields"
_GROUPING_FIELD_ROW = ("key", "slot", "scope", "max_cardinality")
_DECLARE_GROUPING_FIELD = _Remediation(
    metering_endpoints.declare_grouping_fields, "PUT",
    "/api/v1/metering/grouping-fields", (_GROUPING_FIELDS,))


def _remediation_request(remediation, *, body_key=None, **route_keys):
    """The request that fixes a diagnostic, ready to copy and never performed.

    It names the object by its key and nothing else of the tenant's: the route
    carries the key, and the body is the operation's published fields with
    every value left empty. No secret is reachable from here — the function is
    handed keys and field names.
    """
    body = None
    if remediation.fields is not None:
        body = {field: None for field in remediation.fields}
        if remediation is _DECLARE_GROUPING_FIELD:
            row = {field: None for field in _GROUPING_FIELD_ROW}
            row["key"] = body_key
            body = {_GROUPING_FIELDS: [row]}
        elif body_key is not None:
            body["key"] = body_key
    return {
        "method": remediation.method,
        "route": remediation.path.format(**{
            name: quote(value, safe="") for name, value in route_keys.items()}),
        "operation_id": _operation_id(remediation.view),
        "body": body,
    }


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

#: A value this resolution could not produce. Distinct from `None`, which is a
#: literal a declaration may legitimately hold.
_NOT_RESOLVED = object()


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


def _provenance(object_kind, key, published=None):
    """Which declaration a value was read from.

    An Event Type's facts also say which publication, in the names the Event
    Type's own route serves. A kind of work and a Grouping Field have no
    publish record, so they carry neither — a held file is told from a
    current one by the fingerprint (ADR-0012).
    """
    return {
        "object_kind": object_kind, "key": key,
        "published_revision": (published.published_revision
                               if published else None),
        "published_at": (published.published_at.isoformat()
                         if published and published.published_at else None),
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


def _refuse_the_selection(target, event_types, subtask_types):
    """What a selection may not be. The marker on the contract is applied when
    the document is exported and refuses nothing here, so the request-side
    value set is held in code."""
    if target not in CODE_TARGET_VALUES:
        raise Problem(
            "validation_error",
            f"{target!r} is not a target: the targets are "
            f"{', '.join(sorted(CODE_TARGET_VALUES))}")
    for name, selected in (("event_types", event_types),
                           ("subtask_types", subtask_types)):
        if len(selected) > MAXIMUM_SELECTED:
            raise Problem(
                "validation_error",
                f"{name} names {len(selected)} entries; one selection may "
                f"name at most {MAXIMUM_SELECTED}")


def resolve(tenant, *, target, task_type=None, event_types=(),
            subtask_types=(), draft_preview=False):
    """The Blueprint for one selection, and the content to keep for it.

    Returns `(document, content)`. `document` is the Blueprint without its
    fingerprint — the fingerprint is the hash of `content`, which contains the
    document, so it cannot also be inside it. `content` is `None` for a draft
    preview: a preview is not resolved from published configuration, so there
    is nothing it may be stored or verified as.

    A selection is a SET. The Event Types and the Subtask kinds are resolved
    in key order whatever order they were sent in, so one integration has one
    fingerprint.
    """
    _refuse_the_selection(target, event_types, subtask_types)
    event_types = sorted(set(event_types))
    subtask_types = sorted(set(subtask_types))
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
        return document, None

    declared = [declaration for declaration in resolved_event_types
                if declaration is not None]
    content = {
        "selection": {"target": target, "task_type": task_type,
                      "event_types": event_types,
                      "subtask_types": subtask_types},
        BLUEPRINT: document,
        "configuration": _configuration(tenant, kinds, declared,
                                        declared_fields),
    }
    return document, content


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

    kind_provenance = _provenance(object_kind, key)
    call.add(_known("task_type", key, kind_provenance))
    if policy["retired"]:
        resolution.report(call, DIAGNOSTIC_CODE_TASK_TYPE_RETIRED,
                          object_kind, key, field="retired")

    for required in policy["required_grouping_fields"]:
        field = declared_fields.get(required)
        if field is None:
            resolution.report(
                call, DIAGNOSTIC_CODE_REQUIRED_GROUPING_FIELD_NOT_DECLARED,
                CONFIGURATION_OBJECT_KIND_GROUPING_FIELD, required,
                remediation_request=_remediation_request(
                    _DECLARE_GROUPING_FIELD, body_key=required))
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
            _runtime(f"{_GROUPING_FIELDS}.{required}",
                     call.parameters.named_for(required), kind_provenance))
    return {"kind": altitude, **policy}


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


def _the_draft(tenant, key):
    """An Event Type's LIVE declaration, in the shape a publication is read in.

    The draft preview's read. The published read never answers with a draft,
    so a preview reads the rows itself — and claims no publication for them:
    the revision and its date are left empty rather than borrowed from a
    publication that said something else.
    """
    event_type = EventType.objects.filter(tenant=tenant, key=key).first()
    if event_type is None:
        return None
    mapping = (ReportedCostMapping.objects.filter(event_type=event_type)
               .values(*ReportedCostMapping.PINNED).first())
    return PublishedDeclaration(
        **{name: getattr(event_type, name) for name in EventType.PINNED},
        published_revision=None, published_at=None,
        measurements=tuple(
            PublishedMeasurement(**{**declared, "source_path": tuple(
                declared["source_path"])})
            for declared in Measurement.objects.filter(event_type=event_type)
            .order_by("code").values(*Measurement.PINNED)),
        reported_cost_mapping=(None if mapping is None else
                               PublishedReportedCostMapping(**{
                                   **mapping,
                                   "source_path": tuple(mapping["source_path"]),
                                   "currency_path": tuple(
                                       mapping["currency_path"])})))


def _record(resolution, key):
    """The call that records one Event Type. Returns what it resolved from,
    with the supplier beside it, or `None` where nothing could be.

    **Published by default.** The declaration is the one the Event Type last
    PUBLISHED, whatever has been edited since: a deployed integration was
    generated against a publication, and the draft is somebody's work in
    progress. What decides "nothing published" is the read answering `None` —
    never the revision count, which a row can carry with no publication left
    to read.
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
                _DECLARE_EVENT_TYPE, body_key=key))
        return None

    declaration = (_the_draft(tenant, key) if resolution.draft_preview
                   else last_published_declaration(tenant=tenant, key=key))
    published = None if resolution.draft_preview else declaration
    provenance = _provenance(CONFIGURATION_OBJECT_KIND_EVENT_TYPE, key,
                             published)
    call.add(_known("event_type", key, provenance))
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

    # The supplier is not pinned by a publication — it may be corrected
    # without one — so it is the catalogue's current answer.
    supplier = live["provider__key"]
    if supplier:
        call.add(_known("provider", supplier, _provenance(
            CONFIGURATION_OBJECT_KIND_PROVIDER, supplier)))

    reads_the_response = _quantities(resolution, call, declaration, provenance)
    reads_the_response |= _reported_cost(resolution, call, declaration,
                                         provenance)
    if reads_the_response:
        _response_shape(resolution, call, declaration)
    return {"declaration": declaration, "provider_key": supplier or None,
            "published": published}


def _quantities(resolution, call, declaration, provenance):
    """A token pair per declared quantity. Returns whether any is read off
    the supplier's response."""
    key = declaration.key
    reads_the_response = False
    for quantity in declaration.measurements:
        member = f"measurements.{quantity.code}"
        address = f"{key}:{quantity.code}"
        declare = _remediation_request(_DECLARE_MEASUREMENT, key=key,
                                       code=quantity.code)
        call.add(_known("measurements", quantity.code, provenance))
        if quantity.source_kind == SOURCE_KIND_PROVIDER_RESPONSE:
            reads_the_response = True
            path = list(quantity.source_path)
            call.add(_runtime(member, RESPONSE_PARAMETER, provenance),
                     _known(f"{member}.source_path", path, provenance))
            if advisories(declaration.source_shape_id, path):
                resolution.report(
                    call, DIAGNOSTIC_CODE_SOURCE_PATH_CONVENTION_MISMATCH,
                    CONFIGURATION_OBJECT_KIND_MEASUREMENT, address,
                    field="source_path", remediation_request=declare)
        elif quantity.source_kind == SOURCE_KIND_CALLER_SUPPLIED:
            call.add(_runtime(member,
                              call.parameters.named_for(quantity.code),
                              provenance))
        elif quantity.source_kind == SOURCE_KIND_CONSTANT:
            # A constant's value has nowhere to be declared yet, so there is
            # none to carry — and one is never made up.
            call.add(_unconfigured(member))
            resolution.report(
                call, DIAGNOSTIC_CODE_CONSTANT_VALUE_NOT_DECLARED,
                CONFIGURATION_OBJECT_KIND_MEASUREMENT, address,
                field="source_kind", remediation_request=declare)
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


def _reported_cost(resolution, call, declaration, provenance):
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
    if mapping.source_kind != SOURCE_KIND_CALLER_SUPPLIED:
        # A cost read off the supplier's response has no truthful request
        # field: the one that exists means the caller supplied the figure. So
        # the call fills none, rather than the wrong one.
        resolution.report(
            call, DIAGNOSTIC_CODE_REPORTED_COST_PROVIDER_RESPONSE_UNSUPPORTED,
            CONFIGURATION_OBJECT_KIND_REPORTED_COST_MAPPING, key,
            field="source_kind", remediation_request=declare)
        return mapping.source_kind == SOURCE_KIND_PROVIDER_RESPONSE
    call.add(
        _runtime("provider_cost_micros", REPORTED_COST_PARAMETER, provenance),
        _known("provider_cost_micros.amount_representation",
               mapping.amount_representation, provenance))
    if mapping.currency:
        call.add(_known("currency", mapping.currency, provenance))
    return False


def _response_shape(resolution, call, declaration):
    """Whether this target can read the shape the declared paths are written
    against. Asked only where something is read off the response."""
    key = declaration.key
    revise = _remediation_request(_REVISE_EVENT_TYPE, key=key)
    shape = declaration.source_shape_id
    if not shape:
        resolution.report(call, DIAGNOSTIC_CODE_RESPONSE_SHAPE_NOT_DECLARED,
                          CONFIGURATION_OBJECT_KIND_EVENT_TYPE, key,
                          field="source_shape_id", remediation_request=revise)
        return
    representation = SHAPE_REPRESENTATIONS.get(shape)
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

    Kept beside the Blueprint and hashed with it, so a fact no call spells —
    the ceiling a kind declares, the rule that costs a quantity — still moves
    the fingerprint when it changes.

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
    return {
        "task_type": task,
        "subtask_types": [kind for kind in subtasks if kind is not None],
        "grouping_fields": [declared_fields[key] for key in required],
        "event_types": [_event_type_content(resolved)
                        for resolved in event_types],
        "cost_rates": _rules(tenant, codes, keys, book="cost_book"),
        "pricing_rules": _rules(tenant, codes, keys, book="pricing_book"),
        "default_markup_micro_percent": (
            TenantDefaultMarkup.objects.filter(tenant=tenant)
            .values_list("markup_micro_percent", flat=True).first()),
        # What a sandbox is provisioned from, by the provisioning's own list:
        # an allowlist, so a column added to the tenant is not kept here by
        # default — and none of the three is a secret.
        "tenant": {field: getattr(tenant, field)
                   for field in COPIED_TO_A_SANDBOX},
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
        "measurements": [
            {**quantity._asdict(), "source_path": list(quantity.source_path)}
            for quantity in declaration.measurements],
        "reported_cost_mapping": (None if mapping is None else {
            **mapping._asdict(),
            "source_path": list(mapping.source_path),
            "currency_path": list(mapping.currency_path)}),
    }


def _rules(tenant, codes, event_type_keys, *, book):
    """The tenant-wide rules in force that can cost, or price, a selected
    quantity — the ones in a cost book, or the ones in a Pricing Book.

    A customer's own rules are left out: a sandbox runs the lifecycle for a
    customer of its own, who has none. A rule pinned to another Event Type is
    left out because no selected call can match it.
    """
    now = timezone.now()
    # A Pricing Book may be one customer's own; a cost book never is.
    tenant_wide = ({"pricing_book__customer__isnull": True}
                   if book == "pricing_book" else {})
    rules = (Rate.objects
             .filter(tenant=tenant, customer__isnull=True,
                     measurement__code__in=codes, valid_from__lte=now,
                     **{f"{book}__isnull": False}, **tenant_wide)
             .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=now))
             .filter(Q(event_type="") | Q(event_type__in=event_type_keys))
             .select_related(book, "measurement")
             .order_by(f"{book}__key", "measurement__code", "provider",
                       "event_type", "task_type", "subtask_type",
                       "valid_from", "id"))
    return [_rule_content(rule, getattr(rule, book)) for rule in rules]


def _rule_content(rule, book):
    return {
        "book": {"key": book.key, "is_default": book.is_default,
                 # A cost book names its supplier and its currency; a Pricing
                 # Book names neither.
                 "provider_key": getattr(book, "provider_key", None),
                 "currency": getattr(book, "currency", None)},
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
