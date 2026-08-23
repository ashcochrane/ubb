"""The book surface: declare a Pricing Book or a cost book, open rules under
one, publish reprices, list rules with history, and withdraw a book.

⚠ **THE CONTAINER IS TWO ENTITIES AND THE SURFACE FOLLOWS (#368).** A tenant
declares a Pricing Book at `/pricing/pricing-books` and a cost book at
`/pricing/cost-books`; they take different bodies, because they are different
things. A cost book names the supplier it records and the currency that
supplier bills in; a Pricing Book names neither, because a tenant's price does
not move when they switch supplier and a tenant has exactly one currency.

Everything performed *on* a book — list its rules, declare a change, publish
it, discard it — stays one family at `/pricing/books/{book_id}/...`, because
those are one act each whichever kind of book they are performed on.
Duplicating them per kind would put the discriminator back as a path segment.

⚠ **A RULE IS OPENED BY A PUBLISH SINCE #367**, and as of #368 that is the ONLY
way a book changes: the immediate reprice went with the third of the retired
audit action names. `_open_rule` below declares the change and publishes it, so
a book with one rule in it is already at version 2.
"""
import json

from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.platform.event_types.tests._helpers import declares_a_quantity
from apps.metering.pricing.models import CostBook, PricingBook, Rate
# The kind word neither body publishes, read off the migration that deleted it
# rather than spelled (#374) — see the function's own docstring for why.
from apps.metering.pricing.tests._helpers import retired_kind_column


class _ABookApiMixin:

    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(
            name="Book Tenant", products=["metering", "billing"])
        self.key_obj, self.raw_key = TenantApiKey.create_key(
            self.tenant, label="book")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1")
        # The two quantities every rule below prices. A rule names a DECLARED
        # quantity since #326, so this is the step a tenant now takes first —
        # and the route answers 422 without it, which is its own test rather
        # than a surprise in these.
        for code in ("input_tokens", "output_tokens"):
            declares_a_quantity(self.tenant, code)

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _post(self, path, body=None):
        return self.http.post(path, data=json.dumps(body or {}),
                              content_type="application/json", **self._auth())

    def _get(self, path):
        return self.http.get(path, **self._auth())

    def _delete(self, path):
        return self.http.delete(path, **self._auth())

    def _a_pricing_book(self, **body):
        return self._post("/api/v1/metering/pricing/pricing-books",
                          {"key": "catalogue", **body})

    def _a_cost_book(self, **body):
        return self._post("/api/v1/metering/pricing/cost-books",
                          {"key": "openai", "provider_key": "openai", **body})

    def _open_rule(self, book_id, **change):
        """Declare a rule and publish it, which is how a book gains one.

        Returns the publish record. `opened_rule_ids` is what a caller wanting
        the rule it just opened reads — off the rows, rather than off a
        create's echo of its own request.
        """
        declared = self._post(
            f"/api/v1/metering/pricing/books/{book_id}/publishes",
            {"changes": [{"kind": "add", **change}]})
        if declared.status_code != 200:
            return declared
        return self._post(f"/api/v1/metering/pricing/books/{book_id}"
                          f"/publishes/{declared.json()['id']}/publish")

    def _reprice(self, book_id, **change):
        declared = self._post(
            f"/api/v1/metering/pricing/books/{book_id}/publishes",
            {"changes": [{"kind": "reprice", **change}]})
        if declared.status_code != 200:
            return declared
        return self._post(f"/api/v1/metering/pricing/books/{book_id}"
                          f"/publishes/{declared.json()['id']}/publish")


