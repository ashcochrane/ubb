from datetime import timedelta
from typing import Optional

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from ninja import Router, Schema, Field

from core.auth import ADMIN, ApiKeyAuth, READ, role_floor
from core.identifiers import UUIDIdentifier
from core.pagination import paginate
from core.problems import Problem, ProblemOut
from core.responses import StatusResponse
from core.url_validation import validate_webhook_url
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.marker import records_audit
from apps.platform.events.webhook_models import (
    TenantWebhookConfig,
    WebhookDeliveryAttempt,
)
from apps.platform.events.catalog import is_valid_event_selector

# Rotation overlap window bounds (hours): long enough that a receiver has time
# to cut over, capped so a stale retiring secret can't linger indefinitely.
_DEFAULT_OVERLAP_HOURS = 24
_MAX_OVERLAP_HOURS = 168  # one week

# The (tenant, url) natural-identity collision message — one string, raised from
# both the pre-check and the DB-constraint race, in create and PATCH alike.
_URL_CONFLICT_DETAIL = "a webhook config for this url already exists"


class WebhookConfigCreateRequest(Schema):
    url: str = Field(max_length=500)
    secret: str = Field(min_length=32, max_length=255)
    # Required and non-empty — there is no implicit "subscribe to everything".
    # Pass ["*"] to opt in to all events, or specific types. See events/catalog.py.
    event_types: list[str] = Field(min_length=1)
    is_active: bool = True


class WebhookConfigUpdateRequest(Schema):
    # Every field optional — PATCH applies only what is sent (exclude_unset).
    # `secret` is deliberately absent: it is untouchable via PATCH and moves
    # only through the rotation endpoint (#83).
    url: Optional[str] = Field(default=None, max_length=500)
    event_types: Optional[list[str]] = None
    is_active: Optional[bool] = None


class WebhookSecretRotateRequest(Schema):
    new_secret: str = Field(min_length=32, max_length=255)
    overlap_hours: int = Field(
        default=_DEFAULT_OVERLAP_HOURS, ge=1, le=_MAX_OVERLAP_HOURS)


class WebhookConfigResponse(Schema):
    id: str
    url: str
    event_types: list[str]
    is_active: bool
    created_at: str
    # When the retiring secret stops signing (null when no rotation is in
    # flight). The secret itself is never serialised.
    retiring_secret_expires_at: Optional[str] = None


class WebhookConfigListResponse(Schema):
    data: list[WebhookConfigResponse]
    next_cursor: Optional[str] = None
    has_more: bool


class WebhookDeliveryResponse(Schema):
    id: str
    event_id: str
    event_type: str
    status_code: Optional[int] = None
    success: bool
    error_message: str
    created_at: str


class WebhookDeliveryListResponse(Schema):
    data: list[WebhookDeliveryResponse]
    next_cursor: Optional[str] = None
    has_more: bool


webhook_router = Router(auth=ApiKeyAuth())


def _serialize(config):
    return {
        "id": str(config.id),
        "url": config.url,
        "event_types": config.event_types,
        "is_active": config.is_active,
        "created_at": config.created_at.isoformat(),
        "retiring_secret_expires_at": (
            config.retiring_secret_expires_at.isoformat()
            if config.retiring_secret_expires_at else None),
    }


def _serialize_delivery(attempt):
    return {
        "id": str(attempt.id),
        "event_id": str(attempt.outbox_event_id),
        "event_type": attempt.outbox_event.event_type,
        "status_code": attempt.status_code,
        "success": attempt.success,
        "error_message": attempt.error_message,
        "created_at": attempt.created_at.isoformat(),
    }


def _validate_event_types(event_types):
    """Shared create/PATCH validation: non-empty and every selector known."""
    if not event_types:
        raise Problem(
            "validation_error",
            "event_types cannot be empty — a webhook subscribed to nothing "
            'would deliver nothing. Use ["*"] for all events.')
    unknown = sorted({t for t in event_types if not is_valid_event_selector(t)})
    if unknown:
        raise Problem(
            "validation_error",
            f"Unknown event type(s): {', '.join(unknown)}. "
            'Use "*" to subscribe to all events, or see the event catalog for valid types.')


