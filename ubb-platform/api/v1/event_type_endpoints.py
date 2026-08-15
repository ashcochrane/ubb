"""The Event Type catalogue on the tenant contract (#267).

Everything the slice has built so far is invisible to a tenant: five records, a
lifecycle, a grammar for structured paths and a money conversion, and no way to
declare or read any of it. This module is the surface, and it publishes three
closed value sets with it — the costing method, the source kind and the amount
representation, each rendering a real ``enum`` beside its concept marker.

**Where these routes sit, and why it is the root.** The catalogue is a KERNEL
concept: rating reads it, the drawdown reads its cost, analytics groups by it,
spend control needs it to know in advance that an event is costable, and the
Code Builder generates from it. ``api/v1/plan_endpoints.py`` took the same
decision for the same reason and states it — a thing several products realize
and none owns is mounted at the root prefix rather than inside one product's
mount. Putting the catalogue under ``/metering/`` would say on the published
contract that metering owns it, and ADR-0007 §3 is explicit that a name is not
broken a second time to repair the first break: the two nearest neighbours
(``/metering/grouping-fields``, ``/metering/task-types``) are where they are
because they predate that rule, not because they settle this.

**The product gate is metering**, which is a different question from the mount:
a tenant who does not meter has no vocabulary to declare. ``/plans`` gates on
``billing`` from the root prefix on exactly this footing.

⚠ **That gate cannot currently refuse anybody, and saying so is the point.**
``Tenant.clean`` will not save a tenant whose products omit metering, so the
403 branch is unreachable from outside — the same is true of every
``/metering/`` route, which is why this is a property of the product model
rather than of this module. It is kept because being the one tenant surface
that declares no product would be the drift rather than the tidy-up, and
because the day metering stops being universal this surface is already right.
``test_event_type_endpoints.py`` asserts the constraint that makes it
unreachable, so the day that changes, the claim goes red instead of aging into
a lie.

**The write floor is Admin throughout, with no ``_WRITE_ROUTES`` carve-out.**
The ruling is the one the Grouping Field and Task Type registries already
carry: a declaration decides how usage is costed, which makes it a
pricing-rule change rather than a day-to-day data operation.

**Every list wears the cursor envelope** (``docs/conventions/api-contract.md``)
— including the short ones, because the rule says so and because the shape of
a published list is exactly the thing ADR-0007 §3 will not let a later slice
repair. The row serializers live beside their Out schemas in ``schemas.py``,
which is the same convention's other half.

**What this module does NOT do.** It resolves nothing, rates nothing and costs
nothing — no recording path reads a single row it serves. Slice 2 owns the
declaration; slice 3 owns every behaviour the declaration selects. The one
place that shows through is ``event_type_out``'s ``publication_blockers``,
which is served rather than stored so that two encodings of one fact cannot
disagree.
"""
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from ninja import Router

from api.v1.pagination import page
from api.v1.schemas import (
    EventCategoryIn, EventCategoryOut, EventTypeIn, EventTypeOut,
    EventTypeUpdateIn, MeasurementIn, MeasurementOut, PaginatedEventCategories,
    PaginatedEventTypes, PaginatedMeasurements, PaginatedProviders, ProviderIn,
    ProviderOut, ProviderUpdateIn, ReportedCostMappingIn,
    ReportedCostMappingOut, event_category_out, event_type_out,
    measurement_out, provider_out, reported_cost_mapping_out,
)
from apps.metering.pricing.models import Rate
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.marker import records_audit
from apps.platform.event_types.models import (
    REPORTED_COST_MAPPING, DeclarationIncomplete, EventCategory, EventType,
    Measurement, Provider, ReportedCostMapping,
)
from core.auth import ADMIN, ApiKeyAuth, ProductAccess, READ, role_floor
from core.problems import Problem, ProblemOut

event_type_router = Router(auth=ApiKeyAuth())

_product_check = ProductAccess("metering")

#: The default page size the cursor envelope's endpoints take. The clamp to
#: [1, 100] is `paginate`'s; this is only the default a caller who says nothing
#: gets, and it matches the rest of the surface.
_DEFAULT_LIMIT = 50


