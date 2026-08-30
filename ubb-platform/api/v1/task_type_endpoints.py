"""The kind-of-work registry on the tenant contract (#414, slice 5 §9/§10/§18).

**Where these routes sit, and why it is the root.** A tenant's declared kinds of
work are a KERNEL concept: metering resolves a unit's COGS ceiling and its two
expiry windows from one, billing resolves how the work is SOLD from the same
row, spend control reads the ceiling, and the Code Builder generates against
the vocabulary. ``api/v1/event_type_endpoints.py``, ``api/v1/plan_endpoints.py``
and ``api/v1/task_endpoints.py`` took the same decision for the same reason and
state it — a thing several products realize and none owns is mounted at the root
prefix rather than inside one product's mount.

⚠ **THIS IS A DELIBERATE DEPARTURE FROM A MERGED DECISION**, on evidence that
document did not have. #141 §3's table says this registry stays behind
``/metering/`` because *"task types are part of the declared metering
vocabulary. Moving them would drag the whole of /metering behind it"* — and then
hands the question on: *"#154 owns whether these names survive."* Two things
have happened since and both are on ``main``. Slice 2 moved the Event Type
catalogue to the root and the product prefix did **not** come with it, so the
stated reason has a landed counter-example one module over — and that module's
own docstring names this very route as unsettled: *"the two nearest neighbours
(/metering/grouping-fields, **/metering/task-types**) are where they are because
they predate that rule, not because they settle this."* And this slice puts
``pricing_mode`` on the registry: a declaration deciding whether a tenant's
customer is charged per event or one agreed number is realized by billing *and*
by metering and owned by neither, which is the kernel test verbatim.

⚠ **The move is available exactly once.** ADR-0007 §3 is explicit that a name is
not broken a second time to repair the first break, and #154 §14 records that
the clean break expires on platform admission rather than on a date. Leaving the
declaration surface behind ``/metering/`` while its subject moves is precisely
the split #141 §8 called *"the strongest reason the split namespace could not
survive"*.

**THE PRODUCT GATE IS STILL ``metering``, AND THE MOUNT IS A DIFFERENT QUESTION
FROM THE GATE.** A tenant who does not meter has no vocabulary to declare.
``/plans`` gates on ``billing`` from the root prefix on exactly this footing, and
the Event Type catalogue's docstring makes the same argument in the same words.
⚠ As there, the 403 branch cannot currently refuse anybody — ``Tenant.clean``
will not save a tenant whose products omit metering — and it is kept for the
same reason: being the one declaration surface that gates on nothing would be
the drift rather than the tidy-up, and the day metering stops being universal
this surface is already right.

**The write floor is Admin throughout, with no ``_WRITE_ROUTES`` carve-out.**
The ruling is the one the Grouping Field and Event Type registries already
carry: a declaration decides how usage is costed, which makes it a pricing-rule
change rather than a day-to-day data operation. Freezing the money-shaped half
of that declaration is consistent with the floor rather than novel.

**Job analytics does NOT come with them.** ``GET /metering/analytics/tasks``
stays where it is and stays gated on ``metering``: it is a reporting surface, it
belongs to the five-endpoint analytics collapse, and moving it now would break a
path twice — once here and once there.

**The public path says ``task-types``, not ``kinds``.** The console route says
*kinds of work*. That is ADR-0008 §4's identity/expression split working as
designed: the contract carries the registry's identity, the console carries the
expression.

**NO PUBLISH RECORD, NO DRAFT STATE AND NO EFFECTIVE-DATING LIVE HERE.** The
regime is frozen instead, and changing it is a retirement plus a new
declaration. The argument for that — including why this slice may not mint a
third publish mechanism — is stated once, at the column and at the rule that
keeps it: ``apps/platform/work/models.py:TaskType.pricing_mode`` and
``work/migrations/0021_a_kind_of_work_declares_how_it_is_sold.py``.
"""
from django.db import transaction
from ninja import Router

from api.v1.schemas import TaskTypeRegistryIn, TaskTypeRegistryOut
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.marker import records_audit
from apps.platform.grouping_fields.queries import slot_map
from apps.platform.work.models import TaskType
from apps.platform.work.queries import declared_task_types
from apps.platform.work.services import (
    KindOfWorkDeclaration, RegimeChangeRefused)
