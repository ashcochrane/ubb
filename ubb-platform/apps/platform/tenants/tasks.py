"""Sandbox reset (F4.4).

``reset_sandbox_tenant`` wipes a sandbox tenant's domain data while preserving
the Tenant row and its API keys (and, with ``keep_config=True``, the tenant's
configuration rows) so the same test keys keep working after the reset.

ADR-001: the platform kernel must not import product modules, and a reset that
had to name every product model would silently leak rows whenever a new model
shipped. The sweep therefore discovers tenant-scoped models GENERICALLY via
Django's app registry (any concrete model with a FK/O2O to Tenant) and config
models are addressed by their ``app_label.ModelName`` labels — no product
imports, and new tenant-scoped models are wiped automatically.
"""
import logging

from celery import shared_task
from django.apps import apps as django_apps
from django.db import transaction

from apps.platform.tenants.models import Tenant

logger = logging.getLogger(__name__)

# Always preserved: the sandbox Tenant itself + its API keys (test keys must
# survive a reset). Customer is handled separately (PROTECT seat hierarchy).
_SKIP_LABELS = frozenset({
    "tenants.Tenant",
    "tenants.TenantApiKey",
    "customers.Customer",
})

# Tenant-level CONFIG rows preserved when keep_config=True (the default).
# Customer-scoped config (per-customer rate cards, markups, budgets, billing
# profiles, auto-top-up configs) always dies with the customers it points at.
CONFIG_MODEL_LABELS = frozenset({
    "pricing.Rate",
    "pricing.TenantMarkup",
    "subscriptions.TenantBillingPlan",
    "subscriptions.MarginThresholdConfig",
    "gating.BudgetConfig",
    "gating.RiskConfig",
    "invoicing.PostpaidUsageConfig",
    "tenant_billing.BillingTenantConfig",
    "tenant_billing.ProductFeeConfig",
    "events.TenantWebhookConfig",
    "referrals.ReferralProgram",
})


def _tenant_fk_name(model):
    """Name of the model's FK/O2O to Tenant, or None if not tenant-scoped."""
    for field in model._meta.concrete_fields:
        if field.is_relation and field.related_model is Tenant:
            return field.name
    return None


def _wipe_manager(model):
    """Unfiltered manager: soft-delete models hide rows from .objects."""
    return getattr(model, "all_objects", model._base_manager)