# ---------------------------------------------------------------------------
# Lookups and refusals — the shapes every handler below needs
# ---------------------------------------------------------------------------

def _declarations(tenant):
    """Every Event Type of ``tenant``, with the parts a serializer will ask for.

    One place rather than per handler, because every caller serializes the
    WHOLE declaration: without the joins, listing a page of declarations issues
    a query per quantity and per satellite on each row, and the N+1 arrives on
    the read a Code Builder makes most.
    """
    return (EventType.objects
            .filter(tenant=tenant)
            .select_related("provider", "category", REPORTED_COST_MAPPING)
            .prefetch_related("measurements"))


def _declaration(tenant, key):
    """One Event Type with its parts, or a 404 naming the key that missed."""
    event_type = _declarations(tenant).filter(key=key).first()
    if event_type is None:
        raise Problem("not_found", f"event type with key '{key}' not found")
    return event_type


def _mapping(event_type, key):
    """The Event Type's reported-cost mapping, or a 404 saying it has none.

    ``getattr`` with a default, because a reverse one-to-one RAISES when the
    row is absent rather than answering ``None`` — and the absence is an
    ordinary state here, not an error, so it has to be turned into the 404 the
    caller can act on.
    """
    mapping = getattr(event_type, REPORTED_COST_MAPPING, None)
    if mapping is None:
        raise Problem(
            "not_found",
            f"event type '{key}' declares no reported cost mapping")
    return mapping


#: How Django reports a uniqueness failure out of ``full_clean``. Its own
#: codes rather than the message text, which is localised and reworded
#: between releases — and rather than a pre-flight ``exists()`` query, which
#: would be a second copy of a constraint the model already declares and would
#: still have to keep this branch for the race it cannot close.
_ALREADY_EXISTS = frozenset({"unique", "unique_together", "unique_for_date"})


def _refuse_invalid(model, conflict=None):
    """``full_clean()``, with the model's complaint rendered as one problem.

    Validation happens at the API door because that is where a tenant's mistake
    can still be reported to the person who made it. The model's ``clean()``
    already states every rule with its reason — the narrowing on a reported
    cost's source kind, the currency's exclusivity, the structured path's
    grammar — so this translates rather than restates: a second copy of any of
    those rules here is a copy that would drift.

    ``conflict`` separates the one refusal that is NOT the caller sending
    something invalid. A key that already exists is a disagreement with state
    the tenant themselves created, and 409 is what tells them to look at their
    catalogue rather than at their request. ``full_clean`` reaches it first —
    it runs ``validate_unique`` before anything hits the database — so without
    this the duplicate would arrive as a 422 and the ``IntegrityError`` branch
    below would only ever fire on a race.
    """
    try:
        model.full_clean()
    except ValidationError as invalid:
        if conflict and _is_a_duplicate(invalid):
            raise Problem("conflict", conflict)
        raise Problem("validation_error", _one_message(invalid))


def _is_a_duplicate(invalid):
    """Is this ValidationError a uniqueness failure and nothing else?

    And nothing else, deliberately: an error carrying a real validation
    complaint alongside a duplicate key must still be reported as the
    validation failure it is, or a caller told only "that key exists" would fix
    the key and meet the other refusal on their second attempt.
    """
    errors = getattr(invalid, "error_dict", None)
    if not errors:
        return False
    return all(error.code in _ALREADY_EXISTS
               for reported in errors.values() for error in reported)


def _one_message(invalid):
    """A ValidationError's field errors as one line, field names kept.

    Kept rather than flattened away because the model raises per-field and the
    caller has to know WHICH field it is being told about — a declaration
    carries two paths and two vocabularies, and "this is not a source kind"
    with no field name attached is a message a tenant cannot act on.
    """
    errors = getattr(invalid, "message_dict", None)
    if not errors:
        return "; ".join(invalid.messages)
    return "; ".join(f"{field}: {' '.join(messages)}"
                     for field, messages in sorted(errors.items()))


