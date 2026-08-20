"""A Plan cannot exist without naming the Pricing Book it prices from (#362, #151 §7.2).

Assigning a plan is all it takes to price a customer, and this module is the
half of that which happens before anything is resolved: the reference is
required, so a Plan cannot be written until its book exists, and there is no
state in which a plan has customers and no pricing.

**WHY REQUIRED RATHER THAN NULLABLE, WHICH IS THE WHOLE ARGUMENT.** A nullable
reference produces an alert nobody can act on, because *"this plan has no
book"* is indistinguishable from *"this plan does not price usage"*. Required
makes the second sayable the honest way — a book with no rules, whose customers
resolve to one of the two kinds of nothing rather than to zero, which
`apps/metering/pricing/tests/test_a_plan_names_the_book_it_prices_from.py`
asserts at the resolver.

**AND REQUIRED MEANS ORDERED.** Nothing can write a Plan row before the book
row it names exists. That is not a convention this module checks by reading
code: it is the `NOT NULL` and the service signature between them, and the
cases below drive both.

⚠ **THE KERNEL VALIDATES NOTHING BEYOND THE FOREIGN KEY, AND NEITHER PRODUCT
REACHES INTO THE OTHER'S MODELS.** ADR-001 forbids `apps/platform/**` importing
a product, so the plan catalog cannot ask metering whether a book is real — the
database answers that. In the other direction the boundary walker would ALLOW
metering to import the Plan (any product may import the kernel), so the gate
cannot see that reading the reference through `queries.py` is a requirement
rather than a preference. `TheBoundaryTheGateCannotSeeTest` is what does.
"""

import ast
import uuid

from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from apps.metering.pricing.models import RateCard
from apps.metering.pricing.services.book_service import BookService
from apps.platform.plans.models import Plan
from apps.platform.plans.queries import get_pricing_book_for_customer
from apps.platform.plans.services import PlanNeedsAPricingBook, PlanService
from apps.platform.plans.tests._helpers import a_plan
from apps.platform.tenants.models import Tenant
from apps.platform.tests.test_product_boundaries import (
    _iter_source_files, _module_name, iter_import_edges)

#: The plan catalog's own module prefix, and the product whose models it must
#: never reach for. Spelled as prefixes because the claim is about the whole
#: package on each side, not about the two files that happen to exist today.
THE_PLAN_CATALOG = "apps.platform.plans"
METERING = "apps.metering"
THE_PLAN_MODELS = "apps.platform.plans.models"


class TheReferenceIsRequiredTest(TestCase):
    """AC 1 and AC 2 — a Plan cannot be created without a book, at the service
    and at the database."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", default_currency="usd")

    def test_the_column_is_not_nullable(self):
        field = Plan._meta.get_field("pricing_book")

        self.assertFalse(field.null)
        # And the field is a reference rather than a copied key: what a plan
        # names has to be a book that exists, which is the half a plain UUID
        # column would not carry.
        self.assertIs(field.related_model, RateCard)

    def test_the_database_refuses_a_plan_with_no_book(self):
        with self.assertRaisesRegex(IntegrityError, "pricing_book_id"):
            with transaction.atomic():
                Plan.objects.create(tenant=self.tenant, key="p", name="P")

        self.assertEqual(Plan.objects.filter(tenant=self.tenant).count(), 0)

    def test_the_service_refuses_a_plan_with_no_book(self):
        with self.assertRaisesRegex(PlanNeedsAPricingBook, "must name"):
            PlanService.create(self.tenant, pricing_book_id=None,
                               key="p", name="P")

        self.assertEqual(Plan.objects.filter(tenant=self.tenant).count(), 0)


class CreationSequencesTheBookFirstTest(TestCase):
    """AC 3 — the ordering, and the failure mode when a caller supplies a book
    that does not exist.

    The ordering is not a convention a comment asserts: `PlanService.create`
    takes the book's id, so a caller holds it before it may ask for a plan at
    all, and the `NOT NULL` means no later statement can supply one. What these
    cases add is that the refusals are the RIGHT ones — a book that is not
    there is answered as a missing book, never as the duplicate key the route
    above it maps to a 409.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", default_currency="usd")

    def test_the_book_exists_before_the_plan_that_names_it(self):
        plan = a_plan(tenant=self.tenant, key="pro", name="Pro")

        self.assertIsNotNone(plan.pricing_book_id)
        self.assertLessEqual(plan.pricing_book.created_at, plan.created_at)

    def test_the_reference_is_deferred_which_is_why_the_service_lets_it_be(self):
        """The premise for the case below, established rather than assumed.

        Django creates every foreign key on PostgreSQL as
        `DEFERRABLE INITIALLY DEFERRED`, so a book that does not exist is
        refused when the transaction COMMITS and not by the statement that
        named it. That is the reason `PlanService.create` does not translate
        the violation into a coded refusal — it could not fire reliably — and
        the day Django stops deferring, this is what says so.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT condeferrable, condeferred FROM pg_constraint "
                "WHERE conrelid = %s::regclass AND contype = 'f' "
                "AND conname LIKE %s",
                [Plan._meta.db_table, "%pricing_book_id%"])
            rows = cursor.fetchall()

        self.assertEqual(rows, [(True, True)])

    def test_a_book_that_does_not_exist_is_refused_by_the_database(self):
        """AC 3's failure mode. The refusal names the reference.

        The constraint is forced immediate for the length of this case, which
        is the only way to observe a deferred one inside a `TestCase` — the
        outer transaction never commits, so the check would otherwise land in
        teardown attached to no assertion. What is being asserted is the
        refusal and its message, not when Postgres chooses to run it; the case
        above owns that half.
        """
        absent = uuid.uuid4()

        with self.assertRaisesRegex(IntegrityError, "pricing_book_id"):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
                PlanService.create(self.tenant, pricing_book_id=absent,
                                   key="p", name="P")

        self.assertEqual(Plan.objects.filter(tenant=self.tenant).count(), 0)

    def test_a_real_book_passes_the_same_check(self):
        """The control: the refusal above is about the book being absent, not
        about the constraint refusing every insert once made immediate."""
        book = BookService.the_book_a_plan_prices_from(
            self.tenant, plan_key="pro")

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            plan = PlanService.create(self.tenant, pricing_book_id=book.id,
                                      key="pro", name="Pro")

        self.assertEqual(plan.pricing_book_id, book.id)


class TheBookAPlanPricesFromCannotBeDeletedTest(TestCase):
    """`PROTECT` — a plan whose book went would be a plan with no pricing,
    which is the state the required reference exists to make unreachable."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", default_currency="usd")
        self.plan = a_plan(tenant=self.tenant, key="pro", name="Pro")

    def test_deleting_the_book_is_refused(self):
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            self.plan.pricing_book.delete()

        self.assertTrue(Plan.objects.filter(pk=self.plan.pk).exists())

    def test_a_book_no_plan_names_still_deletes(self):
        """The control: the refusal above is about the reference, not about
        books being undeletable.

        The spare comes from the same door the route uses, with no plan built
        on top of it — so the two cases differ in exactly the reference and in
        nothing about how the book was made. (The door also spells the retired
        discriminator so this module does not have to.)
        """
        spare = BookService.the_book_a_plan_prices_from(
            self.tenant, plan_key="spare")

        spare.delete()

        self.assertFalse(RateCard.objects.filter(pk=spare.pk).exists())


