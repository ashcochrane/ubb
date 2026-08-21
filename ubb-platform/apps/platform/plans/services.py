"""Plan lifecycle operations that are not plain reads."""
from django.db import transaction
from django.utils import timezone

from apps.platform.plans.models import CustomerPlanAssignment, Plan
from core.exceptions import UBBError


class PlanInUse(Exception):
    """Raised when archiving a plan that still has assigned customers."""


class PlanNeedsAPricingBook(UBBError):
    """Raised when creating a Plan without naming a Pricing Book.

    A plan with no book is a plan whose customers have no pricing and no way to
    say so — the state #362's required reference exists to make unreachable.

    From the `UBBError` taxonomy, as `docs/conventions/coding-standards.md`
    §Errors requires; `PlanInUse` beside it predates that rule and is left
    alone rather than re-typed in a commit about something else, which is the
    change #360 paid for making casually (a coded refusal that stops being a
    `ValueError` stops being caught by everything that caught one).
    """


class PlanService:
    @staticmethod
    def create(tenant, *, pricing_book_id, key, name, **fields):
        """Create a Plan, which cannot be done before its Pricing Book exists.

        **THE ORDERING IS THIS SIGNATURE, NOT A CONVENTION (#362, #151 §7.2).**
        A Plan names the book its customers are priced from and the column is
        `NOT NULL`, so there is no call that writes a plan row and finds it a
        book afterwards: a caller holds the book's id before it may ask for a
        plan at all. The composition layer creates the book first
        (`BookService.the_book_a_plan_prices_from`) and then calls this.

        ⚠ **THE KERNEL VALIDATES NOTHING BEYOND THE FOREIGN KEY, AND THAT IS
        TWO SEPARATE REFUSALS BY TWO DIFFERENT MECHANISMS.** *No book named* is
        this module's own field being empty and is refused here, before a
        statement is issued. *A book that is not there* is the database's, and
        it can only be the database's: ADR-001 forbids `apps/platform/**`
        importing a product, so this cannot ask metering whether a book is
        real, and reaching the model through the field's `related_model` to ask
        anyway would be validating past the foreign key by a back door.

        ⚠ **AND THAT SECOND REFUSAL ARRIVES AT COMMIT, NOT AT THE INSERT.**
        Django creates every foreign key on PostgreSQL as
        `DEFERRABLE INITIALLY DEFERRED`, so the violation is raised when the
        transaction commits and cannot be attributed to the statement that
        caused it. There is therefore no `except IntegrityError` here dressing
        it up as a coded refusal: it would not fire reliably, and a refusal
        that fires *sometimes* is worse than the database's own message.
        `plans/tests/test_a_plan_names_the_book_it_prices_from.py` pins both
        the deferral and the refusal.

        ``**fields`` are the plan's own columns, passed through unread.
        """
        if not pricing_book_id:
            raise PlanNeedsAPricingBook(
                "a plan must name the Pricing Book its customers are priced from")
        return Plan.objects.create(
            tenant=tenant, pricing_book_id=pricing_book_id,
            key=key, name=name, **fields)

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
        archiving an assigned plan would silently move every one of them off
        the book it prices them from."""
        if CustomerPlanAssignment.objects.filter(plan=plan).exists():
            raise PlanInUse(f"plan '{plan.key}' still has assigned customers")
        plan.archived_at = timezone.now()
        plan.save(update_fields=["archived_at", "updated_at"])
