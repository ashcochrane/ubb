"""The unit-of-work lifecycle on the tenant contract (#409/#410, slice 5
§3/§4/§5/§16/§17).

**Where these routes sit, and why it is the root.** A unit of work is a KERNEL
concept: metering hangs postings off it and rolls their cost into it, billing
tests a customer's spending state before one begins and will key a charge on
how it ended, spend control kills one, and the Code Builder generates the calls
that open and close it. ``api/v1/event_type_endpoints.py`` and
``api/v1/plan_endpoints.py`` took the same decision for the same reason and
state it — a thing several products realize and none owns is mounted at the
root prefix rather than inside one product's mount. The read, the list and the
close were behind ``/metering/`` because they predate that rule, which the
Event Type catalogue's own docstring names them as: *"the two nearest
neighbours … are where they are because they predate that rule, not because
they settle this."* This is the settlement.

**AND THE START IS NOT A FOURTH MOVE — IT IS THE FIRST TIME THERE HAS BEEN
ONE.** There has never been a `POST` on the task surface. Registering a unit of
work was a SIDE EFFECT of a flag on a billing-gated affordability call, so a
metering-only tenant could not begin work at all and a billing tenant got a
product wall, a money-shaped admission check and the registration of a unit
of work fused into one call. That flag is retired here rather than redirected — the clean break is
available exactly once — and what survives of that call is its read-only half,
the advisory answer, which stays where it is and is slice 6's to rebuild.

⚠ **The move is available exactly once.** ADR-0007 §3 is explicit that a name is
not broken a second time to repair the first break, so a lifecycle left under
one product's prefix while its subject is a kernel concept would be permanent.

**AND ALL FOUR ARE UNGATED, WHICH IS A SEPARATE QUESTION FROM THE MOUNT.**
The neighbours at the root still gate — ``/event-types`` on ``metering``,
``/plans`` on ``billing`` — because each declares a *vocabulary* a tenant who
does not use that product has no reason to hold. A unit of work is not a
declaration. It is the thing every product's answer is *about*: refusing to let
a billing-only tenant read the state of the work its own charge will key on
would be refusing it its own record. There is no product whose absence makes
these calls meaningless, so there is no product to gate them on.

⚠ **THE START IS THE ONE WHERE UNGATED HAS TEETH**, because it is the one with
money-shaped checks in it. Those checks are conditioned INSIDE the call on
whether the tenant has a wallet to test — never on a product flag at the door —
so a metering-only caller is not refused them, they simply do not apply. See
``_TENANT_HAS_A_WALLET`` below, which carries the argument and the in-house
precedent for the shape.

**Job analytics is deliberately NOT here.** ``GET /metering/analytics/tasks``
stays where it is and stays gated on ``metering``: it is a reporting surface,
it belongs to the five-endpoint analytics collapse, and moving it now would
break a path twice — once here and once there.

**The write floor is Write, not Admin.** Closing a unit of work is the tail of
usage ingestion rather than a change to the rules or a movement of money, which
is the footing ``POST /metering/usage`` sits on — and registering one is the
HEAD of the same ingestion, on the same footing for the same reason.
``api/v1/tests/test_role_floors.py`` holds the carve and this module must agree
with it rather than restate it.
"""
from uuid import UUID

from django.db import transaction
from django.shortcuts import get_object_or_404
from ninja import Router

from api.v1.pagination import page
from api.v1.schemas import (
    PINNED_FIELD_ON_THE_WIRE, CloseTaskRequest, CloseTaskResponse,
    PaginatedTasks, StartTaskRequest, StartTaskResponse, TaskDetailOut,
    start_task_out, task_out,
)
from apps.platform.customers.models import Customer
from apps.platform.work.models import Task
from apps.platform.work.services import (
    CloseDeclaration, DeclarationRefused, StartDeclaration, StartRefused,
    TaskService,
)
from core.auth import ApiKeyAuth, READ, WRITE, role_floor
from core.identifiers import UUIDIdentifier
from core.problems import Problem, ProblemOut

task_router = Router(auth=ApiKeyAuth())

