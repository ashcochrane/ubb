"""The `spend_controls` handle (#465): the two reports named as operations,
parsed through the generated models, with every filter optional and the
family taken from the vocabulary by constant — and present on every facade
whatever products it holds, because the routes are gated on none.
"""
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from ubb import vocabulary
from ubb.client import UBBClient
from ubb.spend_controls import SpendControlsClient
from ubb._core.models.ceiling_episode_row import CeilingEpisodeRow
from ubb._core.models.customer_spend_pool_episode_row import CustomerSpendPoolEpisodeRow
from ubb._core.models.stops_and_breaches_response import StopsAndBreachesResponse
from ubb._core.models.utilisation_and_headroom_response import (
    UtilisationAndHeadroomResponse)
from ubb._core.models.wallet_policy_episode_row import WalletPolicyEpisodeRow

STOPS = "/api/v1/spend-controls/stops-and-breaches"
UTILISATION = "/api/v1/spend-controls/utilisation-and-headroom"
WINDOW = {"since": "2026-09-01T00:00:00Z", "until": "2026-09-12T00:00:00Z"}
ITEMISED = {"events": [], "event_count": 0, "billed_cost_micros": 0,
            "unpriced_event_count": 0, "provider_cost_micros": 0,
            "unresolved_event_count": 0}


def _ceiling_row():
    return {"control_family": vocabulary.CONTROL_FAMILY_CEILING,
            "control_id": "kind-1", "reason_code": vocabulary.REASON_CODE_TASK_COGS_CEILING,
            "ceiling_basis": vocabulary.CEILING_BASIS_COST,
            "trigger_source": vocabulary.TRIGGER_SOURCE_USAGE_INGEST,
            "task_id": "0f1a3e64-3b6f-4c46-9d0d-8b5d2c1a1111", "parent_task_id": None,
            "customer_id": "0f1a3e64-3b6f-4c46-9d0d-8b5d2c1a2222", "task_type": "pipeline",
            "stop_scope": "task", "task_cogs_ceiling_micros": 10_000_000,
            "opened_at": "2026-09-10T10:00:00Z", "crossed_provider_cost_micros": 11_000_000,
            "crossed_unresolved_event_count": 0, "final_provider_cost_micros": 13_000_000,
            "final_unresolved_event_count": 0, "itemised": ITEMISED}


def _pool_row():
    return {"control_family": vocabulary.CONTROL_FAMILY_CUSTOMER_SPEND_POOL,
            "control_id": "pool-1", "reason_code": vocabulary.REASON_CODE_CUSTOMER_SPEND_POOL,
            "customer_id": "0f1a3e64-3b6f-4c46-9d0d-8b5d2c1a2222", "episode_seq": 1,
            "period": "2026-09", "cap_micros": 8_000_000,
            "opened_at": "2026-09-11T10:00:00Z", "closed_at": None,
            "crossing_charge_id": "0f1a3e64-3b6f-4c46-9d0d-8b5d2c1a3333",
            "crossing_posting_id": "0f1a3e64-3b6f-4c46-9d0d-8b5d2c1a4444",
            "spent_after_micros": 0, "unpriced_after_count": 0, "work_stopped_count": 1,
            "itemised": ITEMISED}


def _wallet_row():
    return {"control_family": vocabulary.CONTROL_FAMILY_WALLET_POLICY,
            "control_id": None, "reason_code": None, "soft_floor": True,
            "customer_id": "0f1a3e64-3b6f-4c46-9d0d-8b5d2c1a2222", "episode_seq": 1,
            "floor_micros": 2_000_000, "balance_at_crossing_micros": -2_500_000,
            "opened_at": "2026-09-09T10:00:00Z", "closed_at": "2026-09-09T11:00:00Z",
            "itemised": ITEMISED}


