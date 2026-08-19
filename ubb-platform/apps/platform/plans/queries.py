"""Plans read contract — plain data for product consumers.

Metering reads markup through this module rather than touching the ORM, so
the rating hot path depends on a stable shape rather than a model.
"""
from apps.platform.plans.models import CustomerPlanAssignment, Plan


def get_plan_markup_for_customer(tenant_id, customer_id):
    """The markup axis of the customer's plan, or None if unassigned.

    An archived plan yields None: archival must stop it pricing new events.

    **THE PLAN'S ID RIDES WITH THE TERMS (#357).** A price resolved from this
    rung is recorded on a Pricing Receipt that has to name the record the
    percentage came from — a plan's markup can be edited, so a receipt naming
    only "the plan rung" would leave a tenant re-deriving a historical charge
    against today's catalogue. It is a cross-reference and not a term: the
    percentage itself is written into the receipt by value beside it.
    """
    row = (
        CustomerPlanAssignment.objects
        .filter(tenant_id=tenant_id, customer_id=customer_id,
                plan__archived_at__isnull=True)
        .select_related("plan")
        .first()
    )
    if row is None:
        return None
    return {
        "plan_id": str(row.plan.id),
        "markup_percentage_micros": row.plan.markup_percentage_micros,
        "fixed_uplift_micros": row.plan.fixed_uplift_micros,
    }


def get_plan_by_key(tenant_id, key):
    """The tenant's plan with this key, archived or not, or None."""
    return Plan.objects.filter(tenant_id=tenant_id, key=key).first()


def list_plans(tenant_id, include_archived=False):
    """The tenant's plans, oldest first."""
    qs = Plan.objects.filter(tenant_id=tenant_id)
    if not include_archived:
        qs = qs.filter(archived_at__isnull=True)
    return list(qs.order_by("created_at"))