class TheTwoBooksAreDeclaredSeparatelyTest(_ABookApiMixin, TestCase):
    """AC 1 at the surface: the bodies differ because the entities do."""

    def test_a_pricing_book_names_neither_a_supplier_nor_a_currency(self):
        r = self._a_pricing_book(name="Catalogue", is_default=True)

        self.assertEqual(r.status_code, 200, r.content)
        book = r.json()
        self.assertEqual(book["version"], 1)
        self.assertEqual(book["key"], "catalogue")
        self.assertTrue(book["is_default"])
        self.assertIsNone(book["customer_id"])
        self.assertNotIn("provider_key", book)
        self.assertNotIn("currency", book)
        self.assertNotIn(retired_kind_column(), book)

    def test_a_cost_book_names_both(self):
        r = self._a_cost_book(name="OpenAI", is_default=True)

        self.assertEqual(r.status_code, 200, r.content)
        book = r.json()
        self.assertEqual(book["provider_key"], "openai")
        self.assertEqual(book["currency"], "usd")  # the tenant's
        self.assertNotIn(retired_kind_column(), book)

    def test_the_two_are_listed_apart(self):
        self._a_pricing_book()
        self._a_cost_book()

        priced = self._get(
            "/api/v1/metering/pricing/pricing-books").json()["data"]
        costed = self._get(
            "/api/v1/metering/pricing/cost-books").json()["data"]

        self.assertEqual([b["key"] for b in priced], ["catalogue"])
        self.assertEqual([b["key"] for b in costed], ["openai"])

    def test_a_second_default_pricing_book_is_a_conflict(self):
        self._a_pricing_book(is_default=True)

        r = self._a_pricing_book(key="second", is_default=True)

        self.assertEqual(r.status_code, 409, r.content)

    def test_a_cost_book_may_not_declare_another_tenants_currency(self):
        r = self._a_cost_book(currency="eur")

        self.assertEqual(r.status_code, 422, r.content)
        self.assertIn("does not match tenant currency", r.json()["detail"])


class ABookGainsRulesByPublishingTest(_ABookApiMixin, TestCase):

    def test_declare_a_book_then_open_a_rule_then_reprice_it(self):
        book_id = self._a_pricing_book(is_default=True).json()["id"]

        r = self._open_rule(book_id, measurement_key="input_tokens",
                            provider="gemini", rate_structure="per_unit",
                            rate_per_unit_micros=10)
        self.assertEqual(r.status_code, 200, r.content)
        (original_rate_id,) = r.json()["opened_rule_ids"]

        (row,) = self._get(
            f"/api/v1/metering/pricing/books/{book_id}/rates").json()["data"]
        self.assertEqual(row["rate_per_unit_micros"], 10)
        self.assertEqual(row["book_id"], book_id)
        self.assertEqual(row["id"], original_rate_id)

        r = self._reprice(book_id, measurement_key="input_tokens",
                          provider="gemini", rate_per_unit_micros=12)
        self.assertEqual(r.status_code, 200, r.content)

        active = self._get(
            f"/api/v1/metering/pricing/books/{book_id}/rates").json()["data"]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["rate_per_unit_micros"], 12)
        self.assertNotEqual(active[0]["id"], original_rate_id)
        self.assertIsNotNone(Rate.objects.get(id=original_rate_id).valid_to)

    def test_a_rule_in_a_pricing_book_is_written_in_the_tenants_currency(self):
        """The Pricing Book has no currency of its own, so a rule in one takes
        the tenant's — which is the same answer the deleted column gave, from
        the record that owns the fact."""
        book_id = self._a_pricing_book(is_default=True).json()["id"]

        self._open_rule(book_id, measurement_key="input_tokens",
                        rate_structure="per_unit", rate_per_unit_micros=5)

        (row,) = self._get(
            f"/api/v1/metering/pricing/books/{book_id}/rates").json()["data"]
        self.assertEqual(row["currency"], "usd")

    def test_a_rule_in_a_cost_book_is_written_in_that_books_currency(self):
        book_id = self._a_cost_book().json()["id"]

        self._open_rule(book_id, measurement_key="input_tokens",
                        provider="openai", rate_structure="per_unit",
                        rate_per_unit_micros=5)

        (row,) = self._get(
            f"/api/v1/metering/pricing/books/{book_id}/rates").json()["data"]
        self.assertEqual(row["currency"], "usd")

    def test_a_rules_provider_must_match_the_default_cost_books_provider(self):
        """The refusal moved with the act it guards (#367) and narrowed with
        the split (#368).

        It lived on the immediate add-a-rule route and would have left with it.
        A default cost book is selected for one supplier's events, so a rule
        naming another provider inside it prices nothing and looks configured.
        A Pricing Book has no provider at all now, so the condition is
        unstatable on that half rather than unchecked.
        """
        book_id = self._a_cost_book(is_default=True).json()["id"]

        r = self._open_rule(book_id, measurement_key="input_tokens",
                            provider="gemini", rate_structure="per_unit",
                            rate_per_unit_micros=10)
        self.assertEqual(r.status_code, 422, r.content)
        self.assertIn("must match the default book's provider",
                      r.json()["detail"])

        r = self._open_rule(book_id, measurement_key="input_tokens",
                            provider="openai", rate_structure="per_unit",
                            rate_per_unit_micros=10)
        self.assertEqual(r.status_code, 200, r.content)

    def test_list_rules_include_history_shows_superseded(self):
        book_id = self._a_pricing_book(is_default=True).json()["id"]
        self._open_rule(book_id, measurement_key="input_tokens",
                        provider="gemini", rate_per_unit_micros=10)
        self._reprice(book_id, measurement_key="input_tokens",
                      provider="gemini", rate_per_unit_micros=12)

        active = self._get(
            f"/api/v1/metering/pricing/books/{book_id}/rates").json()["data"]
        self.assertEqual(len(active), 1)
        hist = self._get(
            f"/api/v1/metering/pricing/books/{book_id}/rates"
            "?include_history=true").json()["data"]
        self.assertEqual({x["rate_per_unit_micros"] for x in hist}, {10, 12})

    def test_the_rules_of_both_kinds_of_book_are_listed_by_one_route(self):
        """One family for the acts performed ON a book, whichever kind it is.

        The control that stops this being read as "the route ignores the book":
        each answers only its OWN book's rules.
        """
        priced = self._a_pricing_book(is_default=True).json()["id"]
        costed = self._a_cost_book(is_default=True).json()["id"]
        self._open_rule(priced, measurement_key="input_tokens",
                        rate_per_unit_micros=99)
        self._open_rule(costed, measurement_key="output_tokens",
                        provider="openai", rate_per_unit_micros=3)

        of_priced = self._get(
            f"/api/v1/metering/pricing/books/{priced}/rates").json()["data"]
        of_costed = self._get(
            f"/api/v1/metering/pricing/books/{costed}/rates").json()["data"]

        self.assertEqual([r["measurement_key"] for r in of_priced],
                         ["input_tokens"])
        self.assertEqual([r["measurement_key"] for r in of_costed],
                         ["output_tokens"])


