from ninja import NinjaAPI, Schema

from core.auth import ApiKeyAuth
from apps.platform.events.webhook_models import TenantWebhookConfig


class WebhookConfigCreateRequest(Schema):
    url: str
    secret: str
    event_types: list[str] = []
    is_active: bool = True


class WebhookConfigResponse(Schema):
    id: str
    url: str
    event_types: list[str]
    is_active: bool
    created_at: str


webhook_api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_webhooks_v1")


@webhook_api.post("/configs", response={201: WebhookConfigResponse})
def create_webhook_config(request, payload: WebhookConfigCreateRequest):
    config = TenantWebhookConfig.objects.create(
        tenant=request.auth.tenant,
        url=payload.url,
        secret=payload.secret,
        event_types=payload.event_types,
        is_active=payload.is_active,
    )
    return 201, {
        "id": str(config.id),
        "url": config.url,
        "event_types": config.event_types,
        "is_active": config.is_active,
        "created_at": config.created_at.isoformat(),
    }


@webhook_api.get("/configs")
def list_webhook_configs(request):
    configs = TenantWebhookConfig.objects.filter(
        tenant=request.auth.tenant,
    ).order_by("-created_at")
    return {
        "data": [
            {
                "id": str(c.id),
                "url": c.url,
                "event_types": c.event_types,
                "is_active": c.is_active,
                "created_at": c.created_at.isoformat(),
            }
            for c in configs
        ],
    }


@webhook_api.delete("/configs/{config_id}")
def delete_webhook_config(request, config_id: str):
    from django.shortcuts import get_object_or_404

    config = get_object_or_404(
        TenantWebhookConfig,
        id=config_id,
        tenant=request.auth.tenant,
    )
    config.delete()
    return {"status": "deleted"}