def _by_key(model, tenant, key, kind):
    """One tenant-scoped record by key, or a 404 naming the key that missed.

    One helper rather than a lookup per handler, so the message a tenant gets
    for a key that is not there is the same message wherever they meet it —
    and so the tenant scoping is written once. A lookup that forgot it would be
    a cross-tenant read, which is the one direction this surface must never
    point.
    """
    found = model.objects.filter(tenant=tenant, key=key).first()
    if found is None:
        raise Problem("not_found", f"{kind} with key '{key}' not found")
    return found


def _satellite(model, tenant, key, kind):
    """A Provider or an EventCategory named on a declaration, or ``None``.

    The empty string and ``None`` mean different things to a caller — see
    ``EventTypeUpdateIn`` — but both mean "no record" here, and the branch that
    tells them apart belongs to the handler that knows whether an absent field
    is a detach or a no-op.

    A key that names nothing is a 404 rather than an auto-registration: a name
    UBB has never seen must never become permanent billing vocabulary by being
    mentioned.
    """
    return _by_key(model, tenant, key, kind) if key else None


def _saved(model, action, tenant, resource_type, resource_id, metadata,
           conflict):
    """Validate, save and audit one catalogue write, as one act.

    Extracted because it was written five times and each copy spelled its
    conflict message twice — once for the validator's uniqueness failure and
    once for the ``IntegrityError`` underneath it. Two spellings of one
    sentence is two chances to fix only one of them.

    Both refusals are kept, and they are not redundant: ``full_clean`` catches
    the duplicate a tenant can see, and the database catches the one they
    cannot — a concurrent write between the check and the insert. Without the
    second, that race is a 500 rather than the same 409.

    ``metadata`` is called with the SAVED model rather than closing over the
    caller's variable, and that is not a style preference: the caller's name is
    unbound until this returns, so a closure over it raises on the first write.
    Deferred rather than passed as a dict because the serializers read fields
    the save fills in.
    """
    _refuse_invalid(model, conflict=conflict)
    try:
        with transaction.atomic():
            model.save()
            audit_record(action=action, tenant_id=tenant.id,
                         resource_type=resource_type, resource_id=resource_id,
                         metadata=metadata(model))
    except IntegrityError:
        raise Problem("conflict", conflict)
    return model


def _withdrawn(model, action, tenant, resource_type, resource_id, metadata):
    """Delete one catalogue record and record that it went, as one act."""
    with transaction.atomic():
        model.delete()
        audit_record(action=action, tenant_id=tenant.id,
                     resource_type=resource_type, resource_id=resource_id,
                     metadata=metadata)


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------

@event_type_router.get("/providers", response={200: PaginatedProviders})
@role_floor(READ)
def list_providers(request, cursor: str = None, limit: int = _DEFAULT_LIMIT):
    """Every supplier this tenant has declared, retired ones included.

    Retirement governs what may be ATTACHED next and never what may be READ:
    hiding retired suppliers here would make reading last quarter the clever
    path and the wrong answer the easy one.
    """
    _product_check(request)
    return 200, page(Provider.objects.filter(tenant=request.auth.tenant),
                     cursor, limit, serialize=provider_out)


@event_type_router.post("/providers",
                        response={201: ProviderOut, 409: ProblemOut,
                                  422: ProblemOut})
@role_floor(ADMIN)
@records_audit("provider.declared")
def declare_provider(request, payload: ProviderIn):
    """Declare a supplier. The key is the tenant's own handle for it."""
    _product_check(request)
    tenant = request.auth.tenant
    provider = _saved(
        Provider(tenant=tenant, key=payload.key),
        action="provider.declared", tenant=tenant, resource_type="provider",
        resource_id=payload.key,
        metadata=provider_out,
        conflict=f"provider with key '{payload.key}' already exists")
    return 201, provider_out(provider)


