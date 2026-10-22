"""Plans read contract — plain data for product consumers.

Metering reads the book a customer's plan prices them from through this module
rather than touching the ORM, so the rating hot path depends on a stable shape
rather than a model.
"""
from apps.platform.plans.models import CustomerPlanAssignment, Plan


def _the_plan_pricing_this_customer(tenant_id, customer_id):
    """The customer's live plan, or None.

    **AN ARCHIVED PLAN IS NOT ONE**, and that is stated here rather than at the
    caller: archival must stop a plan pricing new events, and the book the plan
    names is the whole of what it prices them from.

    ⚠ **IT HAD A SECOND CALLER UNTIL #369**, which read the plan's own markup
    percentage, and this function exists in its own right because two readers
    asking one question of one row must not be able to disagree about whether
    that row is still in force (#362). One reader is left; the shape is kept
    because the reason it was extracted is a property of the question, not of
    how many callers happen to ask it today.
    """
    return (
        CustomerPlanAssignment.objects
        .filter(tenant_id=tenant_id, customer_id=customer_id,
                plan__archived_at__isnull=True)
        .select_related("plan")
        .first()
    )


# THE PLAN'S MARKUP READ LEFT WITH THE COLUMNS IT READ (#369). It answered a
# percentage and a flat addend off the Plan row, and metering resolved them as
# the middle rung of the price ladder. Both columns are deleted: a plan prices
# its customers through the book below and nothing else, so there is no second
# axis for a read contract to carry.


def get_pricing_book_for_customer(tenant_id, customer_id):
    """The Pricing Book the customer's plan prices them from, or None (#362).

    **THIS IS THE CHANNEL, AND THERE IS NO OTHER ONE.** Metering resolves a
    customer's price from the book their Plan names, and the plan catalog is
    the kernel's (ADR-001 rule 1) — so the reference crosses as plain data
    through this read contract rather than by metering importing the Plan. The
    caller loads the book from its own app by the id returned here.

    Answers the book's id and nothing else. A book is not a term on any
    receipt — what a rule charged is written into the receipt by value, and the
    rule's own id is the cross-reference — so there is nothing here for a
    second value to be for.
    """
    row = _the_plan_pricing_this_customer(tenant_id, customer_id)
    if row is None:
        return None
    return str(row.plan.pricing_book_id)


def pricing_books_of_live_plans(tenant_id):
    """The id of the Pricing Book each of the tenant's live Plans prices from
    (#586).

    The question the Code Builder's readiness asks of the plan catalog: which
    books COULD price a start, read off configuration alone. So it reads the
    Plans and never who is on them — a Plan's book can price a start whether or
    not anybody is on the Plan today, and the owner's ruling of 2026-10-20 on
    #553 forbids readiness from depending on Plan membership. An archived Plan
    is left out for the reason `_the_plan_pricing_this_customer` leaves it out:
    it prices nobody.
    """
    return [str(book_id) for book_id in Plan.objects.filter(
        tenant_id=tenant_id, archived_at__isnull=True,
    ).values_list("pricing_book_id", flat=True)]


def get_plan_by_key(tenant_id, key):
    """The tenant's plan with this key, archived or not, or None."""
    return Plan.objects.filter(tenant_id=tenant_id, key=key).first()


def list_plans(tenant_id, include_archived=False):
    """The tenant's plans, oldest first."""
    qs = Plan.objects.filter(tenant_id=tenant_id)
    if not include_archived:
        qs = qs.filter(archived_at__isnull=True)
    return list(qs.order_by("created_at"))
