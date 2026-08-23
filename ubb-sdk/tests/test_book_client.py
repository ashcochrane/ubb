import unittest
from unittest.mock import patch, MagicMock
from ubb.metering import MeteringClient

#: The two entities the container split into (#368). They carry different
#: columns, which is what the split is, so a fixture for one cannot stand in
#: for the other.
PRICING_BOOK_FIXTURE = {
    "id": "pb1", "key": "catalogue", "name": "Catalogue", "version": 1,
    "is_default": True, "customer_id": None,
}
COST_BOOK_FIXTURE = {
    "id": "cb1", "key": "openai", "provider_key": "openai", "currency": "usd",
    "name": "OpenAI", "version": 1, "is_default": True,
}

# ⚠ THE THIRD FIXTURE AND ITS THREE CASES ARE GONE (#373). They covered the
# client's soft-version, lineage-history and atomic-batch methods, which called
# routes that exist in no spec and no router — and they were green for months
# BECAUSE they patched the HTTP client, so the mock answered the shape the
# method expected and the server's silence never reached the assertion.
# `gates/README.md` counts that among the checks this repository has shipped
# that could not fail. Nothing replaces them: the methods are deleted, and what
# proves no call reaches an unpublished route now reads the real tree instead
# of a mock (`tests/contracts/test_sdk_operations.py`).


class BookClientTest(unittest.TestCase):
    def setUp(self):
        self.client = MeteringClient(api_key="ubb_live_t", base_url="http://localhost:8001")

    def tearDown(self):
        self.client.close()

    @patch("ubb.metering.httpx.Client.post")
    def test_declare_a_pricing_book(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: PRICING_BOOK_FIXTURE)

        book = self.client.declare_pricing_book(key="catalogue",
                                                name="Catalogue",
                                                is_default=True)

        self.assertEqual(book.id, "pb1")
        self.assertEqual(book.key, "catalogue")
        self.assertTrue(book.is_default)
        self.assertEqual(mock_post.call_args.args[0],
                         "/api/v1/metering/pricing/pricing-books")
        self.assertEqual(mock_post.call_args.kwargs["json"],
                         {"key": "catalogue", "name": "Catalogue",
                          "is_default": True})

    @patch("ubb.metering.httpx.Client.post")
    def test_declare_a_cost_book(self, mock_post):
        """The body differs from the one above, which is the whole point: a
        cost book names the supplier it records and the currency that supplier
        bills in, and a Pricing Book names neither."""
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: COST_BOOK_FIXTURE)

        book = self.client.declare_cost_book(key="openai",
                                             provider_key="openai",
                                             currency="usd")

        self.assertEqual(book.provider_key, "openai")
        self.assertEqual(book.currency, "usd")
        self.assertEqual(mock_post.call_args.args[0],
                         "/api/v1/metering/pricing/cost-books")
        self.assertEqual(mock_post.call_args.kwargs["json"]["currency"], "usd")

    @patch("ubb.metering.httpx.Client.post")
    def test_a_cost_book_omitting_the_currency_states_none(self, mock_post):
        """The route defaults it to the tenant's, so the client must not
        invent one — a hand-written default here would be the client holding
        its own answer to a question the server owns."""
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: COST_BOOK_FIXTURE)

        self.client.declare_cost_book(key="openai")

        self.assertNotIn("currency", mock_post.call_args.kwargs["json"])

    @patch("ubb.metering.httpx.Client.get")
    def test_list_pricing_books(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"data": [PRICING_BOOK_FIXTURE],
                          "next_cursor": None, "has_more": False})

        books = self.client.list_pricing_books()

        self.assertEqual(len(books), 1)
        self.assertEqual(books[0].key, "catalogue")
        self.assertEqual(mock_get.call_args.args[0],
                         "/api/v1/metering/pricing/pricing-books")

    @patch("ubb.metering.httpx.Client.get")
    def test_list_cost_books(self, mock_get):
        """The control for the pair: two methods, two paths, two types — where
        one method with a kind argument would have had one of each."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"data": [COST_BOOK_FIXTURE],
                          "next_cursor": None, "has_more": False})

        books = self.client.list_cost_books()

        self.assertEqual(books[0].provider_key, "openai")
        self.assertEqual(mock_get.call_args.args[0],
                         "/api/v1/metering/pricing/cost-books")

    @patch("ubb.metering.httpx.Client.delete")
    def test_withdraw_a_pricing_book(self, mock_delete):
        mock_delete.return_value = MagicMock(status_code=200,
                                             json=lambda: {"status": "ok"})

        self.client.withdraw_pricing_book("pb1")

        self.assertEqual(mock_delete.call_args.args[0],
                         "/api/v1/metering/pricing/pricing-books/pb1")

    @patch("ubb.metering.httpx.Client.delete")
    def test_withdraw_a_cost_book(self, mock_delete):
        mock_delete.return_value = MagicMock(status_code=200,
                                             json=lambda: {"status": "ok"})

        self.client.withdraw_cost_book("cb1")

        self.assertEqual(mock_delete.call_args.args[0],
                         "/api/v1/metering/pricing/cost-books/cb1")

    @patch("ubb.metering.httpx.Client.get")
    def test_a_tenant_with_no_books_gets_an_empty_list(self, mock_get):
        """⚠ THE CASE BESIDE THIS ONE WAS `..._with_card_type` AND IS GONE
        (#368). It asserted the kind travelled as a query parameter; there is
        no kind to pass, because the two entities are listed at two paths, and
        the pair of cases above is what says so."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"data": [], "next_cursor": None, "has_more": False})

        self.assertEqual(self.client.list_pricing_books(), [])
        self.assertEqual(self.client.list_cost_books(), [])

    def test_the_three_dead_methods_are_gone_rather_than_merely_unused(self):
        """#373, asserted here because this is where their tests were.

        A deletion leaves nothing behind to assert on, which is how one gets
        half-done: the method goes and a delegate, an alias or a re-export
        keeps the name resolving. `hasattr` over the client is the reader's own
        question — *can I still call this?* — and it is answered against the
        real class, not a mock.

        The routes themselves are not named here. What makes these three wrong
        is not their spelling but that nothing publishes them, and
        `tests/contracts/test_sdk_operations.py` asserts that property over the
        whole shell. This case guards the narrower thing that suite cannot see:
        a name surviving with no call in it at all.
        """
        for gone in ("update_rate_card", "get_rate_card_history",
                     "bulk_create_rate_cards", "_rate_card"):
            with self.subTest(method=gone):
                self.assertFalse(
                    hasattr(self.client, gone),
                    f"MeteringClient still answers to `{gone}`; #373 deletes "
                    f"the three dead methods and the private helper that "
                    f"parsed their rows")


if __name__ == "__main__":
    unittest.main()