@event_type_router.patch("/providers/{key}",
                         response={200: ProviderOut, 404: ProblemOut,
                                   409: ProblemOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("provider.declared", "provider.retired")
def revise_provider(request, key: str, payload: ProviderUpdateIn):
    """Rename a supplier, or retire one — two acts, recorded apart.

    There is no delete. Supplier COGS attribution keys on this record's
    identity, so removing one would silently rewrite what historical postings
    say they cost — the failure a finance owner finds a quarter later and
    cannot repair. Renaming is safe for exactly the same reason the identity is
    not the key: nothing downstream holds the handle.

    Retirement records ``provider.retired`` rather than a second
    ``provider.declared``, because it is a commercial decision to stop offering
    a supplier and not a correction to a name. Where one request does both, the
    retirement is what the ledger is told: it is the consequential half.
    """
    _product_check(request)
    tenant = request.auth.tenant
    provider = _by_key(Provider, tenant, key, "provider")

    changed = []
    retirement_moved = False
    if payload.key is not None and payload.key != provider.key:
        provider.key = payload.key
        changed.append("key")
    if payload.retired is not None:
        was_retired = provider.retired_at is not None
        if payload.retired != was_retired:
            provider.retired_at = timezone.now() if payload.retired else None
            changed.append("retired_at")
            retirement_moved = True
    if not changed:
        return 200, provider_out(provider)

    _saved(
        provider,
        action=("provider.retired" if retirement_moved
                else "provider.declared"),
        tenant=tenant, resource_type="provider", resource_id=provider.key,
        metadata=lambda saved: {"changed": changed, **provider_out(saved)},
        conflict=f"provider with key '{provider.key}' already exists")
    return 200, provider_out(provider)


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

@event_type_router.get("/event-categories",
                       response={200: PaginatedEventCategories})
@role_floor(READ)
def list_event_categories(request, cursor: str = None,
                          limit: int = _DEFAULT_LIMIT):
    """Every category this tenant has declared. One level, current."""
    _product_check(request)
    return 200, page(EventCategory.objects.filter(tenant=request.auth.tenant),
                     cursor, limit, serialize=event_category_out)


@event_type_router.post("/event-categories",
                        response={201: EventCategoryOut, 409: ProblemOut,
                                  422: ProblemOut})
@role_floor(ADMIN)
@records_audit("event_category.declared")
def declare_event_category(request, payload: EventCategoryIn):
    """Declare a category. Analytics-only: it can never reach a cost or price."""
    _product_check(request)
    tenant = request.auth.tenant
    category = _saved(
        EventCategory(tenant=tenant, key=payload.key),
        action="event_category.declared", tenant=tenant,
        resource_type="event_category", resource_id=payload.key,
        metadata=event_category_out,
        conflict=f"event category with key '{payload.key}' already exists")
    return 201, event_category_out(category)


@event_type_router.delete("/event-categories/{key}",
                          response={204: None, 404: ProblemOut,
                                    409: ProblemOut})
@role_floor(ADMIN)
@records_audit("event_category.withdrawn")
def withdraw_event_category(request, key: str):
    """Withdraw a category, unless an Event Type still groups under it.

    A real delete rather than a retirement, and the asymmetry with the supplier
    above is the point rather than an inconsistency: a Provider earns
    ``retired_at`` because historical COGS attribution keys on it, and a
    category reaches no money by any path, so there is no past reading to
    protect. Refused while in use, because ``PROTECT`` on the Event Type's
    relation would otherwise surface as a 500.
    """
    _product_check(request)
    tenant = request.auth.tenant
    category = _by_key(EventCategory, tenant, key, "event category")
    in_use = EventType.objects.filter(category=category).count()
    if in_use:
        raise Problem(
            "conflict",
            f"event category '{key}' still groups {in_use} event type(s); "
            f"move them to another category first")
    _withdrawn(category, action="event_category.withdrawn", tenant=tenant,
               resource_type="event_category", resource_id=key,
               metadata={"key": key})
    return 204, None


# ---------------------------------------------------------------------------
# Event Types
# ---------------------------------------------------------------------------

@event_type_router.get("/event-types", response={200: PaginatedEventTypes})
@role_floor(READ)
def list_event_types(request, cursor: str = None, limit: int = _DEFAULT_LIMIT):
    """The tenant's metered vocabulary, each declaration whole."""
    _product_check(request)
    return 200, page(_declarations(request.auth.tenant), cursor, limit,
                     serialize=event_type_out)


@event_type_router.get("/event-types/{key}",
                       response={200: EventTypeOut, 404: ProblemOut})
@role_floor(READ)
def get_event_type(request, key: str):
    """One declaration, whole — the read a Code Builder generates from."""
    _product_check(request)
    return 200, event_type_out(_declaration(request.auth.tenant, key))


@event_type_router.post("/event-types",
                        response={201: EventTypeOut, 404: ProblemOut,
                                  409: ProblemOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("event_type.declared")
def declare_event_type(request, payload: EventTypeIn):
    """Register an Event Type. It arrives as a draft, always.

    Never auto-registered from a recorded event, and that is the rule rather
    than an implementation detail: a typo that registered itself would become
    permanent billing vocabulary. An Event Type UBB has never seen is
    quarantined and replayed instead.
    """
    _product_check(request)
    tenant = request.auth.tenant
    event_type = _saved(
        EventType(tenant=tenant, key=payload.key,
                  costing_method=payload.costing_method,
                  provider=_satellite(Provider, tenant, payload.provider_key,
                                      "provider"),
                  category=_satellite(EventCategory, tenant,
                                      payload.category_key, "event category"),
                  source_shape_id=payload.source_shape_id,
                  source_shape_label=payload.source_shape_label),
        action="event_type.declared", tenant=tenant,
        resource_type="event_type", resource_id=payload.key,
        metadata=event_type_out,
        conflict=f"event type with key '{payload.key}' already exists")
    return 201, event_type_out(event_type)


@event_type_router.patch("/event-types/{key}",
                         response={200: EventTypeOut, 404: ProblemOut,
                                   409: ProblemOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("event_type.declared")
def revise_event_type(request, key: str, payload: EventTypeUpdateIn):
    """Edit a declaration. Changing a pinned element returns it to draft.

    The un-publishing is the model's, not this handler's, and deliberately so:
    it is a rule about what a change MEANS, and anything a caller has to
    remember to route through is a rule that holds until the first caller who
    does not. What this decides is what an absent field means — untouched,
    never cleared — and that an empty string detaches a satellite, because "no
    supplier" is a state a tenant reaches on purpose.
    """
    _product_check(request)
    tenant = request.auth.tenant
    event_type = _declaration(tenant, key)

    changed = []
    if payload.costing_method is not None:
        event_type.costing_method = payload.costing_method
        changed.append("costing_method")
    if payload.provider_key is not None:
        event_type.provider = _satellite(Provider, tenant,
                                         payload.provider_key, "provider")
        changed.append("provider")
    if payload.category_key is not None:
        event_type.category = _satellite(EventCategory, tenant,
                                         payload.category_key,
                                         "event category")
        changed.append("category")
    if payload.source_shape_id is not None:
        event_type.source_shape_id = payload.source_shape_id
        changed.append("source_shape_id")
    if payload.source_shape_label is not None:
        event_type.source_shape_label = payload.source_shape_label
        changed.append("source_shape_label")
    if not changed:
        return 200, event_type_out(event_type)

    _saved(event_type, action="event_type.declared", tenant=tenant,
           resource_type="event_type", resource_id=event_type.key,
           metadata=lambda saved: {"changed": changed, **event_type_out(saved)},
           conflict=f"event type with key '{event_type.key}' already exists")
    return 200, event_type_out(_declaration(tenant, event_type.key))


@event_type_router.post("/event-types/{key}/publish",
                        response={200: EventTypeOut, 404: ProblemOut,
                                  409: ProblemOut})
@role_floor(ADMIN)
@records_audit("event_type.published")
def publish_event_type(request, key: str):
    """Publish the declaration, or refuse and say what is missing.

    A refusal rather than a partial publication: the two outcomes a caller must
    tell apart are published and not-published, and an incomplete mapping
    published anyway generates an integration that computes no cost at all.
    What is missing travels on the 409 so the caller can say which.
    """
    _product_check(request)
    tenant = request.auth.tenant
    event_type = _declaration(tenant, key)
    try:
        with transaction.atomic():
            event_type.publish()
            audit_record(
                action="event_type.published", tenant_id=tenant.id,
                resource_type="event_type", resource_id=event_type.key,
                metadata={"published_revision": event_type.published_revision,
                          **event_type_out(event_type)})
    except DeclarationIncomplete as incomplete:
        raise Problem("conflict", str(incomplete))
    return 200, event_type_out(_declaration(tenant, key))


# ---------------------------------------------------------------------------
# Declared quantities
# ---------------------------------------------------------------------------

@event_type_router.get("/event-types/{key}/measurements",
                       response={200: PaginatedMeasurements, 404: ProblemOut})
@role_floor(READ)
def list_measurements(request, key: str, cursor: str = None,
                      limit: int = _DEFAULT_LIMIT):
    """The quantities this Event Type declares."""
    _product_check(request)
    event_type = _declaration(request.auth.tenant, key)
    return 200, page(event_type.measurements.all(), cursor, limit,
                     serialize=measurement_out)


@event_type_router.put("/event-types/{key}/measurements/{code}",
                       response={200: MeasurementOut, 201: MeasurementOut,
                                 404: ProblemOut, 409: ProblemOut,
                                 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("measurement.declared")
def declare_measurement(request, key: str, code: str, payload: MeasurementIn):
    """Declare or re-declare one quantity beneath an Event Type.

    The same name on two Event Types is two independent declarations, so this
    is keyed on the pair and never on the code alone: a tenant's Gemini and
    OpenAI integrations never have to agree about spelling to both be correct.

    Declaring one under a PUBLISHED Event Type revises the publication — the
    model does that, on the same footing as an edit, because a published
    declaration that grows a required quantity is a different declaration from
    the one a tenant generated their integration against.
    """
    _product_check(request)
    tenant = request.auth.tenant
    event_type = _declaration(tenant, key)
    measurement = Measurement.objects.filter(
        event_type=event_type, code=code).first()
    created = measurement is None
    if created:
        measurement = Measurement(event_type=event_type, code=code)

    measurement.display_name = payload.display_name
    measurement.value_type = payload.value_type
    measurement.unit = payload.unit
    measurement.required_for_costing = payload.required_for_costing
    measurement.source_kind = payload.source_kind
    measurement.source_path = list(payload.source_path)

    _saved(measurement, action="measurement.declared", tenant=tenant,
           resource_type="measurement",
           resource_id=f"{event_type.key}:{code}",
           metadata=lambda saved: {"event_type_key": event_type.key,
                                  **measurement_out(saved)},
           conflict=f"event type '{key}' is already declaring a measurement "
                    f"with code '{code}'")
    return (201 if created else 200), measurement_out(measurement)


@event_type_router.delete("/event-types/{key}/measurements/{code}",
                          response={204: None, 404: ProblemOut,
                                    409: ProblemOut})
@role_floor(ADMIN)
@records_audit("measurement.withdrawn")
def withdraw_measurement(request, key: str, code: str):
    """Withdraw one declared quantity, unless a rate still prices it.

    A real delete rather than the data plane's soft delete: that rule protects
    rows carrying money history, and a part of a declaration carries none.

    Refused while a rate names it: a priced rule against a quantity you no
    longer declare is a rule that can price nothing, so either the rule goes
    first or the declaration stays.
    """
    _product_check(request)
    tenant = request.auth.tenant
    event_type = _declaration(tenant, key)
    measurement = Measurement.objects.filter(
        event_type=event_type, code=code).first()
    if measurement is None:
        raise Problem(
            "not_found",
            f"event type '{key}' declares no measurement with code '{code}'")
    # The same shape `withdraw_event_category` above states, and checked ahead
    # of the delete for the same reason: `PROTECT` on the rate's reference
    # (#326) would otherwise surface as a 500. Withdrawing the declaration and quietly deactivating the
    # tenant's rates was the alternative — and beyond rewriting their pricing on
    # their behalf, it is not even available: `SET_NULL` would leave a row
    # referencing nothing and carrying no name, which `ck_rate_names_one_quantity`
    # refuses, so the 500 would simply move.
    #
    # NOT SCOPED TO THIS TENANT, deliberately: what must be refused is exactly
    # what `PROTECT` would block, and that is every rate pointing here whoever
    # owns it. No supported path creates a cross-tenant one — the route and the
    # conversion both resolve within the tenant — and the detail below carries no
    # count, so a row this repository cannot create still cannot leak a number.
    if Rate.objects.filter(measurement=measurement).exists():
        raise Problem(
            "conflict",
            f"a rate prices '{code}'. Delete it first, or keep the "
            f"declaration: a rate names the quantity it prices, so a quantity "
            f"nobody declares is a rate that prices nothing.")
    _withdrawn(measurement, action="measurement.withdrawn", tenant=tenant,
               resource_type="measurement",
               resource_id=f"{event_type.key}:{code}",
               metadata={"event_type_key": event_type.key, "code": code})
    return 204, None


# ---------------------------------------------------------------------------
# The reported supplier cost
# ---------------------------------------------------------------------------

@event_type_router.get("/event-types/{key}/reported-cost-mapping",
                       response={200: ReportedCostMappingOut,
                                 404: ProblemOut})
@role_floor(READ)
def get_reported_cost_mapping(request, key: str):
    """Where this Event Type's supplier cost is read from, if it is declared."""
    _product_check(request)
    return 200, reported_cost_mapping_out(
        _mapping(_declaration(request.auth.tenant, key), key))


@event_type_router.put("/event-types/{key}/reported-cost-mapping",
                       response={200: ReportedCostMappingOut,
                                 201: ReportedCostMappingOut, 404: ProblemOut,
                                 409: ProblemOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("reported_cost_mapping.declared")
def declare_reported_cost_mapping(request, key: str,
                                  payload: ReportedCostMappingIn):
    """Declare where a supplier's own cost figure is read from. One per type.

    A sibling of the quantities rather than one of them, which is why it is a
    PUT on a singular path: money with a currency does not fit a shape built
    for a quantity and its unit, and there is exactly one such number per
    Event Type. It carries its own action for the reason each satellite does —
    the ledger's `resource_type` names which record moved, and an action
    naming the Event Type over a row that is the mapping would make the two
    disagree.
    """
    _product_check(request)
    tenant = request.auth.tenant
    event_type = _declaration(tenant, key)
    mapping = getattr(event_type, REPORTED_COST_MAPPING, None)
    created = mapping is None
    if created:
        mapping = ReportedCostMapping(event_type=event_type)

    mapping.source_kind = payload.source_kind
    mapping.amount_representation = payload.amount_representation
    mapping.source_path = list(payload.source_path)
    mapping.currency_path = list(payload.currency_path)
    mapping.currency = payload.currency

    _saved(mapping, action="reported_cost_mapping.declared", tenant=tenant,
           resource_type="reported_cost_mapping", resource_id=event_type.key,
           metadata=lambda saved: {"event_type_key": event_type.key,
                                  **reported_cost_mapping_out(saved)},
           conflict=f"event type '{key}' is already declaring a reported cost "
                    f"mapping")
    return (201 if created else 200), reported_cost_mapping_out(mapping)


@event_type_router.delete("/event-types/{key}/reported-cost-mapping",
                          response={204: None, 404: ProblemOut})
@role_floor(ADMIN)
@records_audit("reported_cost_mapping.withdrawn")
def withdraw_reported_cost_mapping(request, key: str):
    """Withdraw the mapping. A `reported` declaration then cannot publish.

    Not refused here, and that is deliberate: the blocker is reported on the
    declaration itself and enforced where publication happens, so withdrawing a
    mapping in order to redeclare it is an ordinary edit rather than a sequence
    a tenant has to work around.
    """
    _product_check(request)
    tenant = request.auth.tenant
    event_type = _declaration(tenant, key)
    _withdrawn(_mapping(event_type, key),
               action="reported_cost_mapping.withdrawn", tenant=tenant,
               resource_type="reported_cost_mapping",
               resource_id=event_type.key,
               metadata={"event_type_key": event_type.key})
    return 204, None