class ABookIsWithdrawnOnlyWhenNothingDependsOnItTest(_ABookApiMixin, TestCase):
    """The second of the two acts this slice registers on the books.

    Withdrawal is refused while rules point at the book, because those rules
    are what a tenant was charged from and the receipts explaining past charges
    point at them. That is `PROTECT` at the database, answered as a 409 rather
    than as a 500.
    """

    def test_an_empty_pricing_book_is_withdrawn(self):
        book_id = self._a_pricing_book().json()["id"]

        r = self._delete(
            f"/api/v1/metering/pricing/pricing-books/{book_id}")

        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(PricingBook.objects.filter(id=book_id).exists())

    def test_a_pricing_book_holding_rules_answers_409(self):
        book_id = self._a_pricing_book(is_default=True).json()["id"]
        self._open_rule(book_id, measurement_key="input_tokens",
                        rate_per_unit_micros=10)

        r = self._delete(
            f"/api/v1/metering/pricing/pricing-books/{book_id}")

        self.assertEqual(r.status_code, 409, r.content)
        self.assertTrue(PricingBook.objects.filter(id=book_id).exists())

    def test_an_empty_cost_book_is_withdrawn(self):
        book_id = self._a_cost_book().json()["id"]

        r = self._delete(f"/api/v1/metering/pricing/cost-books/{book_id}")

        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(CostBook.objects.filter(id=book_id).exists())

    def test_a_cost_book_holding_rules_answers_409(self):
        book_id = self._a_cost_book(is_default=True).json()["id"]
        self._open_rule(book_id, measurement_key="input_tokens",
                        provider="openai", rate_per_unit_micros=3)

        r = self._delete(f"/api/v1/metering/pricing/cost-books/{book_id}")

        self.assertEqual(r.status_code, 409, r.content)

    def test_a_book_whose_rules_are_all_RETIRED_still_answers_409(self):
        """The case the 409's own wording used to get wrong (#368, review).

        The message said "retire its rules through a publish first", which
        reads as a remedy. It is not one: retiring a rule stamps its end and
        KEEPS the row, so the book still holds it and `PROTECT` still fires —
        the caller who followed the advice would get the same 409 with no way
        forward. Withdrawal is for a book that was declared and never used, and
        this is the case that says so.
        """
        book_id = self._a_pricing_book(is_default=True).json()["id"]
        self._open_rule(book_id, measurement_key="input_tokens",
                        rate_per_unit_micros=10)
        retired = self._post(
            f"/api/v1/metering/pricing/books/{book_id}/publishes",
            {"changes": [{"kind": "retire", "measurement_key": "input_tokens"}]})
        self.assertEqual(retired.status_code, 200, retired.content)
        self.assertEqual(
            self._post(f"/api/v1/metering/pricing/books/{book_id}"
                       f"/publishes/{retired.json()['id']}/publish").status_code,
            200)
        self.assertEqual(
            self._get(f"/api/v1/metering/pricing/books/{book_id}/rates")
            .json()["data"], [],
            "the rule is retired, so nothing is active in the book")

        r = self._delete(f"/api/v1/metering/pricing/pricing-books/{book_id}")

        self.assertEqual(r.status_code, 409, r.content)
        self.assertIn("retired rule is kept", r.json()["detail"])

    def test_a_book_with_a_pending_change_is_not_withdrawn(self):
        """The publish record CASCADES from its book, so without a refusal the
        withdrawal would take a tenant's pending intention with it silently.

        A draft is the only thing exposed — a published record opened or closed
        a rule, and a rule holds its book with `PROTECT` — so the message
        points at the act that clears one.
        """
        book_id = self._a_pricing_book().json()["id"]
        declared = self._post(
            f"/api/v1/metering/pricing/books/{book_id}/publishes",
            {"changes": [{"kind": "add", "measurement_key": "input_tokens",
                          "rate_per_unit_micros": 10}]})
        self.assertEqual(declared.status_code, 200, declared.content)

        r = self._delete(f"/api/v1/metering/pricing/pricing-books/{book_id}")

        self.assertEqual(r.status_code, 409, r.content)
        self.assertIn("Discard", r.json()["detail"])
        # And the draft is still there, which is the half a 409 alone does not
        # say: a refusal that had already cascaded would look identical.
        self.assertEqual(
            len(self._get(f"/api/v1/metering/pricing/books/{book_id}/publishes")
                .json()["data"]), 1)

    def test_discarding_the_draft_makes_the_book_withdrawable(self):
        """The remedy the message names, driven — because a refusal pointing at
        an unreachable act is what the case above exists to have caught."""
        book_id = self._a_pricing_book().json()["id"]
        declared = self._post(
            f"/api/v1/metering/pricing/books/{book_id}/publishes",
            {"changes": [{"kind": "add", "measurement_key": "input_tokens",
                          "rate_per_unit_micros": 10}]})
        self.http.delete(
            f"/api/v1/metering/pricing/books/{book_id}"
            f"/publishes/{declared.json()['id']}", **self._auth())

        r = self._delete(f"/api/v1/metering/pricing/pricing-books/{book_id}")

        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(PricingBook.objects.filter(id=book_id).exists())

    def test_one_kind_of_book_is_not_withdrawn_through_the_others_route(self):
        """The control. Without it a route that ignored its own model would
        pass every case above."""
        priced = self._a_pricing_book().json()["id"]
        costed = self._a_cost_book().json()["id"]

        self.assertEqual(
            self._delete(
                f"/api/v1/metering/pricing/cost-books/{priced}").status_code,
            404)
        self.assertEqual(
            self._delete(
                f"/api/v1/metering/pricing/pricing-books/{costed}").status_code,
            404)


