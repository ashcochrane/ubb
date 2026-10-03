"""Verifying a stored Integration Blueprint: does the configuration a
generated file was stamped with actually record and cost? (#580, #184 §13.)

A generated file carries a `configuration_fingerprint`, which names the
snapshot kept when its Blueprint was resolved (ADR-0015). Verifying it runs, in
this order:

(a) **Load** the snapshot. A fingerprint nobody resolved, one that was pruned
    and another tenant's are all the ordinary not-found, before anything else.
(b) **Refuse an Event Type the snapshot does not publish** (#567), before
    anything is written. The check reads the snapshot's published content and
    never the live catalogue: an Event Type that was undeclared or still a
    draft when the Blueprint was resolved, or that the Blueprint never
    selected, is unavailable whatever has happened to it since. Only a
    COMPLETE Blueprint runs at all — a scaffold or a blocked one generates a
    file that fails fast rather than records, so there is nothing to verify.
(c) **Materialise** the snapshot's configuration in a tenant made for the
    run, then start the unit of work, start each Subtask a recording asks
    for, record each claimed Event Type with the request's sample values and
    send each recording a second time with the same key, then close.
(d) **Answer** every acknowledgement, and a verdict read off them. The
    verdict is about the WHOLE Blueprint and about recording and costing: it
    is true only when every Event Type and Subtask kind the Blueprint selected
    was exercised, no call was refused, and every recording carried what its
    cost needs and was costed. It does not judge a customer price, which each
    acknowledgement's `pricing_status` reports. A run that exercises less is
    allowed, and says what it left out.
(e) **Discard** everything (c) wrote.

WHERE IT RUNS, AND HOW IT IS DISCARDED
--------------------------------------
In a tenant that exists only inside one database transaction, which is rolled
back when the run ends — whether it passed, failed or raised. Nothing the run
wrote is ever committed, so there is nothing to delete afterwards and no
moment at which another connection can see it. Effects that wait for a commit
never happen: outbox delivery, the kill of a unit of work that crossed its
ceiling, anything sent to Stripe. The acknowledgements still say what each
recording decided, which is what is being verified.

Two alternatives were measured and refused. The tenant's sandbox holds the
developer's own configuration, and there is one per tenant, so running there
would mix the two and discarding would take theirs. A separate tenant that is
committed and then removed has to get past every `PROTECT` edge its rows hold
(a supplier under an Event Type, a declared quantity a rule prices, a rule's
book), its
outbox rows would be committed and delivered, and a process that died in the
middle would leave it behind. The rollback has none of those.

What can leave the database at all is decided by the tenant made for the run.
Beside a name, it is given only the three fields a sandbox copies, so its
spend enforcement is off and it declares no admission bound: neither the live
counter nor the admission window is touched, and
`test_verifying_a_blueprint.py` holds both by watching them. No API key is
minted for it. (Saving a tenant also deletes its cached product list, a key
nothing has written for a tenant that did not exist a moment before.)

WHAT IS SUPPLIED THAT THE SNAPSHOT DOES NOT HOLD
------------------------------------------------
The snapshot was shaped to be hashed, not replayed, and nothing is added to it
here: adding to it would move every fingerprint. So the run supplies, and its
answer states, two things — a customer to record for, and the moment the
stored rules take effect (the run's own start, so each is in force for the run
whatever window it was declared with). A display name, an analytics heading
and an event category are not held and not needed: none decides a cost or a
price.

**IT NEVER MAKES UP A RUNTIME VALUE** (owner's review of #599). A value a
tenant's code passes at run time — a Measurement's, a required Grouping
Field's — is a SAMPLE the request carries, exactly as the Blueprint calls it
`runtime_bound`. A required Grouping Field the request gives no value for is
refused before anything is written, never filled in: an invented value can
match no rule pinned to a real one, and the verdict would then report a gap
the configuration does not have.

**THE CUSTOMER IS SYNTHESISED BECAUSE WHO IT IS CANNOT MOVE A COST.** The
run's customer is a new one, on no plan, with no override. That is safe for
what the verdict proves: no cost rule names a customer (a cost book has no
customer column, and no rule selector is a customer), and the snapshot holds
only tenant-wide rules — a customer's own pricing book is left out of it by
the resolver (`integration_blueprint._configuration`). What a customer's
identity CAN move is a customer price, through a plan's book or an override,
and the verdict does not judge price: the acknowledgements' `pricing_status`
reports it, and it is the price of a customer on no plan and no deal.

THE UNIT OF WORK'S OUTCOME
--------------------------
The server ran the work itself, so it holds the evidence a declaration needs.
A run that reaches its close declares `delivered` — every recording was made,
including one whose cost UBB could not work out, because an uncosted
recording is still delivered work. A run stopped by a refused call after the
Task started declares `cancelled` on it: the run withdrew the rest of the work,
and closing the Task withdraws any Subtask inside it. A refused start leaves no
Task to declare anything on. If that cancelling close is itself refused, the
Task is left as it is and `refusal` still names the call that stopped the run.
Pass and fail is the verdict's, never the outcome's.
"""
import json

