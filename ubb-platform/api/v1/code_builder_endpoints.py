"""The Code Builder on the tenant contract: an Integration Blueprint, resolved
and read back (#576, #184 §3).

Two routes. One resolves a selection into a Blueprint and keeps the resolved
content; the other returns a kept Blueprint by the fingerprint a generated
file was stamped with.

**Where these routes sit.** At a prefix of their own. A Blueprint is resolved
from the kernel's registries and metering's rules together and belongs to
neither, so mounting it inside one product's prefix would say on the published
contract that the product owns it — the argument
``api/v1/event_type_endpoints.py`` makes for the catalogue.

**The product gate is metering**, like every registry a Blueprint resolves
(ADR-0011 §2: the mount is a different question from the gate). A tenant who
does not meter has declared nothing to generate against. ⚠ As on those
registries the 403 branch cannot currently refuse anybody — ``Tenant.clean``
will not save a tenant whose products omit metering — and it is kept for the
reason they keep it.

**THE RESOLUTION IS A `POST` AT THE READ FLOOR, AND BOTH HALVES ARE THE
DECISION** (#184 §3). It is a POST because it stores: the fingerprint has to
name a snapshot that exists, not a hash recomputed later from whatever
configuration is there by then. It floors at Read because what it stores is a
derived fixture — nothing prices, costs or enforces from it — and the people
it exists for are developers reading configuration they may not change.
``test_role_floors.py`` carries the one-line exception to "every write is
Admin", and ``test_audit_sweep.py`` the exemption from the audit ledger: a
Blueprint is not a governance act, and an audit entry would be a second row
written by a route that promises to write one.

**A DRAFT PREVIEW IS ADMIN'S**, checked inside the handler because it is the
same route asked a different question. A draft is configuration nobody has
published, and showing how it would render is for the people who may publish
it.

**WHAT THIS MODULE DOES NOT DO.** It declares nothing, edits nothing and
publishes nothing, for an admin exactly as for anybody else, and it never
sends the request a diagnostic offers. It renders no code. It verifies
nothing.
"""
from ninja import Router

from api.v1 import integration_blueprint
from api.v1.schemas import (
    IntegrationBlueprintSelectionIn, ResolvedIntegrationBlueprint)
from apps.platform.code_builder import snapshots
from core.auth import (
    ADMIN, ApiKeyAuth, ProductAccess, READ, require_role, role_floor)
from core.problems import Problem, ProblemOut

code_builder_router = Router(auth=ApiKeyAuth())

_product_check = ProductAccess("metering")

def _with_fingerprint(document, fingerprint):
    """The Blueprint as published: the document, carrying the fingerprint of
    the snapshot kept for it. Assembled in one place so the resolution and
    the read cannot serve two shapes."""
    return {**document, "configuration_fingerprint": fingerprint}


@code_builder_router.post("/blueprints",
                          response={200: ResolvedIntegrationBlueprint,
                                    403: ProblemOut, 422: ProblemOut})
@role_floor(READ)
def resolve_blueprint(request, payload: IntegrationBlueprintSelectionIn):
    """Resolve a selection into an Integration Blueprint.

    The Blueprint says what your integration code must mean: every call, each
    token of each call with where its value comes from, how ready each call
    is, and what stands in the way.

    Resolved from PUBLISHED configuration: an Event Type revised since it was
    published resolves from what it last published. The resolution is stored,
    and `configuration_fingerprint` identifies it: the selection, what it
    resolved to, and the configuration it was resolved from, including which
    publication of each Event Type. The same selection answers the same
    fingerprint for as long as the configuration in force is the same; the
    order things are listed in, and the `remediation_request` a diagnostic
    offers, are not part of it. Nothing else is written, and no configuration
    is changed.

    With `draft_preview: true` the Blueprint resolves from draft declarations
    instead. That requires the admin role, stores nothing and answers
    `configuration_fingerprint: null`.

    `422 validation_error` answers a `target` that is not one of the published
    targets, or a selection naming more than 50 distinct Event Types or more
    than 50 distinct Subtask kinds.
    `403 forbidden` answers a draft preview asked for below the admin role.
    """
    _product_check(request)
    if payload.draft_preview:
        require_role(request, ADMIN)
    tenant = request.auth.tenant
    resolved = integration_blueprint.resolve(
        tenant, target=payload.target, task_type=payload.task_type,
        event_types=payload.event_types, subtask_types=payload.subtask_types,
        draft_preview=payload.draft_preview)
    fingerprint = (None if resolved.identity is None
                   else snapshots.store(tenant=tenant,
                                        identity=resolved.identity,
                                        presentation=resolved.presentation))
    return 200, _with_fingerprint(resolved.document, fingerprint)


@code_builder_router.get("/blueprints/{configuration_fingerprint}",
                         response={200: ResolvedIntegrationBlueprint,
                                   404: ProblemOut})
@role_floor(READ)
def get_blueprint(request, configuration_fingerprint: str):
    """The Integration Blueprint stored under a fingerprint.

    Exactly the Blueprint that was resolved, whatever has changed since. A
    fingerprint that was never resolved, or whose snapshot has been removed,
    answers `404 not_found`: resolve the selection again.
    """
    _product_check(request)
    content = snapshots.stored(
        tenant=request.auth.tenant,
        configuration_fingerprint=configuration_fingerprint)
    if content is None:
        raise Problem(
            "not_found",
            f"no blueprint is stored under '{configuration_fingerprint}'")
    return 200, _with_fingerprint(integration_blueprint.as_answered(content),
                                  configuration_fingerprint)