class NoRouteAssignsABookToACustomerTest(_ABookApiMixin, TestCase):
    """AC 3 and AC 4 at the surface: the record is deleted and so is its route.

    A customer reaches a book through their Plan (#362) or through a book that
    carries them, and there is no third way. Asserted over the ROUTER rather
    than by calling one path, because a differently-spelled route doing the
    same job would pass a single 404 check — the shape #366 paid for one schema
    over.
    """

    def test_no_route_in_the_pricing_family_assigns_a_book(self):
        from api.v1.api import api

        paths = {path for _, path, _ in _mutating_pricing_operations(api)}

        self.assertTrue(paths, "no pricing routes found, so this asserts "
                               "nothing")
        for path in paths:
            self.assertNotIn("rate-card", path)
            self.assertNotIn("assign", path)

    def test_the_old_assignment_path_is_gone(self):
        r = self._post(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/rate-card",
            {"rate_card_id": str(self._a_pricing_book().json()["id"])})

        self.assertEqual(r.status_code, 404, r.content)


def _mutating_pricing_operations(api):
    """(method, path, operation) for every pricing route the API publishes."""
    found = []
    for prefix, router in api._routers:
        for path, view in router.path_operations.items():
            for operation in view.operations:
                full = f"{prefix}{path}"
                if "/pricing/" in full:
                    for method in operation.methods:
                        found.append((method, full, operation))
    return found