#: WHETHER THE MONEY-SHAPED HALF OF A START APPLIES TO THIS TENANT AT ALL.
#:
#: ⚠ A CAPABILITY CHECK INSIDE THE CALL, NEVER A PRODUCT WALL AT THE DOOR, and
#: the difference is the whole point of the route being ungated. The in-house
#: shape is one file over — a rate-card write is metering-gated and its
#: money-shaped variant ADDITIONALLY requires billing, asked inside the handler
#: rather than by the router — with one difference that matters here: a
#: metering-only caller is not REFUSED the money-shaped part, it simply does
#: not apply, because there is no wallet to test. Refusing would be telling a
#: tenant it may not register its own work because it does not buy a product
#: the work does not need.
#:
#: The product is what the question asks, rather than *does a Wallet row
#: exist*, and those are not the same question: a billing tenant's customer who
#: has never been credited has no wallet row and a zero balance, and reading
#: the absence of the row as *no wallet regime to test* would let exactly that
#: customer start unlimited work with nothing behind it.
_TENANT_HAS_A_WALLET = "billing"


@task_router.post("/tasks", response={200: StartTaskResponse, 404: ProblemOut,
                                      409: ProblemOut, 422: ProblemOut})
@role_floor(WRITE)
def start_task(request, payload: StartTaskRequest):
    """Register a unit of work, and hand back the same one on a retry.

    `idempotency_key` is REQUIRED and is unique per customer. Send the same key
    again and you get the unit of work you already started, with
    `replayed: true` and nothing created a second time — no second ceiling, no
    second set of totals. Send the same key describing a DIFFERENT unit and the
    call answers `409 idempotency_key_conflict`, naming the request field that
    differs. A unit of work is pinned by its customer, its parent, its declared
    kind of work, the ceiling it resolved and the grouping values declared on
    it. `external_task_id` and `metadata` are not pinned — a replay carrying
    different values is still a replay, and the original's values stand.

    Naming `parent_task_id` registers contained work under a running unit.
    There is one start shape, not two.

    `409 task_start_refused` names, in `reason`, why the customer may not begin
    new work — a wallet below its floor, a stop in force, the concurrency cap,
    or a parent that is not a running top-level unit. `422 validation_error`
    answers a request that is wrong in itself: an undeclared or retired kind of
    work, a missing required grouping field, an undeclared grouping key, or a
    ceiling above the one the kind of work carries.
    """
    # ADR-001's boundary discipline puts the product import in the body; this
    # is the composition layer, which may import any product, and the money
    # -shaped half of a start is billing's rule to state.
    from apps.billing.gating.services.risk_service import RiskService
    from apps.platform.grouping_fields.services import (
        DimensionError, DimensionService)

    tenant = request.auth.tenant
    customer = get_object_or_404(Customer, id=payload.customer_id, tenant=tenant)
    # ⚠ NOT THE SAME VOCABULARY AS THE DECLARED KIND OF WORK, though two of its
    # words are spelled the same — this is `GroupingField.scope`, saying where a
    # value is SET and therefore how far it is inherited. The argument is made
    # in full in `RiskService.resolve_type_policy`.
    scope = "subtask" if payload.parent_task_id is not None else "task"

    # ⚠ ONE TRANSACTION AROUND THE WHOLE START, AND EVERY REFUSAL IS RAISED
    # FROM INSIDE IT. That is what makes a refused start spend nothing: the
    # grouping values a start records against a key's cardinality cap are
    # permanent, and a refusal that returned instead of raising would commit
    # them for work that never began. The parent's lock is taken in the same
    # block for the reason it has always been — contained work must not be
    # born under a unit a cascade is withdrawing.
    with transaction.atomic():
        # THE KEY'S CLAIM IS READ FIRST, BEFORE ANYTHING SPENDS OR COUNTS.
        # A retry after a lost response must be answerable from what is already
        # written down, so it never reaches the wallet checks, never counts
        # against the concurrency cap and never records a grouping value. The
        # uniqueness constraint underneath is still what settles two identical
        # starts racing; this is what settles the ordinary retry.
        claimed = TaskService.claimed_by(tenant, customer,
                                         payload.idempotency_key)
        if claimed is not None:
            # RESOLVED, NEVER ADMITTED, and never re-derived from policy. A
            # comparison is a question about what the caller SAID, and both a
            # recording resolution and a re-run of the ceiling ladder would
            # make the answer depend on configuration that can move under a
            # retry — which is the one case a permanent claim exists to answer.
            try:
                declared_slots = DimensionService.resolve(
                    tenant, payload.dimensions, scope)
            except DimensionError as exc:
                raise Problem("validation_error", str(exc))
            differing = StartDeclaration(
                payload.idempotency_key,
                parent_task_id=payload.parent_task_id,
                task_type=payload.task_type,
                slot_values=declared_slots,
                provider_cost_limit_micros=payload.provider_cost_limit_micros,
            ).conflicting_field_on(claimed)
            if differing is not None:
                field = PINNED_FIELD_ON_THE_WIRE[differing]
                raise Problem(
                    "idempotency_key_conflict",
                    f"this idempotency_key already started a unit of work with "
                    f"a different {field}",
                    extensions={"field": field, "task_id": str(claimed.id)})
            return 200, start_task_out(claimed, replayed=True)

        # THE MONEY-SHAPED HALF, AND ONLY FOR A TENANT IT CAN MEAN ANYTHING
        # FOR. A metering-only tenant is not refused these checks — there is no
        # wallet to test, so they do not apply, and its balance snapshot is the
        # zero it has always been for a customer with no wallet.
        has_a_wallet = _TENANT_HAS_A_WALLET in tenant.products
        balance = 0
        if has_a_wallet:
            verdict = RiskService.check(
                customer, parent_task_id=payload.parent_task_id)
            if not verdict["allowed"]:
                raise _refused(verdict)
            balance = verdict["balance_micros"] or 0

        # THE ORDER OF THE THREE REFUSALS BELOW IS THE ORDER THEY HAVE ALWAYS
        # RUN IN: the customer's own standing, then the parent this start
        # names, then the cap on work already running. It is preserved
        # deliberately rather than tidied — each is a published verdict, and
        # which one a caller is told about first is part of what the surface
        # answers.
        try:
            parent = TaskService.parent_for(
                tenant, customer, payload.parent_task_id)
        except StartRefused as refused:
            raise Problem("task_start_refused", str(refused),
                          extensions={"reason": refused.reason})
        if has_a_wallet:
            verdict = RiskService.concurrency_verdict(customer, balance)
            if not verdict["allowed"]:
                raise _refused(verdict)

        # THE CEILING IS UNIVERSAL AND RESOLVES THE SAME WAY FOR EVERY TENANT
        # (design D7): the caller may request lower than the declared kind of
        # work allows, never higher, then the kind of work's own default, then
        # the tenant default for this altitude, then uncapped.
        try:
            declared_kind, slot_values, ceiling = (
                RiskService.resolve_start_policy(
                    tenant, task_type=payload.task_type,
                    dimensions=payload.dimensions,
                    requested_limit_micros=payload.provider_cost_limit_micros,
                    is_subtask=parent is not None))
        except ValueError as exc:
            raise Problem("validation_error", str(exc))

        task = TaskService.create_task(
            tenant=tenant,
            customer=customer,
            parent=parent,
            balance_snapshot_micros=balance,
            provider_cost_limit_micros=ceiling,
            metadata=payload.metadata or {},
            external_task_id=payload.external_task_id,
            idempotency_key=payload.idempotency_key,
            # Tier-2 (D4/I6): pin the resolved billing owner so the concurrency
            # slot and both reapers never re-resolve it.
            billing_owner_id=customer.resolve_billing_owner().id,
            task_type=declared_kind,
            dimension_slots=slot_values,
        )
    return 200, start_task_out(task, replayed=False)


