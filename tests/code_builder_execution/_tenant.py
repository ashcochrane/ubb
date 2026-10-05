"""A tenant of its own for each scenario, declared the way a tenant declares
itself (#582; #158 §5.3 step 1).

**Two rows are written, because no route writes them:** the tenant, and its
first API key. Everything after that goes through the tenant's own routes,
with that key — the posture (products, billing mode, enforcement), the
customers, the registries, the books, the markup and the spend pools — and
the Blueprint is asked for through its own route. A fixture that wrote rows
would hide exactly the defects a route-built one exposes (#593 was found
that way).

The route mechanics are the platform suite's shared ones
(`api/v1/tests/_helpers.py::BlueprintRoutes`), so a configuration here is
declared the same way the Blueprint's and Verify's own suites declare one.
"""
from __future__ import annotations

from api.v1.tests._helpers import BlueprintRoutes
from apps.platform.tenants.models import Tenant, TenantApiKey
from django.test import Client

TENANT_CONFIG = "/api/v1/tenant/config"
CUSTOMERS = "/api/v1/platform/customers"
TASKS = "/api/v1/tasks"


class ScenarioTenant(BlueprintRoutes):
    """One scenario's tenant: its key, its routes and its customers."""

    def __init__(self, name: str, **posture):
        # Written to the row: no route creates a tenant, and none mints the
        # key a tenant's first call is made with.
        self.tenant = Tenant.objects.create(name=name, products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()
        self.customers: dict[str, str] = {}
        if posture:
            self._call("patch", TENANT_CONFIG, posture)

    def customer(self, external_id: str) -> str:
        """A customer, created through the route; its id, which is what a
        generated call is handed as `customer_id`."""
        created = self._call("post", CUSTOMERS, {"external_id": external_id})
        self.customers[external_id] = created["id"]
        return created["id"]

    def spend_pool(self, external_id: str, cap_micros: int) -> None:
        """A blocking spend pool on one customer."""
        self._call(
            "put",
            f"/api/v1/billing/customers/{self.customers[external_id]}"
            f"/customer-spend-pool",
            {"cap_micros": cap_micros, "enforce_mode": "blocking"})

    def blueprint(self, target: str, **selection) -> dict:
        """The Blueprint, resolved through its route for `target`."""
        return self._resolve(target=target, **selection)

    def task(self, task_id: str) -> dict:
        """A unit of work as the API answers it, with its Subtasks."""
        return self._call("get", f"{TASKS}/{task_id}")