class BookGatingTest(_ABookApiMixin, TestCase):
    """A metering-only tenant records what its suppliers charge and sells
    nothing, so cost books are theirs and Pricing Books are not.

    ⚠ The gate this replaces took the kind word as an argument and branched on
    it, which is how a cost route came to be gated on billing at least once in
    this programme. Two named gates cannot make that mistake.
    """

    def setUp(self):
        super().setUp()
        self.tenant.products = ["metering"]
        self.tenant.save(update_fields=["products"])

    def test_metering_only_cannot_declare_a_pricing_book(self):
        self.assertEqual(self._a_pricing_book().status_code, 403)

    def test_metering_only_cannot_list_pricing_books(self):
        self.assertEqual(
            self._get("/api/v1/metering/pricing/pricing-books").status_code,
            403)

    def test_metering_only_can_declare_a_cost_book(self):
        self.assertEqual(self._a_cost_book().status_code, 200)

    def test_metering_only_can_list_cost_books(self):
        self.assertEqual(
            self._get("/api/v1/metering/pricing/cost-books").status_code, 200)

    def test_metering_only_cannot_read_a_pricing_books_rules(self):
        """⚠ THE HOLE REVIEW FOUND, DRIVEN (#368).

        The three acts performed on EITHER kind of book — list its rules, list
        its pending changes, read one of them — took the bare metering check
        they had when one container served both halves. After the split the
        collection routes gated per kind and these did not, so this tenant was
        refused at `/pricing/pricing-books` and served the same workspace's
        Pricing Book rules one path over. It is the mistake the deleted
        kind-word gate made in the other direction (#363), and no walker sees
        it: they check that a route HAS a floor, never which product it names.
        """
        # The book is declared while the workspace still has billing, because
        # a metering-only tenant cannot declare one — which is the whole reason
        # the read had to be gated separately.
        self.tenant.products = ["metering", "billing"]
        self.tenant.save(update_fields=["products"])
        book_id = self._a_pricing_book(is_default=True).json()["id"]
        self._open_rule(book_id, measurement_key="input_tokens",
                        rate_per_unit_micros=10)
        self.tenant.products = ["metering"]
        self.tenant.save(update_fields=["products"])

        for path in (f"/api/v1/metering/pricing/books/{book_id}/rates",
                     f"/api/v1/metering/pricing/books/{book_id}/publishes"):
            with self.subTest(path=path):
                self.assertEqual(self._get(path).status_code, 403)

    def test_metering_only_can_still_read_a_cost_books_rules(self):
        """The control. A gate that refused every per-book read would pass the
        case above while breaking the product this tenant actually has."""
        book_id = self._a_cost_book(is_default=True).json()["id"]
        self._open_rule(book_id, measurement_key="input_tokens",
                        provider="openai", rate_per_unit_micros=3)

        for path in (f"/api/v1/metering/pricing/books/{book_id}/rates",
                     f"/api/v1/metering/pricing/books/{book_id}/publishes"):
            with self.subTest(path=path):
                self.assertEqual(self._get(path).status_code, 200)