def _refused(verdict):
    """A money-shaped verdict, as the refusal a start answers with.

    ONE CODE CARRYING THE REASON, rather than a code per verdict. Every word in
    that vocabulary says the same thing about the request — it is well formed,
    and what refuses it is the current state of the customer, the tenant's own
    controls or the work being named — which is what a 409 means in
    `docs/conventions/api-contract.md`'s terms. The words themselves belong to
    a vocabulary slice 6 rebuilds, so they travel as data rather than as codes
    a caller would have to unlearn.
    """
    return Problem(
        "task_start_refused",
        f"this customer cannot start new work: {verdict['reason']}",
        extensions={"reason": verdict["reason"],
                    "balance_micros": verdict["balance_micros"]})


@task_router.get("/tasks", response=PaginatedTasks)
@role_floor(READ)
def list_tasks(request, cursor: str = None, limit: int = 50,
               customer_id: UUIDIdentifier = None, task_type: str = None,
               status: str = None):
    """Top-level work with its materialized cost rollups.

    Contained work is omitted — it belongs to its parent's detail view, so a
    listing counts whole jobs rather than the steps inside them."""
    qs = Task.objects.filter(tenant=request.auth.tenant, parent__isnull=True)
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
    if task_type:
        qs = qs.filter(task_type=task_type)
    if status:
        qs = qs.filter(status=status)
    return page(qs, cursor, limit, serialize=task_out, time_field="created_at")