class SpendControlsClientTest(unittest.TestCase):
    def setUp(self):
        self.client = SpendControlsClient(api_key="ubb_live_test123",
                                          base_url="http://localhost:8001", max_retries=0)

    def tearDown(self):
        self.client.close()

    @patch("ubb.spend_controls.httpx.Client.get")
    def test_stops_and_breaches_parses_all_three_row_shapes(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            **WINDOW, "rows": [_wallet_row(), _ceiling_row(), _pool_row()],
            "totals": [{"control_family": vocabulary.CONTROL_FAMILY_CEILING,
                        "event_count": 0, "billed_cost_micros": 0,
                        "unpriced_event_count": 0, "provider_cost_micros": 0,
                        "unresolved_event_count": 0}]})
        result = self.client.stops_and_breaches()
        self.assertIsInstance(result, StopsAndBreachesResponse)
        self.assertEqual([type(row) for row in result.rows],
                         [WalletPolicyEpisodeRow, CeilingEpisodeRow,
                          CustomerSpendPoolEpisodeRow])
        self.assertEqual(result.rows[1].crossed_provider_cost_micros, 11_000_000)
        self.assertEqual(result.rows[2].work_stopped_count, 1)
        self.assertEqual(result.totals[0].control_family, vocabulary.CONTROL_FAMILY_CEILING)
        call_args = mock_get.call_args
        self.assertEqual(call_args.args[0], STOPS)
        self.assertEqual(call_args.kwargs["params"], {})
        self.assertNotIn("json", call_args.kwargs)

    @patch("ubb.spend_controls.httpx.Client.get")
    def test_every_filter_is_sent_and_an_absent_one_is_left_off(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            **WINDOW, "rows": [], "totals": []})
        since = datetime(2026, 9, 1, tzinfo=timezone.utc)
        self.client.stops_and_breaches(
            customer_id="cust_1", task_type="pipeline", since=since,
            control_family=vocabulary.CONTROL_FAMILY_WALLET_POLICY)
        self.assertEqual(mock_get.call_args.kwargs["params"], {
            "customer_id": "cust_1", "task_type": "pipeline",
            "since": "2026-09-01T00:00:00+00:00",
            "control_family": vocabulary.CONTROL_FAMILY_WALLET_POLICY})

    @patch("ubb.spend_controls.httpx.Client.get")
    def test_a_family_the_registry_has_not_seen_is_the_routes_to_refuse(self, mock_get):
        """No client-side value list (sdk-wrap): the word goes over the wire
        and the route answers."""
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            **WINDOW, "rows": [], "totals": []})
        self.client.stops_and_breaches(control_family="a_control_from_next_year")
        self.assertEqual(mock_get.call_args.kwargs["params"],
                         {"control_family": "a_control_from_next_year"})

    @patch("ubb.spend_controls.httpx.Client.get")
    def test_utilisation_and_headroom_keeps_a_null_average_null(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            **WINDOW, "rows": [], "unit_count": 0, "evaluated_count": 0,
            "not_applicable_count": 0, "ceiling_reached_count": 0,
            "ceiling_reached_share_percentage": None, "indeterminate_count": 0,
            "indeterminate_share_percentage": None, "within_ceiling_count": 0,
            "average_final_utilisation_percentage": None,
            "average_unused_headroom_micros": None, "customer_spend_pool": None})
        result = self.client.utilisation_and_headroom(customer_id="cust_1")
        self.assertIsInstance(result, UtilisationAndHeadroomResponse)
        self.assertIsNone(result.average_final_utilisation_percentage)
        self.assertIsNone(result.customer_spend_pool)
        self.assertEqual(mock_get.call_args.args[0], UTILISATION)
        self.assertEqual(mock_get.call_args.kwargs["params"], {"customer_id": "cust_1"})


class TheHandleIsOnEveryFacadeTest(unittest.TestCase):
    def test_the_handle_exists_whatever_products_the_facade_holds(self):
        """Ungated on the wire, so ungated on the facade: a workspace that
        holds neither product still asks these two questions."""
        for products in ({"metering": True, "billing": True},
                         {"metering": True, "billing": False},
                         {"metering": False, "billing": False}):
            client = UBBClient(api_key="test", **products)
            self.assertIsInstance(client.spend_controls, SpendControlsClient)
            client.close()

    def test_closing_the_facade_closes_the_handle(self):
        client = UBBClient(api_key="test", metering=False, billing=False)
        client.spend_controls.close = MagicMock()
        client.close()
        client.spend_controls.close.assert_called_once_with()