class TheReadContractIsHowMeteringReachesItTest(TestCase):
    """The channel — plain data, never an ORM object (ADR-001 rule 2)."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", default_currency="usd")
        from apps.platform.customers.models import Customer
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="acme")

    def test_an_unassigned_customer_reaches_no_book(self):
        self.assertIsNone(get_pricing_book_for_customer(
            self.tenant.id, self.customer.id))

    def test_an_assigned_customer_gets_the_book_id_as_plain_data(self):
        plan = a_plan(tenant=self.tenant, key="pro", name="Pro")
        PlanService.assign(self.tenant, self.customer, plan)

        answer = get_pricing_book_for_customer(self.tenant.id,
                                               self.customer.id)

        self.assertEqual(answer, str(plan.pricing_book_id))
        # Plain data and nothing else: an answer carrying a model would let a
        # consumer reach the whole plan catalog through the read contract.
        self.assertIsInstance(answer, str)


class TheBoundaryTheGateCannotSeeTest(TestCase):
    """AC 7 — neither product reaches into the other's models to read or
    validate the reference.

    ⚠ **THE PRODUCT-BOUNDARY GATE PASSES EITHER WAY IN ONE DIRECTION.** ADR-001
    rule 1 lets any product import `apps.platform.*`, so metering importing the
    Plan model would be legal there and this ticket's requirement — that the
    reference crosses through `queries.py` — would go unchecked. The other
    direction the gate does own (the kernel imports no product), and it is
    asserted here too so the pair reads as one claim.

    It walks with the gate's OWN `iter_import_edges` rather than a copy of the
    search: two copies of one walker agreeing with each other proves nothing,
    and a lazy function-body import is exactly what a hand-rolled grep misses.
    """

    def _edges_under(self, prefix):
        for path, rel in _iter_source_files():
            module, is_package = _module_name(rel)
            if not module.startswith(prefix):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for lineno, base, full in iter_import_edges(tree, module,
                                                        is_package):
                yield module, lineno, full

    def test_no_metering_module_imports_the_plan_models(self):
        offenders = [
            f"{module}:{lineno} imports {full}"
            for module, lineno, full in self._edges_under(METERING)
            if full.startswith(THE_PLAN_MODELS)
        ]

        self.assertEqual(offenders, [], "\n".join([
            "metering must read the Plan's book through the plans read",
            "contract (`queries.py`), never off the model.",
            *offenders]))

    def test_metering_does_read_it_through_the_read_contract(self):
        """The other half — without it the case above passes for a metering
        that has stopped reading the reference at all."""
        readers = [
            module for module, _, full in self._edges_under(METERING)
            if full.startswith("apps.platform.plans.queries")
        ]

        self.assertIn("apps.metering.pricing.services.pricing_service", readers)

    def test_the_plan_catalog_imports_no_metering_module(self):
        """The kernel side. The one allowlisted exception is the markup cache
        hook on `plans/models.py`, which predates this ticket and is named in
        the gate's own file list — so this asserts the SERVICE and the read
        contract carry nothing new, which is where a shortcut would land.
        """
        offenders = [
            f"{module}:{lineno} imports {full}"
            for module, lineno, full in self._edges_under(THE_PLAN_CATALOG)
            if full.startswith(METERING) and module != f"{THE_PLAN_CATALOG}.models"
        ]

        self.assertEqual(offenders, [], "\n".join([
            "the plan catalog is the kernel's and may not import a product;",
            "the reference is declared by app label and validated by the",
            "database alone.",
            *offenders]))