from django.db import transaction
from django.utils import timezone

from api.v1 import (
    integration_blueprint, metering_endpoints, task_endpoints,
    task_type_endpoints)
from api.v1.schemas import (
    CloseTaskRequest, RecordUsageRequest, StartTaskRequest, TaskTypeIn,
    TaskTypeRegistryIn)
from apps.metering.pricing.models import (
    CHANGE_ADD, CostBook, PricingBook, TenantDefaultMarkup)
from apps.metering.pricing.services.book_service import BookService
from apps.platform.code_builder import snapshots
from apps.platform.customers.models import Customer
from apps.platform.event_types.models import (
    EventType, Measurement, Provider, ReportedCostMapping)
from apps.platform.grouping_fields.services import DimensionService
from apps.platform.tenants.models import Tenant
from core.problems import PROBLEM_TYPE_BASE, Problem
from core.vocabulary import (
    COSTING_METHOD_REPORTED, COSTING_STATUS_UNRESOLVED,
    INTEGRATION_READINESS_COMPLETE,
    TASK_OUTCOME_CANCELLED, TASK_OUTCOME_DELIVERED)

#: The external id of the customer the run records for — the one value the run
#: makes up, and one that decides no cost (see the module docstring).
VERIFICATION_CUSTOMER = "ubb-verification"

#: The fields of a declared kind of work that the registry takes back, by the
#: names its own request publishes. The snapshot keeps each kind as the
#: registry's read answers it, which holds every one of them.
_KIND_FIELDS = tuple(TaskTypeIn.model_fields)

#: The operation each call of the run is, as the Blueprint names it.
START = integration_blueprint.START_TASK
RECORD = integration_blueprint.RECORD_USAGE
CLOSE = integration_blueprint.CLOSE_TASK


def verify(tenant, configuration_fingerprint, payload):
    """Verify the snapshot `tenant` keeps under `configuration_fingerprint`,
    with the recordings `payload` claims. The answer, or a refusal."""
    content = snapshots.stored(
        tenant=tenant, configuration_fingerprint=configuration_fingerprint)
    if content is None:
        raise Problem(
            "not_found",
            f"no blueprint is stored under '{configuration_fingerprint}'")
    identity = content[snapshots.IDENTITY]
    configuration = identity["configuration"]
    _refuse_what_the_snapshot_does_not_publish(configuration, payload)
    readiness = identity[integration_blueprint.BLUEPRINT]["readiness"]
    if readiness != INTEGRATION_READINESS_COMPLETE:
        raise Problem(
            "conflict",
            f"the Blueprint stored under '{configuration_fingerprint}' is "
            f"{readiness}, and only a {INTEGRATION_READINESS_COMPLETE} one "
            f"generates code that records: resolve it again once its "
            f"diagnostics are fixed")
    _refuse_a_subtask_kind_not_selected(configuration, payload)
    _refuse_grouping_values_that_do_not_match(configuration, payload)

    with transaction.atomic():
        answer = _Run(configuration, payload).run()
        # (e): whatever the run wrote goes with the transaction it wrote in.
        transaction.set_rollback(True)
    return {"configuration_fingerprint": configuration_fingerprint, **answer}


def _refuse_what_the_snapshot_does_not_publish(configuration, payload):
    """#567. The snapshot holds an Event Type's content only where the
    Blueprint resolved it from a publication, so "in the snapshot's
    configuration" and "published in the configuration being verified" are
    one question."""
    published = {declared["key"] for declared in configuration["event_types"]}
    unavailable = list(dict.fromkeys(
        claim.event_type for claim in payload.records
        if claim.event_type not in published))
    if unavailable:
        raise Problem(
            "event_type_not_available",
            f"the configuration being verified does not publish "
            f"{', '.join(repr(key) for key in unavailable)}: an Event Type "
            f"is available to a verification only if the Blueprint selected "
            f"it and resolved it from a publication",
            extensions={"event_types": unavailable})