def reset_sandbox_tenant_sync(tenant_id, keep_config=True,
                              actor_kind="", actor_id="", actor_display=""):
    """Synchronous body of the reset (directly callable in tests).

    ``actor_*`` are the reset-initiating principal, threaded by value from the
    request (a worker has no request-scoped actor). They attribute the
    ``sandbox.reset`` audit entry; empty => the reserved ``system`` kind.
    """
    tenant = Tenant.objects.filter(id=tenant_id, is_sandbox=True).first()
    if tenant is None:
        # Defense: a live tenant id (or unknown id) must no-op LOUDLY.
        logger.error(
            "sandbox.reset_refused: tenant is not a sandbox",
            extra={"data": {"tenant_id": str(tenant_id)}},
        )
        return {"status": "refused", "deleted": {}}

    # Quiesce: verify_key filters tenant__is_active=True, so sandbox traffic
    # 401s for the duration of the wipe. Queryset update — no clean()/signals.
    Tenant.objects.filter(id=tenant.id).update(is_active=False)

    deleted = {}
    errors = []

    def _wipe(label, fn):
        try:
            count, per_model = fn()
            deleted[label] = count
            if count:
                logger.info("sandbox.reset_deleted", extra={"data": {
                    "tenant_id": str(tenant.id), "model": label,
                    "deleted": count, "breakdown": {k: v for k, v in per_model.items() if v}}})
        except Exception as exc:  # noqa: BLE001 — every failure must be loud + non-fatal
            errors.append((label, repr(exc)))
            logger.exception(
                "sandbox.reset_delete_failed",
                extra={"data": {"tenant_id": str(tenant.id), "model": label}},
            )

    # 1. Customers: seats BEFORE parents (Customer.parent is PROTECT), via the
    #    unfiltered manager (soft-deleted seats would otherwise block their
    #    business). Queryset .delete() bypasses the insert-only UsageEvent
    #    save guard; cascades take wallets, transactions, grants, usage
    #    events, runs, invoices, subscriptions, referrals etc. with them.
    Customer = django_apps.get_model("customers", "Customer")
    _wipe("customers.Customer[seats]",
          lambda: Customer.all_objects.filter(tenant=tenant, parent__isnull=False).delete())
    _wipe("customers.Customer",
          lambda: Customer.all_objects.filter(tenant=tenant).delete())

    # 2. Outbox: OutboxEvent.tenant_id is a bare UUID (no FK) — never reached
    #    by any cascade. HandlerCheckpoint + WebhookDeliveryAttempt cascade.
    OutboxEvent = django_apps.get_model("events", "OutboxEvent")
    _wipe("events.OutboxEvent",
          lambda: OutboxEvent.objects.filter(tenant_id=tenant.id).delete())

    # 3. Generic sweep: every remaining concrete model with a FK/O2O to Tenant.
    for model in django_apps.get_models():
        label = model._meta.label
        if label in _SKIP_LABELS:
            continue
        if keep_config and label in CONFIG_MODEL_LABELS:
            continue
        fk_name = _tenant_fk_name(model)
        if fk_name is None:
            continue
        manager = _wipe_manager(model)
        _wipe(label, lambda m=manager, f=fk_name: m.filter(**{f: tenant}).delete())

    if errors:
        # Leave the sandbox INACTIVE: a half-wiped sandbox must not serve
        # traffic. The task is rerunnable — re-enqueue after fixing the cause.
        logger.error("sandbox.reset_failed", extra={"data": {
            "tenant_id": str(tenant.id), "errors": errors}})
        raise RuntimeError(f"sandbox reset for {tenant.id} failed on: {errors}")

    from apps.platform.audit.actors import Actor
    from apps.platform.audit.ledger import record as audit_record
    from apps.platform.audit.models import AuditRecord
    from apps.platform.events.outbox import write_event
    from apps.platform.events.schemas import SandboxResetCompleted

    with transaction.atomic():
        Tenant.objects.filter(id=tenant.id).update(is_active=True)
        write_event(SandboxResetCompleted(
            tenant_id=str(tenant.id), keep_config=keep_config))
        # Audit-clear (ADR-004): the ledger has no FK to Tenant, so the generic
        # sweep never reaches it — clear the sandbox's own entries here, then
        # record THIS reset as the first entry of the fresh history (written
        # after the clear so it survives it). Attributed to the threaded actor.
        AuditRecord.objects.filter(tenant_id=tenant.id).delete()
        actor = (Actor(kind=actor_kind, id=actor_id, display=actor_display)
                 if actor_kind else None)
        audit_record(
            action="sandbox.reset", tenant_id=tenant.id,
            resource_type="sandbox", resource_id=tenant.id, actor=actor,
            metadata={"keep_config": keep_config,
                      "deleted": {k: v for k, v in deleted.items() if v}})

    logger.info("sandbox.reset_completed", extra={"data": {
        "tenant_id": str(tenant.id), "keep_config": keep_config,
        "deleted": {k: v for k, v in deleted.items() if v}}})
    return {"status": "completed", "deleted": deleted}


@shared_task(queue="ubb_events")
def reset_sandbox_tenant(tenant_id, keep_config=True,
                         actor_kind="", actor_id="", actor_display=""):
    """Celery entrypoint for POST /api/v1/sandbox/reset."""
    return reset_sandbox_tenant_sync(
        tenant_id, keep_config=keep_config, actor_kind=actor_kind,
        actor_id=actor_id, actor_display=actor_display)
