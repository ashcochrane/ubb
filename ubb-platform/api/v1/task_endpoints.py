"""The unit-of-work lifecycle on the tenant contract (#409, slice 5 §5/§17).

**Where these routes sit, and why it is the root.** A unit of work is a KERNEL
concept: metering hangs postings off it and rolls their cost into it, billing
starts one behind its spend gate and will key a charge on how it ended, spend
control kills one, and the Code Builder generates the calls that open and close
it. ``api/v1/event_type_endpoints.py`` and ``api/v1/plan_endpoints.py`` took the
same decision for the same reason and state it — a thing several products
realize and none owns is mounted at the root prefix rather than inside one
product's mount. These three calls were behind ``/metering/`` because they
predate that rule, which the Event Type catalogue's own docstring names them
as: *"the two nearest neighbours … are where they are because they predate that
rule, not because they settle this."* This is the settlement.

⚠ **The move is available exactly once.** ADR-0007 §3 is explicit that a name is
not broken a second time to repair the first break, so a lifecycle left under
one product's prefix while its subject is a kernel concept would be permanent.

**AND THESE THREE ARE UNGATED, WHICH IS A SEPARATE QUESTION FROM THE MOUNT.**
The neighbours at the root still gate — ``/event-types`` on ``metering``,
``/plans`` on ``billing`` — because each declares a *vocabulary* a tenant who
does not use that product has no reason to hold. A unit of work is not a
declaration. It is the thing every product's answer is *about*: refusing to let
a billing-only tenant read the state of the work its own charge will key on
would be refusing it its own record. There is no product whose absence makes
these calls meaningless, so there is no product to gate them on.

**Job analytics is deliberately NOT here.** ``GET /metering/analytics/tasks``
stays where it is and stays gated on ``metering``: it is a reporting surface,
it belongs to the five-endpoint analytics collapse, and moving it now would
break a path twice — once here and once there.

**The write floor is Write, not Admin.** Closing a unit of work is the tail of
usage ingestion rather than a change to the rules or a movement of money, which
is the footing ``POST /metering/usage`` sits on; ``api/v1/tests/test_role_floors.py``
holds the carve and this module must agree with it rather than restate it.
"""
from uuid import UUID

from django.db import transaction
from django.shortcuts import get_object_or_404
from ninja import Router

from api.v1.pagination import page
from api.v1.schemas import (
    CloseTaskRequest, CloseTaskResponse, PaginatedTasks, TaskDetailOut,
    task_out,
)
from apps.platform.work.models import Task
from apps.platform.work.services import (
    OUTCOMES_ACCEPTING_A_REASON, OUTCOMES_REQUIRING_A_REASON,
    STATUS_FOR_OUTCOME, TaskService,
)
from core.auth import ApiKeyAuth, READ, WRITE, role_floor
from core.identifiers import UUIDIdentifier
from core.problems import Problem, ProblemOut
from core.vocabulary import OUTCOME_REASON_VALUES

task_router = Router(auth=ApiKeyAuth())


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
    _refuse_an_ill_formed_declaration(payload)

    task = get_object_or_404(Task, id=task_id, tenant=request.auth.tenant)
    with transaction.atomic():
        closed, transitioned = TaskService.close_task(
            task.id, payload.outcome,
            outcome_reason=payload.outcome_reason or "",
            reason_detail=payload.reason_detail or "")

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
    # THE OUTCOME IS WHAT IS COMPARED, and not the reason beside it. The
    # outcome is the declaration — it is what the state and the money follow
    # from — while the reason explains it and moves nothing. Refusing a retry
    # whose free-text sentence had been re-worded would fail the honest caller
    # for a difference with no consequence, and `killed` and `expired` are
    # refused by construction anyway: no outcome maps onto either.
    replayed = not transitioned
    if replayed and closed.status != STATUS_FOR_OUTCOME[payload.outcome]:
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


def _refuse_an_ill_formed_declaration(payload):
    """Judge the declaration itself, before any unit is read or locked.

    ⚠ AN UNRECOGNISED REASON IS REFUSED, AND THE ARGUMENT THAT SOFTENS UBB'S
    OWN STOP REASONS DOES NOT TRANSFER HERE. `apps/platform/work/reasons.py`
    reconciles its own closed set with an open registry concept by ruling that
    closed binds UBB's PRODUCERS while open binds CONSUMERS — which holds only
    because a stop reason is UBB-produced. This value arrives from outside, so
    the closed set is a rule on what may come in.
    """
    if payload.outcome not in STATUS_FOR_OUTCOME:
        raise Problem("validation_error",
                      f"outcome must be one of "
                      f"{', '.join(sorted(STATUS_FOR_OUTCOME))}")

    declared = payload.outcome_reason is not None or payload.reason_detail is not None
    if payload.outcome not in OUTCOMES_ACCEPTING_A_REASON:
        if declared:
            raise Problem("validation_error",
                          f"outcome_reason and reason_detail are not accepted "
                          f"when the outcome is {payload.outcome}")
        return

    if payload.outcome_reason is None:
        if payload.outcome in OUTCOMES_REQUIRING_A_REASON:
            raise Problem("validation_error",
                          f"outcome_reason is required when the outcome is "
                          f"{payload.outcome}")
        return

    if payload.outcome_reason not in OUTCOME_REASON_VALUES:
        raise Problem("validation_error",
                      f"{payload.outcome_reason!r} is not a recognised "
                      f"outcome_reason")
