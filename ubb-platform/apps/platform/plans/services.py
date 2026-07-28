"""Plan lifecycle operations that are not plain reads."""
from django.db import transaction
from django.utils import timezone

from apps.platform.plans.models import CustomerPlanAssignment


class PlanInUse(Exception):
    """Raised when archiving a plan that still has assigned customers."""


class PlanService:
    @staticmethod
    @transaction.atomic
    def assign(tenant, customer, plan):
        """Put a customer on a plan, replacing any existing assignment.

        One assignment per customer (DB-enforced), so this is an upsert rather
        than an insert — reassignment moves the customer, never duplicates.
        """
        row, _ = CustomerPlanAssignment.objects.update_or_create(
            tenant=tenant, customer=customer, defaults={"plan": plan},
        )
        return row

    @staticmethod
    def archive(plan):
        """Soft-archive a plan. Refuses while customers are still on it —
        archiving an assigned plan would silently drop their markup to the
        tenant default."""
        if CustomerPlanAssignment.objects.filter(plan=plan).exists():
            raise PlanInUse(f"plan '{plan.key}' still has assigned customers")
        plan.archived_at = timezone.now()
        plan.save(update_fields=["archived_at", "updated_at"])