def _refuse_a_subtask_kind_not_selected(configuration, payload):
    selected = {kind["key"] for kind in configuration["subtask_types"]}
    named = list(dict.fromkeys(
        claim.subtask_type for claim in payload.records
        if claim.subtask_type is not None
        and claim.subtask_type not in selected))
    if named:
        raise Problem(
            "validation_error",
            f"subtask_type {', '.join(repr(key) for key in named)} is not a "
            f"Subtask kind the Blueprint selected")


def _refuse_grouping_values_that_do_not_match(configuration, payload):
    """Every Grouping Field a started kind requires has a sample value, and
    no value is given for a field no selected kind requires.

    A missing value is refused rather than made up: it is runtime-bound, so
    only the tenant's code holds it. A value nobody requires would be sent
    nowhere, so a caller is told rather than left believing it was used.
    """
    selected = (configuration["task_type"], *configuration["subtask_types"])
    required_anywhere = {key for kind in selected
                         for key in kind["required_grouping_fields"]}
    unwanted = sorted(set(payload.grouping_fields) - required_anywhere)
    if unwanted:
        raise Problem(
            "validation_error",
            f"grouping_fields {', '.join(repr(key) for key in unwanted)}: no "
            f"kind of work the Blueprint selected requires it")
    # A kind is its altitude and its key together: a Task kind and a Subtask
    # kind may share a key.
    task = configuration["task_type"]
    started = [task, *(kind for kind in configuration["subtask_types"]
                       if kind["key"] in {claim.subtask_type
                                          for claim in payload.records})]
    missing = sorted({key for kind in started
                      for key in kind["required_grouping_fields"]}
                     - set(payload.grouping_fields))
    if missing:
        raise Problem(
            "validation_error",
            f"grouping_fields must give a sample value for "
            f"{', '.join(repr(key) for key in missing)}: the kind of work "
            f"this run starts requires it, and a value a tenant's code "
            f"passes at run time is never made up")


class _Refused(Exception):
    """A call of the run answered with a refusal: the run stops there."""