@task_router.get("/tasks/{task_id}", response={200: TaskDetailOut, 404: ProblemOut})
@role_floor(READ)
def get_task(request, task_id: UUID):
    """One unit's cost receipt plus the work contained in it.

    Reads the rollups `TaskService.accumulate_cost` maintains — including
    events that landed after a kill — so this never aggregates
    ubb_posting. One indexed row read plus its children."""
    task = get_object_or_404(Task, id=task_id, tenant=request.auth.tenant)
    body = task_out(task)
    body["subtasks"] = [task_out(s) for s in
                        task.subtasks.all().order_by("created_at")]
    return 200, body


@task_router.post("/tasks/{task_id}/close",
                  response={200: CloseTaskResponse, 409: ProblemOut,
                            422: ProblemOut})
@role_floor(WRITE)
def close_task(request, task_id: UUID, payload: CloseTaskRequest):
    """Close a unit of work, DECLARING HOW IT ENDED.

    The outcome is required and the winning transition is the exactly-once
    trigger a charge will later key on. Closing a parent withdraws its
    still-running contained work in the same transaction — cleanup is one call
    — and closing contained work closes it alone.

    ⚠ THIS DOES NOT TOUCH THE USAGE RAIL. A terminal state prevents a customer
    charge; it never rejects, deletes or zeroes genuine operational usage,
    including usage that arrives after termination. A late report on a closed
    unit still lands, costs and rolls up.
    """
    # THE RULE IS THE PRODUCT'S AND THE DIALECT IS THIS LAYER'S. Which reason a
    # given outcome requires, permits or refuses is a fact about the concept,
    # so it is decided in `apps.platform.work`; rendering that refusal as
    # problem+json is the composition layer's job and belongs nowhere else.
    try:
        declaration = CloseDeclaration.declared(
            payload.outcome, payload.outcome_reason, payload.reason_detail)
    except DeclarationRefused as refused:
        raise Problem("validation_error", str(refused),
                      extensions={"field": refused.field})

    task = get_object_or_404(Task, id=task_id, tenant=request.auth.tenant)
    with transaction.atomic():
        closed, transitioned = TaskService.close_task(task.id, declaration)

    # A CLOSE THAT DID NOT WIN THE TRANSITION IS ONE OF EXACTLY TWO THINGS, and
    # telling them apart is the point of this endpoint (spec §5). The unit was
    # already terminal; either it is already in the state this call declares —
    # a retry after a lost response, which must not read as a second close —
    # or this call CONTRADICTS what UBB already recorded.
    #
    # ⚠ THE REFUSAL HALF IS WHY THIS IS NOT A SILENT 200. Once a delivery
    # creates a charge, a job UBB killed on its ceiling that the tenant
    # delivered anyway would answer 200 carrying the killed status and no
    # indication that no charge fired — silent revenue loss whose first symptom
    # is a month-end number lower than expected. Letting a late delivery
    # override a kill or an expiry was rejected outright: it makes ignoring the
    # stop signal free, so the ceiling stops being a ceiling.
    #
    # WHAT COUNTS AS "THE SAME DECLARATION" IS THE DECLARATION'S OWN QUESTION,
    # and `CloseDeclaration.already_recorded_on` carries the argument: the
    # outcome and its reason are both compared, the free-text sentence is not.
    replayed = not transitioned
    if replayed and not declaration.already_recorded_on(closed):
        raise Problem(
            "task_already_terminal",
            f"this unit is already {closed.status} and cannot be closed as "
            f"{payload.outcome}",
            extensions={"task_status": closed.status, "charge_created": False})

    return 200, {
        "task_id": str(closed.id),
        "parent_task_id": str(closed.parent_id) if closed.parent_id else None,
        "status": closed.status,
        "outcome": payload.outcome,
        "replayed": replayed,
        # HONESTLY FALSE ON EVERY PATH, because the Charge does not exist yet.
        # This is the field's true value under the rules in force on this
        # commit rather than a placeholder to be filled in later.
        "charge_created": False,
        "total_billed_cost_micros": closed.total_billed_cost_micros,
        "total_provider_cost_micros": closed.total_provider_cost_micros,
        "unresolved_event_count": closed.unresolved_event_count,
        "unpriced_event_count": closed.unpriced_event_count,
        "event_count": closed.event_count,
    }
