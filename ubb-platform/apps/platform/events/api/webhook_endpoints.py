from typing import Optional

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from ninja import Router, Schema, Field

from core.auth import ADMIN, ApiKeyAuth, READ, role_floor
from core.pagination import paginate
from core.problems import Problem, ProblemOut
from core.url_validation import validate_webhook_url
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.marker import records_audit
from apps.platform.events.webhook_models import TenantWebhookConfig
from apps.platform.events.catalog import is_valid_event_selector


class WebhookConfigCreateRequest(Schema):
    url: str = Field(max_length=500)
    secret: str = Field(min_length=32, max_length=255)
    # Required and non-empty — there is no implicit "subscribe to everything".
    # Pass ["*"] to opt in to all events, or specific types. See events/catalog.py.
    event_types: list[str] = Field(min_length=1)
    is_active: bool = True


class WebhookConfigResponse(Schema):
    id: str
    url: str
    event_types: list[str]
    is_active: bool
    created_at: str


class WebhookConfigListResponse(Schema):
    data: list[WebhookConfigResponse]
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
    }


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

    unknown = sorted({t for t in payload.event_types if not is_valid_event_selector(t)})
    if unknown:
        raise Problem(
            "validation_error",
            f"Unknown event type(s): {', '.join(unknown)}. "
            'Use "*" to subscribe to all events, or see the event catalog for valid types.',
        )

    tenant = request.auth.tenant
    if _url_already_configured(tenant, payload.url):
        raise Problem("conflict", "a webhook config for this url already exists")

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
        raise Problem("conflict", "a webhook config for this url already exists")

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


@webhook_router.delete("/configs/{config_id}")
@role_floor(ADMIN)
@records_audit("webhook_config.deleted")
def delete_webhook_config(request, config_id: str):
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