class _Run:
    """One verification run, inside the transaction that is thrown away."""

    def __init__(self, configuration, payload):
        self.configuration = configuration
        self.payload = payload
        self.at = timezone.now()
        self.refusal = None

    # -- (c) materialise ---------------------------------------------------

    def _materialise(self):
        held = self.configuration
        tenant = Tenant.objects.create(name="Code Builder verification",
                                       **held["tenant"])
        for field in held["grouping_fields"]:
            DimensionService.declare(
                tenant, key=field["key"], slot=field["slot"],
                scope=field["scope"],
                max_cardinality=field["max_cardinality"])
        kinds = [held["task_type"], *held["subtask_types"]]
        task_type_endpoints.declare_kinds(tenant, TaskTypeRegistryIn(
            task_types=[TaskTypeIn(**{name: kind[name]
                                      for name in _KIND_FIELDS})
                        for kind in kinds]))
        # Each supplier once, however many Event Types name it.
        suppliers = {key: _saved(Provider(tenant=tenant, key=key))
                     for key in sorted({declared["provider_key"]
                                        for declared in held["event_types"]
                                        if declared["provider_key"]})}
        for declared in held["event_types"]:
            _declare_and_publish(tenant, declared,
                                 suppliers.get(declared["provider_key"]))
        self._books(tenant, held["cost_rates"], _a_cost_book)
        self._books(tenant, held["pricing_rules"], _a_pricing_book)
        if held["default_markup_micro_percent"] is not None:
            TenantDefaultMarkup.objects.create(
                tenant=tenant,
                markup_micro_percent=held["default_markup_micro_percent"])
        customer = Customer.objects.create(tenant=tenant,
                                           external_id=VERIFICATION_CUSTOMER)
        return tenant, customer

    def _books(self, tenant, rules, a_book):
        """Every stored rule, in the book it was stored with, published to
        take effect at the run's start."""
        by_book = {}
        for rule in rules:
            by_book.setdefault(json.dumps(rule["book"], sort_keys=True),
                               []).append(rule)
        for described, held in by_book.items():
            book = a_book(tenant, json.loads(described))
            draft = BookService.declare(
                book, [_the_change_that_adds(rule) for rule in held],
                effective_at=self.at)
            BookService.publish_declared(draft)

    # -- (c) run -----------------------------------------------------------

    def _call(self, operation_id, function, *arguments):
        """One call of the lifecycle, in a savepoint of its own so that a
        refusal leaves the run's transaction usable for what follows it."""
        try:
            with transaction.atomic():
                return function(*arguments)
        except Problem as refused:
            # The FIRST refusal is the one that stopped the run; a refusal of
            # the close that withdraws the work afterwards does not replace it.
            if self.refusal is None:
                self.refusal = {"operation_id": operation_id, "problem": {
                    "type": PROBLEM_TYPE_BASE + refused.code,
                    "title": refused.title, "status": refused.status,
                    "code": refused.code, "detail": refused.detail}}
            raise _Refused from refused

    def _values_for(self, kind):
        """The request's sample for each Grouping Field `kind` requires.
        Every one is there: `verify` refused the request otherwise."""
        return {key: self.payload.grouping_fields[key]
                for key in kind["required_grouping_fields"]}

    def _start(self, tenant, customer, kind, idempotency_key, parent=None):
        return self._call(START, task_endpoints.start, tenant,
                          StartTaskRequest(
                              customer_id=customer.id,
                              idempotency_key=idempotency_key,
                              parent_task_id=parent, task_type=kind["key"],
                              grouping_fields=self._values_for(kind)))

    def _close(self, tenant, started, outcome):
        return self._call(CLOSE, task_endpoints.close, tenant,
                          started["task_id"], CloseTaskRequest(outcome=outcome))

    def run(self):
        tenant, customer = self._materialise()
        held = self.configuration
        subtask_kinds = {kind["key"]: kind for kind in held["subtask_types"]}
        event_types = {declared["key"]: declared
                       for declared in held["event_types"]}
        task_kind = held["task_type"]
        task = {"start": None, "close": None}
        subtasks = {}
        records = []
        try:
            task["start"] = self._start(tenant, customer, task_kind,
                                        "ubb-verification-task")
            for position, claim in enumerate(self.payload.records):
                unit = task
                if claim.subtask_type is not None:
                    unit = subtasks.get(claim.subtask_type)
                    if unit is None:
                        unit = subtasks[claim.subtask_type] = {
                            "start": None, "close": None}
                        unit["start"] = self._start(
                            tenant, customer, subtask_kinds[claim.subtask_type],
                            f"ubb-verification-subtask-{claim.subtask_type}",
                            parent=task["start"]["task_id"])
                record = {"event_type": claim.event_type,
                          "subtask_type": claim.subtask_type,
                          "acknowledgement": None, "replay": None}
                records.append(record)
                recording = _recording(
                    customer, event_types[claim.event_type], claim,
                    unit["start"]["task_id"], position)
                record["acknowledgement"] = self._call(
                    RECORD, metering_endpoints.record, tenant, recording)
                record["replay"] = self._call(
                    RECORD, metering_endpoints.record, tenant, recording)
            for unit in subtasks.values():
                unit["close"] = self._close(tenant, unit["start"],
                                            TASK_OUTCOME_DELIVERED)
            task["close"] = self._close(tenant, task["start"],
                                        TASK_OUTCOME_DELIVERED)
        except _Refused:
            if task["start"] is not None and task["close"] is None:
                # Closing the Task withdraws whatever runs inside it.
                try:
                    task["close"] = self._close(tenant, task["start"],
                                                TASK_OUTCOME_CANCELLED)
                except _Refused:
                    pass

        for record in records:
            _read(record, event_types[record["event_type"]])
        # WHAT THE RUN DID NOT EXERCISE. `verified` is a statement about the
        # whole Blueprint, so a selected Event Type or Subtask kind no
        # recording reached keeps it false, however well the rest went
        # (owner's review of #599).
        unexercised_event_types = sorted(
            set(event_types) - {claim.event_type
                                for claim in self.payload.records})
        unexercised_subtask_types = sorted(set(subtask_kinds) - set(subtasks))
        return {
            "verified": (self.refusal is None
                         and not unexercised_event_types
                         and not unexercised_subtask_types
                         and all(record["complete"] for record in records)),
            "unexercised_event_types": unexercised_event_types,
            "unexercised_subtask_types": unexercised_subtask_types,
            "environment": {
                "discarded": True,
                "customer_external_id": VERIFICATION_CUSTOMER,
                "rules_effective_at": self.at,
            },
            "task": {"task_type": task_kind["key"], **task},
            "subtasks": [{"task_type": key, **unit}
                         for key, unit in subtasks.items()],
            "records": records,
            "refusal": self.refusal,
        }