from core.auth import ADMIN, ApiKeyAuth, ProductAccess, READ, role_floor
from core.problems import Problem, ProblemOut
from core.vocabulary import TASK_TYPE_KIND_VALUES

task_type_router = Router(auth=ApiKeyAuth())

_product_check = ProductAccess("metering")


def _standing(tenant, requested):
    """What the tenant already holds for the declarations in this request.

    Read once for the whole body rather than per item: both of
    ``KindOfWorkDeclaration``'s rules are comparisons against the standing row,
    so every item needs one, and asking per item would issue a query per
    declaration on a call that may carry a hundred.

    Keyed on ``(kind, key)`` because that is the uniqueness key — one word may
    name a kind of work at either altitude and the two are different
    declarations with different policy.
    """
    return {(row.kind, row.key): row
            for row in TaskType.objects.filter(
                tenant=tenant, key__in={item.key for item in requested})}


@task_type_router.put("/task-types",
                      response={200: TaskTypeRegistryOut, 409: ProblemOut,
                                422: ProblemOut})
@role_floor(ADMIN)
@records_audit("task_type.declared")
def declare_task_types(request, payload: TaskTypeRegistryIn):
    """Declare the kinds of work you meter, and the policy each one carries.

    Idempotent: send the whole vocabulary every time. A kind of work you have
    already declared has its ceiling, its two windows and its
    `required_dimensions` updated in place.

    `pricing_mode` CANNOT BE CHANGED once a kind of work exists. Sending a
    different one answers `409 pricing_mode_frozen`; to change how a kind of
    work is sold, retire it with `retired: true` and declare a replacement under
    a new key. A key change is an integration change for you, so choose the
    regime with that in mind. Omitting it leaves an existing kind of work
    exactly as it is, and declares a new one `event_priced`.

    `retired: true` stops new work of that kind being started and leaves the
    declaration readable; `retired: false` brings it back. Omitting `retired`
    leaves it exactly as it is.

    `422 validation_error` answers a kind this registry does not recognise or a
    `required_dimensions` entry you have not declared as a grouping field.
    """
    # THE WHOLE BODY IS ONE TRANSACTION, so a request whose fourth declaration
    # is refused leaves none of the first three behind. That was true before
    # this route moved and the refusal added below is raised, never returned,
    # for the same reason.
    _product_check(request)
    tenant = request.auth.tenant
    grouping_keys = set(slot_map(tenant.id))
    with transaction.atomic():
        held = _standing(tenant, payload.task_types)
        recorded = []
        for tt in payload.task_types:
            # THE REFUSAL AT DECLARATION TIME (#407), against the registry's own
            # value set rather than a list restated here: a kind of work says
            # which altitude it is meant for, and that is the one thing a unit's
            # single type column cannot carry.
            if tt.kind not in TASK_TYPE_KIND_VALUES:
                raise Problem("validation_error", f"invalid kind {tt.kind!r}")
            missing = [d for d in tt.required_dimensions
                       if d not in grouping_keys]
            if missing:
                raise Problem("validation_error",
                              f"required_dimensions not declared: {missing}")
            standing = held.get((tt.kind, tt.key))
            # THE RULE IS THE PRODUCT'S AND THE DIALECT IS THIS LAYER'S — #409's
            # sentence, unchanged. What an omitted regime means, and when a
            # retirement instant moves, are facts about the concept, so they are
            # decided in `apps.platform.work`; rendering a refusal as
            # problem+json is this layer's job and belongs nowhere else.
            declaration = KindOfWorkDeclaration(tt.pricing_mode, tt.retired)
            # ⚠ ITS OWN CODE, NOT `validation_error`, AND ITS OWN STATUS. This
            # route already answers `validation_error` for two unrelated things,
            # so a third meaning would give away exactly the distinguishability
            # a caller needs to act — and the request is not malformed: it is
            # well formed and refused by the state of a row that already exists,
            # which is what a 409 means here. `currency_locked` is the same
            # shape one module over.
            try:
                regime = declaration.regime_over(standing)
            except RegimeChangeRefused as refused:
                raise Problem(
                    "pricing_mode_frozen", str(refused),
                    extensions={"key": refused.key, "kind": refused.kind,
                                "pricing_mode": refused.standing_regime})
            written, _ = TaskType.objects.update_or_create(
                tenant=tenant, key=tt.key, kind=tt.kind,
                defaults={
                    # `None` only for a kind of work that does not exist yet and
                    # named no regime, so the COLUMN's own default answers
                    # rather than a value invented one layer above it.
                    **({} if regime is None else {"pricing_mode": regime}),
                    "default_provider_cost_limit_micros":
                        tt.default_provider_cost_limit_micros,
                    "silence_window_seconds": tt.silence_window_seconds,
                    "absolute_deadline_seconds": tt.absolute_deadline_seconds,
                    "required_dimensions": tt.required_dimensions,
                    **declaration.retirement_over(standing),
                })
            # ⚠ THE LOOP READS ITS OWN WRITES, BECAUSE A BODY MAY NAME ONE
            # DECLARATION TWICE. Nothing refuses a repeated `(kind, key)` — the
            # list is a list — and with only the pre-read above, the second
            # occurrence would see no standing row, skip the refusal, and hand
            # a regime change straight to the trigger, which answers with an
            # integrity error rather than the 409 that names the next step.
            # It also keeps the retirement instant right in that case: without
            # this, a second occurrence would compare against the row as it was
            # before the first one moved it.
            held[(tt.kind, tt.key)] = written
            # ⚠ THE ENTRY IS THE DECLARATION'S OWN FIELDS, NOT A SECOND LIST OF
            # THEM. Writing the seven names again here is how a field added to
            # `TaskTypeIn` reaches the row and misses the ledger, silently and
            # with every test green; dumping the item makes the ledger follow
            # the schema by construction.
            #
            # ⚠ ONE FIELD IS OVERRIDDEN, AND `retired` IS DELIBERATELY NOT. The
            # regime is recorded as the ROW now holds it, because it is frozen —
            # the resolved value IS the declaration and can never become
            # anything else, so an entry carrying `null` for it would record
            # nothing about the money. Retirement is recorded as the CALLER SENT
            # it, because it is a two-way switch where *said nothing* is a
            # materially different act from *said false*, and flattening the two
            # would lose which one happened.
            recorded.append({**tt.model_dump(),
                             "pricing_mode": written.pricing_mode})
        # ONE ACTION FOR THE WHOLE REQUEST, INCLUDING A RETIREMENT, and that is
        # a fact about this surface rather than a shortcut. `provider.retired`
        # exists beside `provider.declared` because that route revises ONE
        # supplier, so "this request retired one" is a true sentence about it.
        # This one declares a whole vocabulary: a single call can declare three
        # kinds of work and retire a fourth, and an action naming the retirement
        # would then be wrong about the other three. What each item did is in
        # the metadata, per item, which is where a reader can act on it.
        audit_record(
            action="task_type.declared",
            tenant_id=tenant.id,
            resource_type="task_type_registry",
            resource_id=tenant.id,
            metadata={"task_types": recorded},
        )
    return 200, {"task_types": declared_task_types(tenant.id)}


@task_type_router.get("/task-types", response=TaskTypeRegistryOut)
@role_floor(READ)
def list_task_types(request):
    """Every kind of work you have declared, retired ones included.

    A retired one carries `retired_at`, the instant it stopped being offered;
    a live one carries `null`.
    """
    # WHY RETIRED ONES ARE IN THE ANSWER RATHER THAN FILTERED OUT OF IT, and
    # this belongs in a comment because the exporter puts the docstring above
    # verbatim into `openapi/v1.json` and the generated SDK — a caller needs the
    # shape, not the argument. Work already done under a retired declaration
    # still refers to it, and a replacement declared beside it is only a RECORD
    # of a change if both rows stay readable. That record is what lets
    # `pricing_mode` be frozen with no publish mechanism behind it.
    _product_check(request)
    return {"task_types": declared_task_types(request.auth.tenant.id)}
