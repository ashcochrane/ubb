import unittest
from unittest.mock import patch, MagicMock
from ubb.metering import MeteringClient
from ubb.types import RateCard


RATE_CARD_FIXTURE = {
    "id": "rc1", "card_type": "cost", "metric_name": "input_tokens", "provider": "openai",
    "event_type": "chat", "dimensions": {}, "pricing_model": "per_unit",
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
        self.assertEqual(mock_post.call_args.args[0], "/api/v1/pricing/rate-cards")

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
        self.assertEqual(mock_get.call_args.args[0], "/api/v1/pricing/rate-cards")

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
        self.assertEqual(mock_delete.call_args.args[0], "/api/v1/pricing/rate-cards/rc1")


if __name__ == "__main__":
    unittest.main()