# ---------------------------------------------------------------------------
# Materialising, through each record's own writer
# ---------------------------------------------------------------------------

def _saved(record):
    """Validated as the catalogue's routes validate it, then saved."""
    record.full_clean()
    record.save()
    return record


def _declare_and_publish(tenant, declared, provider):
    """One Event Type, from its stored publication, published again, naming
    `provider` — the supplier already declared for the run, or none."""
    event_type = _saved(EventType(
        tenant=tenant, key=declared["key"],
        costing_method=declared["costing_method"], provider=provider,
        source_shape_id=declared["source_shape_id"],
        source_shape_label=declared["source_shape_label"]))
    for quantity in declared["measurements"]:
        _saved(Measurement(
            event_type=event_type, code=quantity["code"],
            value_type=quantity["value_type"], unit=quantity["unit"],
            required_for_costing=quantity["required_for_costing"],
            source_kind=quantity["source_kind"],
            source_path=quantity["source_path"]))
    mapping = declared["reported_cost_mapping"]
    if mapping is not None:
        _saved(ReportedCostMapping(event_type=event_type, **mapping))
    EventType.objects.get(pk=event_type.pk).publish()


def _a_cost_book(tenant, described):
    return CostBook.objects.create(tenant=tenant, **described)


def _a_pricing_book(tenant, described):
    return PricingBook.objects.create(tenant=tenant, **described)


def _the_change_that_adds(rule):
    """A stored rule as the change a book publish takes to open it."""
    return {
        "kind": CHANGE_ADD, "measurement_key": rule["measurement_code"],
        "provider": rule["provider"], "event_type": rule["event_type"],
        "task_type": rule["task_type"], "subtask_type": rule["subtask_type"],
        **rule["grouping_fields"],
        "pricing_method": rule["pricing_method"],
        "rate_structure": rule["rate_structure"],
        "rate_per_unit_micros": rule["rate_per_unit_micros"],
        "unit_quantity": rule["unit_quantity"],
        "fixed_micros": rule["fixed_micros"],
    }


# ---------------------------------------------------------------------------
# Recording, and reading the acknowledgement
# ---------------------------------------------------------------------------

def _recording(customer, declared, claim, task_id, position):
    """The recording a generated file makes for this Event Type: the
    supplier and the currency the Blueprint fills in, and the claim's sample
    values where the Blueprint asks the tenant's code for them."""
    # The currency a reported cost is declared in, where the Blueprint binds
    # one: on an Event Type costed from the supplier's own figure. A complete
    # Blueprint's reported cost always arrives on the call.
    mapping = (declared["reported_cost_mapping"]
               if declared["costing_method"] == COSTING_METHOD_REPORTED
               else None)
    return RecordUsageRequest(
        customer_id=customer.id,
        idempotency_key=f"ubb-verification-record-{position}",
        event_type=declared["key"],
        provider=declared["provider_key"] or None,
        currency=(mapping["currency"] or None) if mapping else None,
        measurements=claim.measurements or None,
        provider_cost_micros=claim.provider_cost_micros,
        task_id=task_id)


def _read(record, declared):
    """The verdict on one recording, read off what it was acknowledged with.

    A gap fails it and is named: a quantity the Event Type requires for a
    complete cost that the recording did not carry, a cost UBB could not work
    out (the acknowledgement names why, and which quantities), or a replay
    that answered a different event. A replay's null running totals are not
    a gap — a replay records nothing, so it has nothing to total.
    """
    acknowledgement, replay = record["acknowledgement"], record["replay"]
    recorded = (acknowledgement or {}).get("measurements") or {}
    record["missing_required_measurement_keys"] = [
        quantity["code"] for quantity in declared["measurements"]
        if quantity["required_for_costing"]
        and quantity["code"] not in recorded]
    record["complete"] = (
        acknowledgement is not None and replay is not None
        and not record["missing_required_measurement_keys"]
        and acknowledgement["costing_status"] != COSTING_STATUS_UNRESOLVED
        and replay["event_id"] == acknowledgement["event_id"])
