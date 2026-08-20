"""Plans read contract — plain data for product consumers.

Metering reads markup through this module rather than touching the ORM, so
the rating hot path depends on a stable shape rather than a model.
"""
from apps.platform.plans.models import CustomerPlanAssignment, Plan


def _the_plan_pricing_this_customer(tenant_id, customer_id):
    """The customer's live plan, or None. The one query both readers below run.

    **AN ARCHIVED PLAN IS NOT ONE**, and that is stated here rather than twice:
    archival must stop a plan pricing new events, and that has to be true of
    the book it names as much as of the markup it carries. Two readers asking
    one question of one row must not be able to disagree about whether it is
    still in force (#362).
    """
    return (
        CustomerPlanAssignment.objects
        .filter(tenant_id=tenant_id, customer_id=customer_id,
                plan__archived_at__isnull=True)
        .select_related("plan")
        .first()
    )


def get_plan_markup_for_customer(tenant_id, customer_id):
    """The markup axis of the customer's plan, or None if unassigned.

    **THE PLAN'S ID RIDES WITH THE TERMS (#357).** A price resolved from this
    rung is recorded on a Pricing Receipt that has to name the record the
    percentage came from — a plan's markup can be edited, so a receipt naming
    only "the plan rung" would leave a tenant re-deriving a historical charge
    against today's catalogue. It is a cross-reference and not a term: the
    percentage itself is written into the receipt by value beside it.
    """
    row = _the_plan_pricing_this_customer(tenant_id, customer_id)
    if row is None:
        return None
    return {
        "plan_id": str(row.plan.id),
        "markup_percentage_micros": row.plan.markup_percentage_micros,
        "fixed_uplift_micros": row.plan.fixed_uplift_micros,
    }


def get_pricing_book_for_customer(tenant_id, customer_id):
    """The Pricing Book the customer's plan prices them from, or None (#362).

    **THIS IS THE CHANNEL, AND THERE IS NO OTHER ONE.** Metering resolves a
    customer's price from the book their Plan names, and the plan catalog is
    the kernel's (ADR-001 rule 1) — so the reference crosses as plain data
    through this read contract rather than by metering importing the Plan. The
    caller loads the book from its own app by the id returned here.

    Answers the book's id and nothing else. The rung above carries its plan's
    id because a receipt has to name the record a percentage came from; a book
    is not a term on any receipt, so there is nothing here for a second value
    to be for.
    """
    row = _the_plan_pricing_this_customer(tenant_id, customer_id)
    if row is None:
        return None
    return str(row.plan.pricing_book_id)


def get_plan_by_key(tenant_id, key):
    """The tenant's plan with this key, archived or not, or None."""
    return Plan.objects.filter(tenant_id=tenant_id, key=key).first()


def list_plans(tenant_id, include_archived=False):
    """The tenant's plans, oldest first."""
    qs = Plan.objects.filter(tenant_id=tenant_id)
    if not include_archived:
        qs = qs.filter(archived_at__isnull=True)
    return list(qs.order_by("created_at"))
