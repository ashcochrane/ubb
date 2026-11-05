from django.contrib import admin

from apps.platform.tenants.models import (
    PaymentRailActivation,
    Tenant,
    TenantApiKey,
)
from core.transitions import FROZEN


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    """A tenant is inspected and maintained here, never deleted (R10 Stage C4,
    PLAN §7 item 41, Ruling C).

    Deleting a tenant row CASCADES to every one of its customers
    (``Customer.tenant``), a database HARD delete — the very thing the Customer
    admin no longer offers (its bulk ``delete_selected`` is gone, and its single
    delete is the canonical soft delete). Left here, it would be the route
    around that ruling, and it would take each customer's wallet, invoices,
    subscriptions and history with no lifecycle event. Tenant deletion is not
    a supported v1 operation: there is no tenant teardown with its own
    economic and lifecycle semantics, so this admin has no delete permission —
    no single-object delete page, and with it Django withdraws the bulk
    ``delete_selected`` action. Every other inspection and maintenance edit is
    unchanged."""

    list_display = ("name", "is_active", "platform_fee_percentage", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentRailActivation)
class PaymentRailActivationAdmin(admin.ModelAdmin):
    """Where a named approver records a rail's activation (ADR-0008 §6), and
    where its flag is turned.

    The evidence is read-only once recorded — the columns the model declares
    `FROZEN`, which the database holds anyway — and nothing here deletes an
    activation: it is historical evidence, and a rail is disabled by its flag
    (the owner's ruling 2).
    """

    list_display = ("rail", "environment", "enabled", "activated_at",
                    "approved_by")
    list_filter = ("rail", "environment", "enabled")

    EVIDENCE = tuple(
        column for column, transition_class
        in PaymentRailActivation.transition_classes.items()
        if transition_class == FROZEN)

    def get_readonly_fields(self, request, obj=None):
        return self.EVIDENCE if obj is not None else ()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TenantApiKey)
class TenantApiKeyAdmin(admin.ModelAdmin):
    list_display = ("key_prefix", "tenant", "label", "is_active", "last_used_at")
    list_filter = ("is_active",)
    search_fields = ("label", "key_prefix")