def _url_already_configured(tenant, url):
    """Pre-check for the (tenant, url) natural identity — the DB constraint
    uq_webhook_config_tenant_url is the race-safe authority."""
    return TenantWebhookConfig.objects.filter(tenant=tenant, url=url).exists()


@webhook_router.post(
    "/configs",
    response={201: WebhookConfigResponse, 409: ProblemOut, 422: ProblemOut},
)
@role_floor(ADMIN)
@records_audit("webhook_config.created")
def create_webhook_config(request, payload: WebhookConfigCreateRequest):
    try:
        validate_webhook_url(payload.url)
    except ValueError as e:
        raise Problem("validation_error", str(e))

    _validate_event_types(payload.event_types)

    tenant = request.auth.tenant
    if _url_already_configured(tenant, payload.url):
        raise Problem("conflict", _URL_CONFLICT_DETAIL)

    try:
        with transaction.atomic():
            config = TenantWebhookConfig.objects.create(
                tenant=tenant,
                url=payload.url,
                secret=payload.secret,
                event_types=payload.event_types,
                is_active=payload.is_active,
            )
            # Curated metadata only — never the signing secret.
            audit_record(
                action="webhook_config.created", tenant_id=tenant.id,
                resource_type="webhook_config", resource_id=config.id,
                metadata={"url": config.url,
                          "event_types": config.event_types,
                          "is_active": config.is_active})
    except IntegrityError:
        # Race: a concurrent create won uq_webhook_config_tenant_url between
        # the pre-check and the insert.
        raise Problem("conflict", _URL_CONFLICT_DETAIL)

    return 201, _serialize(config)


