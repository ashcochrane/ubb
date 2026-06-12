import unittest
from unittest.mock import patch, MagicMock
from ubb.metering import MeteringClient
from ubb.types import RateCard


RATE_CARD_FIXTURE = {
    "id": "rc1", "lineage_id": "lin1", "card_type": "cost", "metric_name": "input_tokens",
    "provider": "openai", "event_type": "chat", "dimensions": {}, "pricing_model": "per_unit",
    "rate_per_unit_micros": 5000, "unit_quantity": 1000000, "fixed_micros": 0,
    "currency": "usd", "product_id": "", "customer_id": None,
    "valid_from": "2026-06-08T00:00:00", "valid_to": None,
}


class RateCardClientTest(unittest.TestCase):
    def setUp(self):
        self.client = MeteringClient(api_key="ubb_live_t", base_url="http://localhost:8001")

    def tearDown(self):
        self.client.close()

    @patch("ubb.metering.httpx.Client.post")
    def test_create_rate_card(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: RATE_CARD_FIXTURE)
        card = self.client.create_rate_card(
            card_type="cost", metric_name="input_tokens",
            provider="openai", event_type="chat", rate_per_unit_micros=5000,
        )
        self.assertIsInstance(card, RateCard)
        self.assertEqual(card.rate_per_unit_micros, 5000)
        self.assertEqual(card.id, "rc1")
        self.assertEqual(card.card_type, "cost")
        self.assertEqual(mock_post.call_args.args[0], "/api/v1/metering/pricing/rate-cards")

    @patch("ubb.metering.httpx.Client.post")
    def test_create_rate_card_body(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: RATE_CARD_FIXTURE)
        self.client.create_rate_card(
            card_type="cost", metric_name="input_tokens",
            provider="openai", event_type="chat",
            rate_per_unit_micros=5000, product_id="prod1",
        )
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["card_type"], "cost")
        self.assertEqual(body["metric_name"], "input_tokens")
        self.assertEqual(body["rate_per_unit_micros"], 5000)
        self.assertEqual(body["product_id"], "prod1")
        self.assertEqual(body["dimensions"], {})

    @patch("ubb.metering.httpx.Client.get")
    def test_list_rate_cards(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [RATE_CARD_FIXTURE])
        cards = self.client.list_rate_cards()
        self.assertEqual(len(cards), 1)
        self.assertIsInstance(cards[0], RateCard)
        self.assertEqual(cards[0].metric_name, "input_tokens")
        self.assertEqual(cards[0].lineage_id, "lin1")
        self.assertEqual(mock_get.call_args.args[0], "/api/v1/metering/pricing/rate-cards")

    @patch("ubb.metering.httpx.Client.get")
    def test_list_rate_cards_include_history_and_as_of(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [RATE_CARD_FIXTURE])
        self.client.list_rate_cards(include_history=True, as_of="2026-06-08T00:00:00")
        params = mock_get.call_args.kwargs.get("params") or {}
        self.assertEqual(params.get("include_history"), True)
        self.assertEqual(params.get("as_of"), "2026-06-08T00:00:00")

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

    @patch("ubb.metering.httpx.Client.post")
    def test_create_rate_card_tolerates_extra_fields(self, mock_post):
        # server adds a field the dataclass doesn't know about -> no crash
        mock_post.return_value = MagicMock(
            status_code=200, json=lambda: {**RATE_CARD_FIXTURE, "future_field": "x"})
        card = self.client.create_rate_card(card_type="cost", metric_name="input_tokens")
        self.assertEqual(card.id, "rc1")

    @patch("ubb.metering.httpx.Client.get")
    def test_list_rate_cards_with_card_type(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [RATE_CARD_FIXTURE])
        self.client.list_rate_cards(card_type="cost")
        params = mock_get.call_args.kwargs.get("params") or {}
        self.assertEqual(params.get("card_type"), "cost")

    @patch("ubb.metering.httpx.Client.get")
    def test_list_rate_cards_empty(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [])
        cards = self.client.list_rate_cards()
        self.assertEqual(cards, [])

    @patch("ubb.metering.httpx.Client.delete")
    def test_delete_rate_card(self, mock_delete):
        mock_delete.return_value = MagicMock(status_code=200, json=lambda: {"status": "deleted"})
        result = self.client.delete_rate_card("rc1")
        self.assertTrue(result)
        self.assertEqual(mock_delete.call_args.args[0], "/api/v1/metering/pricing/rate-cards/rc1")


    @patch("ubb.metering.httpx.Client.post")
    def test_create_graduated_rate_card_sends_tiers(self, mock_post):
        tiers = [
            {"up_to": 10_000, "rate_per_unit_micros": 10_000, "unit_quantity": 1},
            {"up_to": None, "rate_per_unit_micros": 5_000, "unit_quantity": 1},
        ]
        fixture = {**RATE_CARD_FIXTURE, "card_type": "price",
                   "pricing_model": "graduated", "tiers": tiers}
        mock_post.return_value = MagicMock(status_code=200, json=lambda: fixture)
        card = self.client.create_rate_card(
            card_type="price", metric_name="input_tokens",
            pricing_model="graduated", tiers=tiers,
        )
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["pricing_model"], "graduated")
        self.assertEqual(body["tiers"], tiers)
        self.assertEqual(card.tiers, tiers)
        self.assertEqual(card.pricing_model, "graduated")

    @patch("ubb.metering.httpx.Client.post")
    def test_create_rate_card_default_tiers_empty_list(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: RATE_CARD_FIXTURE)
        self.client.create_rate_card(card_type="cost", metric_name="input_tokens")
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["tiers"], [])

    @patch("ubb.metering.httpx.Client.post")
    def test_bulk_create_rate_cards(self, mock_post):
        batch_response = {"created": ["rc-a", "rc-b"], "count": 2}
        mock_post.return_value = MagicMock(status_code=200, json=lambda: batch_response)
        cards = [
            {"card_type": "cost", "metric_name": "tokens", "pricing_model": "per_unit",
             "rate_per_unit_micros": 2, "unit_quantity": 1},
            {"card_type": "cost", "metric_name": "images", "pricing_model": "flat",
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
        self.assertEqual(body["cards"][0]["metric_name"], "tokens")


if __name__ == "__main__":
    unittest.main()
