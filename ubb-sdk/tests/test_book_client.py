import unittest
from unittest.mock import patch, MagicMock
from ubb.metering import MeteringClient
from ubb.types import RateCard

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

RATE_CARD_FIXTURE = {
    "id": "rc1", "lineage_id": "lin1", "card_type": "cost", "measurement_key": "input_tokens",
    "provider": "openai", "event_type": "chat", "dimensions": {}, "pricing_model": "per_unit",
    "rate_per_unit_micros": 5000, "unit_quantity": 1000000, "fixed_micros": 0,
    "currency": "usd", "product_id": "", "customer_id": None,
    "valid_from": "2026-06-08T00:00:00", "valid_to": None,
}


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

    @patch("ubb.metering.httpx.Client.put")
    def test_update_rate_card(self, mock_put):
        updated = {**RATE_CARD_FIXTURE, "id": "rc2", "rate_per_unit_micros": 9000}
        mock_put.return_value = MagicMock(status_code=200, json=lambda: updated)
        card = self.client.update_rate_card("rc1", rate_per_unit_micros=9000)
        self.assertIsInstance(card, RateCard)
        self.assertEqual(card.id, "rc2")
        self.assertEqual(card.lineage_id, "lin1")
        self.assertEqual(card.rate_per_unit_micros, 9000)
        self.assertEqual(mock_put.call_args.args[0], "/api/v1/metering/pricing/rate-cards/rc1")
        self.assertEqual(mock_put.call_args.kwargs["json"], {"rate_per_unit_micros": 9000})

    @patch("ubb.metering.httpx.Client.get")
    def test_get_rate_card_history(self, mock_get):
        v2 = {**RATE_CARD_FIXTURE, "id": "rc2", "rate_per_unit_micros": 9000}
        v1 = {**RATE_CARD_FIXTURE, "valid_to": "2026-06-09T00:00:00"}
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [v2, v1])
        history = self.client.get_rate_card_history("lin1")
        self.assertEqual(len(history), 2)
        self.assertTrue(all(isinstance(c, RateCard) for c in history))
        self.assertEqual(history[0].rate_per_unit_micros, 9000)
        self.assertEqual(history[1].valid_to, "2026-06-09T00:00:00")
        self.assertEqual(mock_get.call_args.args[0],
                         "/api/v1/metering/pricing/rate-cards/lin1/history")


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


    @patch("ubb.metering.httpx.Client.post")
    def test_bulk_create_rate_cards(self, mock_post):
        batch_response = {"created": ["rc-a", "rc-b"], "count": 2}
        mock_post.return_value = MagicMock(status_code=200, json=lambda: batch_response)
        cards = [
            {"card_type": "cost", "measurement_key": "tokens", "pricing_model": "per_unit",
             "rate_per_unit_micros": 2, "unit_quantity": 1},
            {"card_type": "cost", "measurement_key": "images", "pricing_model": "flat",
             "fixed_micros": 500},
        ]
        result = self.client.bulk_create_rate_cards(cards)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["created"], ["rc-a", "rc-b"])
        # assert correct path
        self.assertEqual(mock_post.call_args.args[0],
                         "/api/v1/metering/pricing/rate-cards/batch")
        # assert body structure
        body = mock_post.call_args.kwargs["json"]
        self.assertIn("cards", body)
        self.assertEqual(len(body["cards"]), 2)
        self.assertEqual(body["cards"][0]["measurement_key"], "tokens")


if __name__ == "__main__":
    unittest.main()