@webhook_router.get(
    "/configs",
    response={200: WebhookConfigListResponse, 400: ProblemOut},
)
@role_floor(READ)
def list_webhook_configs(request, cursor: str = None, limit: int = 50):
    configs, next_cursor, has_more = paginate(
        TenantWebhookConfig.objects.filter(tenant=request.auth.tenant),
        cursor, limit)

    return {
        "data": [_serialize(c) for c in configs],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@webhook_router.delete("/configs/{config_id}", response=StatusResponse)
@role_floor(ADMIN)
@records_audit("webhook_config.deleted")
def delete_webhook_config(request, config_id: UUIDIdentifier):
    config = get_object_or_404(
        TenantWebhookConfig,
        id=config_id,
        tenant=request.auth.tenant,
    )
    # Capture before delete() — Django nulls the instance pk on deletion; the
    # signing secret is never captured.
    deleted_id = config.id
    deleted_url = config.url
    with transaction.atomic():  # delete + audit land together (ADR-004)
        config.delete()
        audit_record(
            action="webhook_config.deleted", tenant_id=request.auth.tenant.id,
            resource_type="webhook_config", resource_id=deleted_id,
            metadata={"config_id": str(config_id), "url": deleted_url})
    return {"status": "deleted"}


@webhook_router.patch(
    "/configs/{config_id}",
    response={200: WebhookConfigResponse, 404: ProblemOut, 409: ProblemOut, 422: ProblemOut},
)
@role_floor(ADMIN)
@records_audit("webhook_config.updated")
def update_webhook_config(request, config_id: UUIDIdentifier, payload: WebhookConfigUpdateRequest):
    """Edit url / event_types / pause-resume in place — no delete-and-recreate.

    The secret is not a field here: it is untouchable via PATCH and moves only
    through the rotation endpoint (#83)."""
    tenant = request.auth.tenant
    config = get_object_or_404(TenantWebhookConfig, id=config_id, tenant=tenant)

    # Only the fields the client actually sent — the PATCH contract.
    changes = payload.dict(exclude_unset=True)

    if "url" in changes:
        try:
            validate_webhook_url(changes["url"])
        except ValueError as e:
            raise Problem("validation_error", str(e))
    if "event_types" in changes:
        _validate_event_types(changes["event_types"])

    # (tenant, url) natural identity (#63): only a MOVE to a different url can
    # collide — pre-check, then let the DB constraint settle the race (mirrors
    # create). Re-PATCHing the same url is a no-op, not a conflict.
    if "url" in changes and changes["url"] != config.url and \
            _url_already_configured(tenant, changes["url"]):
        raise Problem("conflict", _URL_CONFLICT_DETAIL)

    if not changes:  # empty PATCH — nothing to persist or audit.
        return 200, _serialize(config)

    for field, value in changes.items():
        setattr(config, field, value)

    try:
        with transaction.atomic():
            config.save(update_fields=[*changes, "updated_at"])
            audit_record(
                action="webhook_config.updated", tenant_id=tenant.id,
                resource_type="webhook_config", resource_id=config.id,
                metadata={"updated_fields": sorted(changes),
                          "url": config.url,
                          "event_types": config.event_types,
                          "is_active": config.is_active})
    except IntegrityError:
        raise Problem("conflict", _URL_CONFLICT_DETAIL)

    return 200, _serialize(config)


@webhook_router.post(
    "/configs/{config_id}/rotate-secret",
    response={200: WebhookConfigResponse, 404: ProblemOut, 422: ProblemOut},
)
@role_floor(ADMIN)
@records_audit("webhook_config.secret_rotated")
def rotate_webhook_secret(request, config_id: UUIDIdentifier, payload: WebhookSecretRotateRequest):
    """Two-secret overlap rotation: the current secret keeps signing a second
    `v1=` candidate for `overlap_hours` while the new one takes over, so a
    receiver verifies with zero downtime. Rotating again mid-window replaces
    the retiring secret (#83)."""
    tenant = request.auth.tenant
    config = get_object_or_404(TenantWebhookConfig, id=config_id, tenant=tenant)

    if payload.new_secret == config.secret:
        raise Problem(
            "validation_error", "new secret must differ from the current secret.")

    with transaction.atomic():
        config.apply_secret_rotation(
            payload.new_secret, overlap=timedelta(hours=payload.overlap_hours))
        config.save(update_fields=[
            "secret", "retiring_secret", "retiring_secret_expires_at", "updated_at"])
        # Curated metadata only — the secret material NEVER reaches the ledger
        # (ADR-004 §4); just that a rotation happened and when it closes.
        audit_record(
            action="webhook_config.secret_rotated", tenant_id=tenant.id,
            resource_type="webhook_config", resource_id=config.id,
            metadata={"overlap_hours": payload.overlap_hours,
                      "retiring_secret_expires_at":
                          config.retiring_secret_expires_at.isoformat()})

    return 200, _serialize(config)


@webhook_router.get(
    "/configs/{config_id}/deliveries",
    response={200: WebhookDeliveryListResponse, 400: ProblemOut, 404: ProblemOut},
)
@role_floor(READ)
def list_webhook_deliveries(request, config_id: UUIDIdentifier, cursor: str = None, limit: int = 50):
    """The self-serve debugging surface: per-endpoint delivery attempts —
    successes, retries, and dead-letters — newest first, in the house cursor
    envelope, over the per-endpoint checkpointed records (#76)."""
    # 404 for another tenant's config (or a missing one) — same posture as
    # delete, so delivery history can't leak across tenants.
    config = get_object_or_404(TenantWebhookConfig, id=config_id, tenant=request.auth.tenant)
    attempts, next_cursor, has_more = paginate(
        WebhookDeliveryAttempt.objects.filter(webhook_config=config)
            .select_related("outbox_event"),
        cursor, limit)
    return {
        "data": [_serialize_delivery(a) for a in attempts],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }
