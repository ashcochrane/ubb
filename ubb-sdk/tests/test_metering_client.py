import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import httpx
from ubb.metering import MeteringClient
from ubb.exceptions import (
    UBBAuthError, UBBAPIError, UBBConflictError, UBBConnectionError,
    UBBValidationError,
)
from ubb.types import PaginatedResponse, BatchItemResult, BatchResult
# ⚠ THE CLOSE'S VALUES ARE NAMED, NEVER SPELLED, on the same footing as the
# platform tests that land beside them. A test spelling `"delivered"` would go
# on passing against a wrapper that had stopped agreeing with the registry,
# which is the whole thing the generated module exists to make impossible.
#
# This is a TEST importing them, so it neither pays nor moves
# `g2-sdk-task_outcome`: the consumer census skips `/tests/` outright — "a test
# is not a surface a value set ships on" — and the hand-written client's own
# conversion belongs to the ticket that re-cuts the SDK's task surface.
from ubb.vocabulary import (
    CEILING_STATUS_INDETERMINATE,
    OUTCOME_REASON_UPSTREAM_PROVIDER_ERROR, TASK_OUTCOME_DELIVERED,
    TASK_OUTCOME_FAILED, TASK_STATUS_COMPLETED, TASK_STATUS_FAILED,
)
from ubb._core.models.usage_event_out import UsageEventOut
from ubb._core.models.record_usage_response import RecordUsageResponse
from ubb._core.models.economics_out import EconomicsOut
from ubb._core.models.economic_row_out import EconomicRowOut
from ubb._core.models.economic_measure_out import EconomicMeasureOut
from ubb._core.models.grouping_option_out import GroupingOptionOut
# The measures, the rollups and the five measure states are reached BY
# MODULE rather than imported one by one: a test naming fifteen constants
# in its import block is a test nobody reads the top of.
from ubb import vocabulary
from ubb.metering import group_by_field, group_by_rollup, measure_on


class MeteringClientTest(unittest.TestCase):
    def setUp(self):
        self.client = MeteringClient(api_key="ubb_live_test123", base_url="http://localhost:8001",
                                     max_retries=0)

    def tearDown(self):
        self.client.close()

    # ---- record_usage ----

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_basic(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_1", "new_balance_micros": 8_500_000, "suspended": False,
            "costing_status": "known", "pricing_status": "known",
        })
        result = self.client.record_usage(
            customer_id="cust_1", idempotency_key="i1",
            provider_cost_micros=1_500_000,
        )
        self.assertIsInstance(result, RecordUsageResponse)
        self.assertEqual(result.event_id, "evt_1")
        self.assertEqual(result.new_balance_micros, 8_500_000)
        self.assertFalse(result.suspended)
        self.assertEqual(mock_post.call_args.kwargs["json"]["provider_cost_micros"], 1_500_000)
        # Verify endpoint
        call_args = mock_post.call_args
        self.assertEqual(call_args.args[0], "/api/v1/metering/usage")

    @patch("ubb.metering.httpx.Client.post")
    def test_the_customers_price_is_read_off_the_ack_and_never_sent(self, mock_post):
        """This case used to SEND the price. It cannot any more (#365).

        A customer price is resolved and held by UBB from the pricing rules a
        tenant configures — it is not a number a caller states per call, so the
        wrapper has no keyword for one and puts no key in the body. What
        survives is the other direction: the resolved price comes BACK on the
        ack, which is where it always belonged.

        ⚠ The refusal asserts the KEYWORD'S NAME, not just `TypeError`. A bare
        `assertRaises(TypeError)` around a call passing an unknown keyword
        asserts only that Python refuses unknown keywords, and would pass
        identically against a wrapper that never had this one.
        """
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_2", "new_balance_micros": 9_000_000, "suspended": False,
            "costing_status": "known", "pricing_status": "known",
            "provider_cost_micros": 500_000, "billed_cost_micros": 1_000_000,
        })

        with self.assertRaisesRegex(TypeError, "billed_cost_micros"):
            self.client.record_usage(
                customer_id="cust_1", idempotency_key="i2",
                billed_cost_micros=1_000_000,
            )

        result = self.client.record_usage(
            customer_id="cust_1", idempotency_key="i2",
            provider_cost_micros=500_000,
            event_type="chat_completion", provider="openai",
        )
        self.assertIsInstance(result, RecordUsageResponse)
        self.assertEqual(result.billed_cost_micros, 1_000_000)
        self.assertEqual(result.provider_cost_micros, 500_000)
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["provider_cost_micros"], 500_000)
        self.assertNotIn("billed_cost_micros", body,
                         "the wrapper still puts a price in the request body")
        # No measurements supplied → must not appear in body
        self.assertNotIn("measurements", body)

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_carries_the_callers_own_claimed_cost(self, mock_post):
        """The caller's belief travels under its OWN key, never the cost (#324).

        The two are different facts and the whole point of the second field is
        that a client cannot express one as the other. A wrapper that folded
        the claim into `provider_cost_micros` would be sending a number the
        route reads as COGS — and, on an Event Type that does not declare it,
        would turn an accepted call into a 422.
        """
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_c", "new_balance_micros": 9_000_000,
            "suspended": False, "costing_status": "unresolved", "pricing_status": "known",
            "unresolved_reason": "reported_cost_missing",
            "claimed_provider_cost_micros": 987_654,
        })
        result = self.client.record_usage(
            customer_id="cust_1", idempotency_key="ic",
            claimed_provider_cost_micros=987_654)

        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["claimed_provider_cost_micros"], 987_654)
        self.assertNotIn("provider_cost_micros", body)
        self.assertEqual(result.claimed_provider_cost_micros, 987_654)
        self.assertIsNone(result.provider_cost_micros)

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_omits_the_claim_when_it_is_not_given(self, mock_post):
        """Absent is absent: an omitted claim sends no key at all.

        The control for the case above. A default of zero here would record a
        caller's belief that the call was free on every event that never
        stated one.
        """
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_d", "new_balance_micros": 9_000_000,
            "suspended": False, "costing_status": "known", "pricing_status": "known"})

        self.client.record_usage(customer_id="cust_1",
                                 idempotency_key="id")

        self.assertNotIn("claimed_provider_cost_micros",
                         mock_post.call_args.kwargs["json"])

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_with_the_open_bag(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_3", "new_balance_micros": 7_000_000, "suspended": False,
            "costing_status": "known", "pricing_status": "known",
        })
        result = self.client.record_usage(
            customer_id="cust_1", idempotency_key="i3",
            provider_cost_micros=1_000_000, metadata={"project": "proj_1"},
        )
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["metadata"], {"project": "proj_1"})

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_with_grouping_fields(self, mock_post):
        """The declared bag is distinct from the open one: rate-selecting and
        groupable values, not free-form labels — plumbed the same way. The
        keyword and the wire key took the registry's own word in #505, which
        is what both responses have called this same object since #277.
        """
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_3b", "new_balance_micros": 7_000_000, "suspended": False,
            "costing_status": "known", "pricing_status": "known",
        })
        self.client.record_usage(
            customer_id="cust_1", idempotency_key="i3b",
            provider_cost_micros=1_000_000, grouping_fields={"service": "alpha"},
        )
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["grouping_fields"], {"service": "alpha"})

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_omitted_grouping_fields_not_in_body(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_3c", "new_balance_micros": 7_000_000, "suspended": False,
            "costing_status": "known", "pricing_status": "known",
        })
        self.client.record_usage(
            customer_id="cust_1", idempotency_key="i3c",
            provider_cost_micros=1_000_000,
        )
        body = mock_post.call_args.kwargs["json"]
        self.assertNotIn("grouping_fields", body)

    # ---- recorded_at (F4.2) ----

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_recorded_at_datetime_serialized(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_4", "suspended": False,
            "costing_status": "known", "pricing_status": "known",
        })
        ts = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
        self.client.record_usage(
            customer_id="cust_1", idempotency_key="i4",
            provider_cost_micros=1, recorded_at=ts,
        )
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["effective_at"], "2026-06-01T12:00:00+00:00")
        self.assertNotIn("recorded_at", body)

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_recorded_at_iso_string_passthrough(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_5", "suspended": False,
            "costing_status": "known", "pricing_status": "known",
        })
        self.client.record_usage(
            customer_id="cust_1", idempotency_key="i5",
            provider_cost_micros=1, recorded_at="2026-06-01T12:00:00+02:00",
        )
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["effective_at"], "2026-06-01T12:00:00+02:00")

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_naive_recorded_at_rejected_before_http(self, mock_post):
        with self.assertRaises(ValueError):
            self.client.record_usage(
                customer_id="cust_1", idempotency_key="i6",
                provider_cost_micros=1, recorded_at=datetime(2026, 6, 1, 12, 0),
            )
        mock_post.assert_not_called()

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_omitted_recorded_at_not_in_body(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_7", "suspended": False,
            "costing_status": "known", "pricing_status": "known",
        })
        self.client.record_usage(
            customer_id="cust_1", idempotency_key="i7",
            provider_cost_micros=1,
        )
        self.assertNotIn("effective_at", mock_post.call_args.kwargs["json"])

    # ---- record_batch (F4.2) ----

    @patch("ubb.metering.httpx.Client.post")
    def test_record_batch_maps_recorded_at_and_parses_results(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "results": [
                {"accepted": True, "event_id": "evt_1", "suspended": False, "billed_cost_micros": 5},
                {"accepted": False, "code": "effective_at_too_old",
                 "detail": "too old", "stop": False, "stop_reason": None,
                 "stop_scope": None},
            ],
            "accepted": 1, "rejected": 1,
        })
        result = self.client.record_batch([
            {"customer_id": "cust_1", "idempotency_key": "k1",
             "recorded_at": datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)},
            {"customer_id": "cust_1", "idempotency_key": "k2",
             "recorded_at": "2026-01-01T00:00:00+00:00"},
        ])
        # Endpoint + body mapping
        self.assertEqual(mock_post.call_args.args[0], "/api/v1/metering/usage/batch")
        wire = mock_post.call_args.kwargs["json"]["events"]
        self.assertEqual(wire[0]["effective_at"], "2026-06-01T12:00:00+00:00")
        self.assertEqual(wire[1]["effective_at"], "2026-01-01T00:00:00+00:00")
        self.assertNotIn("recorded_at", wire[0])
        self.assertNotIn("recorded_at", wire[1])
        # Result parsing (#78: one verdict field set)
        self.assertIsInstance(result, BatchResult)
        self.assertEqual(result.accepted, 1)
        self.assertEqual(result.rejected, 1)
        self.assertIsInstance(result.results[0], BatchItemResult)
        self.assertTrue(result.results[0].accepted)
        self.assertEqual(result.results[0].event_id, "evt_1")
        self.assertEqual(result.results[0].data["billed_cost_micros"], 5)
        self.assertFalse(result.results[1].accepted)
        self.assertEqual(result.results[1].code, "effective_at_too_old")
        self.assertEqual(result.results[1].detail, "too old")

    @patch("ubb.metering.httpx.Client.post")
    def test_record_batch_naive_recorded_at_rejected_before_http(self, mock_post):
        with self.assertRaises(ValueError):
            self.client.record_batch([
                {"customer_id": "cust_1",
                 "idempotency_key": "k1", "recorded_at": datetime(2026, 6, 1)},
            ])
        mock_post.assert_not_called()

    @patch("ubb.metering.httpx.Client.post")
    def test_record_batch_does_not_mutate_caller_events(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "results": [{"ok": True, "event_id": "e1", "suspended": False}], "succeeded": 1, "failed": 0,
        })
        ev = {"customer_id": "cust_1", "idempotency_key": "k1",
              "recorded_at": "2026-06-01T12:00:00+00:00"}
        self.client.record_batch([ev])
        self.assertIn("recorded_at", ev)  # caller's dict untouched
        self.assertNotIn("effective_at", ev)

    # ---- get_usage ----

    @patch("ubb.metering.httpx.Client.get")
    def test_get_usage(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "data": [
                {"id": "00000000-0000-0000-0000-0000000000e1",
                 "kind": "metered_usage",
                 "billed_cost_micros": 10000, "costing_status": "known", "pricing_status": "known",
                 "metadata": {}, "effective_at": "2025-01-01T00:00:00Z"},
            ],
            "next_cursor": "cur_abc",
            "has_more": True,
        })
        result = self.client.get_usage(customer_id="cust_1")
        self.assertIsInstance(result, PaginatedResponse)
        self.assertEqual(len(result.data), 1)
        self.assertIsInstance(result.data[0], UsageEventOut)
        self.assertTrue(result.has_more)
        self.assertEqual(result.next_cursor, "cur_abc")
        # Verify endpoint
        call_args = mock_get.call_args
        self.assertEqual(call_args.args[0], "/api/v1/metering/customers/cust_1/usage")

    @patch("ubb.metering.httpx.Client.get")
    def test_get_usage_with_cursor_and_limit(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "data": [], "next_cursor": None, "has_more": False,
        })
        self.client.get_usage(customer_id="cust_1", cursor="cur_xyz", limit=10)
        call_kwargs = mock_get.call_args
        self.assertEqual(call_kwargs.kwargs["params"]["cursor"], "cur_xyz")
        self.assertEqual(call_kwargs.kwargs["params"]["limit"], 10)

    @patch("ubb.metering.httpx.Client.get")
    def test_get_usage_with_metadata_filter(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "data": [], "next_cursor": None, "has_more": False,
        })
        self.client.get_usage(customer_id="cust_1", metadata_key="project", metadata_value="proj_1")
        call_kwargs = mock_get.call_args
        self.assertEqual(call_kwargs.kwargs["params"]["metadata_key"], "project")
        self.assertEqual(call_kwargs.kwargs["params"]["metadata_value"], "proj_1")

    # ---- error handling ----

    @patch("ubb.metering.httpx.Client.post")
    def test_auth_error_raises(self, mock_post):
        mock_post.return_value = MagicMock(status_code=401)
        with self.assertRaises(UBBAuthError):
            self.client.record_usage(
                customer_id="c1", idempotency_key="i1",
                provider_cost_micros=1000,
            )

    @patch("ubb.metering.httpx.Client.post")
    def test_api_error_raises(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500, text="Internal Server Error")
        mock_post.return_value.json.side_effect = Exception("not json")
        with self.assertRaises(UBBAPIError):
            self.client.record_usage(
                customer_id="c1", idempotency_key="i1",
                provider_cost_micros=1000,
            )

    @patch("ubb.metering.httpx.Client.post")
    def test_conflict_error_raises(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=409, text="Conflict",
            json=lambda: {"error": "duplicate idempotency_key"},
        )
        with self.assertRaises(UBBConflictError):
            self.client.record_usage(
                customer_id="c1", idempotency_key="i1",
                provider_cost_micros=1000,
            )

    @patch("ubb.metering.httpx.Client.post")
    def test_timeout_raises_connection_error(self, mock_post):
        mock_post.side_effect = httpx.TimeoutException("timed out")
        with self.assertRaises(UBBConnectionError) as ctx:
            self.client.record_usage(
                customer_id="c1", idempotency_key="i1",
                provider_cost_micros=1000,
            )
        self.assertIsNotNone(ctx.exception.original)

    @patch("ubb.metering.httpx.Client.post")
    def test_connect_error_raises_connection_error(self, mock_post):
        mock_post.side_effect = httpx.ConnectError("connection refused")
        with self.assertRaises(UBBConnectionError) as ctx:
            self.client.record_usage(
                customer_id="c1", idempotency_key="i1",
                provider_cost_micros=1000,
            )
        self.assertIn("Could not connect", str(ctx.exception))

    # ---- context manager ----

    def test_context_manager(self):
        with patch.object(self.client, "close") as mock_close:
            with self.client:
                pass
            mock_close.assert_called_once()

    # ---- close ----

    def test_close(self):
        with patch.object(self.client._http, "close") as mock_close:
            self.client.close()
            mock_close.assert_called_once()

    # ---- record_usage with measurements (no provider_cost_micros) ----

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_with_measurements_no_cost(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_m1", "new_balance_micros": 9_000_000, "suspended": False,
            "costing_status": "known", "pricing_status": "known",
        })
        result = self.client.record_usage(
            customer_id="c", idempotency_key="i",
            measurements={"input_tokens": 1000},
        )
        self.assertIsInstance(result, RecordUsageResponse)
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["measurements"], {"input_tokens": 1000})
        self.assertNotIn("provider_cost_micros", body)

    # ---- record_usage tolerates extra server fields (measurements/receipt/uncosted) ----

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_full_server_body_with_extra_fields(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "e1", "suspended": False,
            "costing_status": "known", "pricing_status": "known",
            "provider_cost_micros": 2000, "billed_cost_micros": 2000,
            "measurements": {"input_tokens": 1000},
            "pricing_receipt": {"engine_version": "x"},
            "uncosted_measurement_keys": ["foo"],
        })
        res = self.client.record_usage(
            customer_id="c", idempotency_key="i",
            measurements={"input_tokens": 1000},
        )
        self.assertIsInstance(res, RecordUsageResponse)
        self.assertEqual(res.provider_cost_micros, 2000)
        self.assertEqual(res.uncosted_measurement_keys, ["foo"])

    # ---- record_usage with task_id (one-rule task attribution) ----

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_task_id_on_wire_and_totals_parsed(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_t1", "suspended": False,
            "costing_status": "known", "pricing_status": "known",
            "task_id": "task_1", "parent_task_id": None,
            "task_total_billed_cost_micros": 750_000,
            "task_total_provider_cost_micros": 500_000,
            "stop": False, "stop_reason": None, "stop_scope": None,
        })
        result = self.client.record_usage(
            customer_id="cust_1", idempotency_key="it1",
            provider_cost_micros=500_000, task_id="task_1",
        )
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["task_id"], "task_1")
        self.assertEqual(result.task_id, "task_1")
        self.assertIsNone(result.parent_task_id)
        self.assertEqual(result.task_total_billed_cost_micros, 750_000)
        self.assertEqual(result.task_total_provider_cost_micros, 500_000)
        self.assertFalse(result.stop)

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_omitted_task_id_not_in_body(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_t2", "suspended": False,
            "costing_status": "known", "pricing_status": "known",
        })
        self.client.record_usage(
            customer_id="cust_1", idempotency_key="it2",
            provider_cost_micros=1,
        )
        self.assertNotIn("task_id", mock_post.call_args.kwargs["json"])

    # ---- close_task ----

    @patch("ubb.metering.httpx.Client.post")
    def test_close_task_url_and_result(self, mock_post):
        from ubb._core.models.close_task_response import CloseTaskResponse
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "task_id": "task_1", "status": TASK_STATUS_COMPLETED,
            "total_billed_cost_micros": 2_500_000,
            "total_provider_cost_micros": 1_750_000,
            # Closing a unit settles nothing UBB never learned (#328), so a
            # closed unit's total is a floor on the same terms as a running
            # one's. The fixture carries one so the field is exercised rather
            # than merely present.
            "unresolved_event_count": 3,
            "unpriced_event_count": 0,
            "event_count": 12,
            # The declaration echoed back beside the state it produced, and
            # whether this call was the one that performed the close (#409).
            "outcome": TASK_OUTCOME_DELIVERED,
            "replayed": False,
            "charge_created": False,
        })
        result = self.client.close_task("task_1", TASK_OUTCOME_DELIVERED)
        self.assertEqual(mock_post.call_args.args[0],
                         "/api/v1/tasks/task_1/close")
        # THE OUTCOME IS SENT, and it is the whole point of the call: the
        # server has no default and neither does this wrapper.
        self.assertEqual(mock_post.call_args.kwargs["json"],
                         {"outcome": TASK_OUTCOME_DELIVERED})
        self.assertIsInstance(result, CloseTaskResponse)
        self.assertEqual(result.task_id, "task_1")
        self.assertEqual(result.status, TASK_STATUS_COMPLETED)
        self.assertEqual(result.outcome, TASK_OUTCOME_DELIVERED)
        self.assertIs(result.replayed, False)
        self.assertIs(result.charge_created, False)
        self.assertEqual(result.total_billed_cost_micros, 2_500_000)
        self.assertEqual(result.total_provider_cost_micros, 1_750_000)
        self.assertEqual(result.unresolved_event_count, 3)
        self.assertEqual(result.event_count, 12)
        self.assertIsNone(result.parent_task_id)

    @patch("ubb.metering.httpx.Client.post")
    def test_close_subtask_carries_parent_task_id(self, mock_post):
        from ubb._core.models.close_task_response import CloseTaskResponse
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "task_id": "sub_1", "parent_task_id": "task_1",
            "status": TASK_STATUS_COMPLETED,
            "total_billed_cost_micros": 100, "total_provider_cost_micros": 80,
            "unresolved_event_count": 0,
            "unpriced_event_count": 0,
            "event_count": 1,
            "outcome": TASK_OUTCOME_DELIVERED,
            "replayed": False,
            "charge_created": False,
        })
        result = self.client.close_task("sub_1", TASK_OUTCOME_DELIVERED)
        self.assertIsInstance(result, CloseTaskResponse)
        self.assertEqual(result.parent_task_id, "task_1")

    @patch("ubb.metering.httpx.Client.post")
    def test_a_reason_travels_beside_the_outcome(self, mock_post):
        """Both optional fields are omitted from the body unless given, so a
        caller that says nothing sends nothing — which is what lets the server
        tell *not declared* apart from *declared empty*."""
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "task_id": "task_1", "status": TASK_STATUS_FAILED,
            "total_billed_cost_micros": 0, "total_provider_cost_micros": 0,
            "unresolved_event_count": 0, "unpriced_event_count": 0,
            "event_count": 0, "outcome": TASK_OUTCOME_FAILED, "replayed": False,
            "charge_created": False,
        })
        self.client.close_task("task_1", TASK_OUTCOME_FAILED,
                               outcome_reason=OUTCOME_REASON_UPSTREAM_PROVIDER_ERROR,
                               reason_detail="the provider returned 503")
        self.assertEqual(mock_post.call_args.kwargs["json"], {
            "outcome": TASK_OUTCOME_FAILED,
            "outcome_reason": OUTCOME_REASON_UPSTREAM_PROVIDER_ERROR,
            "reason_detail": "the provider returned 503",
        })

    # ---- start_task's grouping bag, and the three reads (#422) ----
    #
    # These sit here rather than in `test_work_block.py`, which holds the
    # rest of the start-and-close surface, because their fixtures spell the
    # grouping bag's wire key — retired vocabulary under a spread ceiling
    # another slice owns, which this module already counts against and a new
    # module would put over.

    @patch("ubb.metering.httpx.Client.post")
    def test_start_task_sends_the_grouping_bag_under_its_wire_key(self, mock_post):
        """The bag travels under the request property's own name — the keyword
        the start shares with ``record_usage`` — and only when given; the
        start's answer never echoes it back (`StartTaskResponse`)."""
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "task_id": "task_1", "parent_task_id": None, "task_type": "render",
            "status": "active", "task_cogs_ceiling_micros": None,
            "agreed_price_micros": None, "external_task_id": "",
            "created_at": "2026-09-02T09:00:00+00:00", "replayed": False,
        })
        task = self.client.start_task("c1", "k1", task_type="render",
                                      grouping_fields={"region": "eu"})
        self.assertEqual(mock_post.call_args.args[0], "/api/v1/tasks")
        self.assertEqual(mock_post.call_args.kwargs["json"], {
            "customer_id": "c1", "idempotency_key": "k1",
            "task_type": "render", "grouping_fields": {"region": "eu"},
        })
        self.assertEqual(task.task_id, "task_1")

    @staticmethod
    def _a_task_row(**overrides) -> dict:
        """`api/v1/schemas.py::task_out`, as the wire sends it."""
        row = {
            "task_id": "task_1", "parent_task_id": None, "task_type": "render",
            "status": TASK_STATUS_COMPLETED, "outcome_reason": None,
            "reason_detail": None, "total_provider_cost_micros": 1_750_000,
            "unresolved_event_count": 1, "total_billed_cost_micros": 2_500_000,
            "unpriced_event_count": 0, "event_count": 12,
            "task_cogs_ceiling_micros": 5_000_000, "agreed_price_micros": None,
            # The assessment beside the totals (#452): known 1,750,000 of a
            # 5,000,000 ceiling with one event uncosted is `indeterminate`,
            # and the two figures are over the known total — the fixture
            # says what its own numbers say, never a status they contradict.
            "ceiling_status": CEILING_STATUS_INDETERMINATE,
            "ceiling_used_percentage": 35,
            "ceiling_remaining_micros": 3_250_000,
            # KEYED BY THE TENANT'S OWN DECLARED KEY (#505), never by the
            # physical slot. The fixture is `task_out` as the wire sends it,
            # and a fixture still carrying the column name would be asserting
            # against a response the server has stopped sending.
            "grouping_fields": {"region": "eu"},
            "created_at": "2026-09-02T09:00:00+00:00",
            "completed_at": "2026-09-02T09:30:00+00:00",
        }
        row.update(overrides)
        return row

    @patch("ubb.metering.httpx.Client.get")
    def test_get_task_url_and_result(self, mock_get):
        from ubb._core.models.task_detail_out import TaskDetailOut
        contained = self._a_task_row(task_id="sub_1", parent_task_id="task_1",
                                     status=TASK_STATUS_FAILED,
                                     outcome_reason=OUTCOME_REASON_UPSTREAM_PROVIDER_ERROR,
                                     reason_detail="the provider returned 503")
        mock_get.return_value = MagicMock(
            status_code=200, json=lambda: dict(self._a_task_row(),
                                              subtasks=[contained]))
        result = self.client.get_task("task_1")
        self.assertEqual(mock_get.call_args.args[0], "/api/v1/tasks/task_1")
        self.assertIsInstance(result, TaskDetailOut)
        self.assertEqual(result.task_id, "task_1")
        self.assertEqual(result.status, TASK_STATUS_COMPLETED)
        self.assertEqual(result.total_billed_cost_micros, 2_500_000)
        self.assertEqual(result.unresolved_event_count, 1)
        self.assertIsNone(result.outcome_reason)
        (inner,) = result.subtasks
        self.assertEqual(inner.task_id, "sub_1")
        self.assertEqual(inner.parent_task_id, "task_1")
        self.assertEqual(inner.status, TASK_STATUS_FAILED)
        self.assertEqual(inner.outcome_reason,
                         OUTCOME_REASON_UPSTREAM_PROVIDER_ERROR)
        self.assertEqual(inner.reason_detail, "the provider returned 503")

    @patch("ubb.metering.httpx.Client.get")
    def test_list_tasks_url_filters_and_page(self, mock_get):
        from ubb._core.models.task_out import TaskOut
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "data": [self._a_task_row(), self._a_task_row(task_id="task_2")],
            "next_cursor": "abc", "has_more": True,
        })
        page = self.client.list_tasks(cursor="xyz", limit=2, customer_id="c1",
                                      task_type="render",
                                      status=TASK_STATUS_COMPLETED)
        self.assertEqual(mock_get.call_args.args[0], "/api/v1/tasks")
        # THE WHOLE PARAMS DICT, not one key at a time: a filter the route
        # publishes nowhere rides along beside a per-key assertion unseen.
        self.assertEqual(mock_get.call_args.kwargs["params"], {
            "cursor": "xyz", "limit": 2, "customer_id": "c1",
            "task_type": "render", "status": TASK_STATUS_COMPLETED,
        })
        self.assertIsInstance(page, PaginatedResponse)
        self.assertEqual([row.task_id for row in page.data],
                         ["task_1", "task_2"])
        self.assertIsInstance(page.data[0], TaskOut)
        self.assertEqual(page.next_cursor, "abc")
        self.assertTrue(page.has_more)

    @patch("ubb.metering.httpx.Client.get")
    def test_list_tasks_sends_no_params_it_was_not_given(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "data": [], "next_cursor": None, "has_more": False,
        })
        page = self.client.list_tasks()
        self.assertIsNone(mock_get.call_args.kwargs.get("params"))
        self.assertEqual(page.data, [])
        self.assertIsNone(page.next_cursor)
        self.assertFalse(page.has_more)

    @patch("ubb.metering.httpx.Client.get")
    def test_list_subtasks_url_and_page(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "data": [self._a_task_row(task_id="sub_1", parent_task_id="task_1")],
            "next_cursor": None, "has_more": False,
        })
        page = self.client.list_subtasks("task_1", limit=10)
        self.assertEqual(mock_get.call_args.args[0],
                         "/api/v1/tasks/task_1/subtasks")
        self.assertEqual(mock_get.call_args.kwargs["params"], {"limit": 10})
        (inner,) = page.data
        self.assertEqual(inner.parent_task_id, "task_1")
        self.assertFalse(page.has_more)

    # ---- book URL correctness ----

    @patch("ubb.metering.httpx.Client.post")
    def test_declare_pricing_book_url(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "id": "pb_1", "key": "catalogue", "name": "", "version": 1,
            "is_default": False, "customer_id": None,
        })
        self.client.declare_pricing_book(key="catalogue")
        self.assertEqual(mock_post.call_args.args[0],
                         "/api/v1/metering/pricing/pricing-books")

    @patch("ubb.metering.httpx.Client.post")
    def test_declare_cost_book_url(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "id": "cb_1", "key": "openai", "provider_key": "openai",
            "currency": "usd", "name": "", "version": 1, "is_default": False,
        })
        self.client.declare_cost_book(key="openai", provider_key="openai")
        self.assertEqual(mock_post.call_args.args[0],
                         "/api/v1/metering/pricing/cost-books")

    @patch("ubb.metering.httpx.Client.get")
    def test_list_books_urls(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "data": [], "next_cursor": None, "has_more": False})

        self.client.list_pricing_books()
        self.assertEqual(mock_get.call_args.args[0],
                         "/api/v1/metering/pricing/pricing-books")
        self.client.list_cost_books()
        self.assertEqual(mock_get.call_args.args[0],
                         "/api/v1/metering/pricing/cost-books")

    # ---- THE ANALYTICS CASES ARE GONE (#501) ----
    #
    # Six of them covered two methods: the cost-and-margin report and the
    # day-or-hour series. They asserted the paths, the query parameters, that a
    # list of axes went out as REPEATED parameters rather than one comma-joined
    # one, and that a `None` parameter was omitted rather than sent as the
    # string "None".
    #
    # Both methods went with their routes, and the one economic query that
    # replaced them has no ergonomic wrapper yet — so there is nothing here to
    # assert those properties about. ⚠ **THE REPEATED-PARAMETER PROPERTY IS THE
    # ONE WORTH CARRYING FORWARD**: the replacement takes repeated `measures`
    # and repeated `group_by`, so whichever ticket writes the wrapper owes a
    # case saying so, and this note is where it will be looked for.
    #
    # What their deletion could have lost — that a hand-written method resolves
    # to an operation the contract really publishes — is a general property held
    # over EVERY method by the git-root contract suite's
    # `test_sdk_operations.py`, not one this file asserted six times.

    # ---- NO MARKUP METHODS (#369) ----
    #
    # Four cases covered a tenant-wide markup read and write and one customer's
    # override, over a record that is deleted with its five routes and its two
    # component schemas. They are not replaced: the rung that took the tenant
    # half over has three published operations and no ergonomic wrapper, signed
    # for in `coverage-authorisations.yaml`, and a customer's own price is a
    # rule in their own pricing book. What their deletion could have lost — that
    # a hand-written method resolves to an operation the contract really
    # publishes — is a general property held over EVERY method by the git-root
    # contract suite's `test_sdk_operations.py`, not one this file asserted four
    # times.


if __name__ == "__main__":
    unittest.main()


class TheOneEconomicQueryTest(unittest.TestCase):
    """`query_economics` and `grouping_options` (#505, slice 7 §18).

    One handle replaced five — the two analytics reads and the three margin
    reads #501 deleted — and the discovery read beside it says what a tenant
    may ask it. What is asserted here is the REQUEST these produce and the
    ANSWER they hand back, because between those two everything is generated.
    """

    def setUp(self):
        self.client = MeteringClient(api_key="ubb_live_test123",
                                     base_url="http://localhost:8001")

    def tearDown(self):
        self.client.close()

    @staticmethod
    def _an_answer(**overrides) -> dict:
        """`api/v1/schemas.py::EconomicsOut`, as the wire sends it."""
        body = {
            "period_start": "2026-01-01", "period_end": "2026-01-31",
            "group_by": ["field:model"], "bucket": None,
            "basis": vocabulary.REVENUE_BASIS_RECORDED,
            "economic_data_available_from": "2020-01-01",
            "measurement_data_available_from": "2025-07-01",
            "rows": [], "context": [],
        }
        body.update(overrides)
        return body

    # ---- the request ----

    @patch("ubb.metering.httpx.Client.get")
    def test_it_names_the_operation_and_sends_every_axis_of_the_question(self, mock_get):
        """The route is named through the generated operation registry, never
        spelled here, and every keyword reaches the wire under its own name."""
        mock_get.return_value = MagicMock(status_code=200,
                                          json=lambda: self._an_answer())
        self.client.query_economics(
            measures=[vocabulary.ANALYTICS_MEASURE_GROSS_MARGIN],
            group_by=[group_by_field("model"),
                      group_by_rollup(vocabulary.ANALYTICS_ROLLUP_EVENT_CATEGORY)],
            start_date="2026-01-01", end_date="2026-01-31", bucket="day",
            basis=vocabulary.REVENUE_BASIS_RECOGNISED, customer_id="c1",
            event_type="completion", task_type="render", task_id="t1",
            include_subtasks=True, where=["field:model=gpt-4"],
            past_limit=True, stop_scope="customer", episode_seq=2)

        self.assertEqual(mock_get.call_args.args[0],
                         "/api/v1/metering/analytics/economics")
        self.assertEqual(mock_get.call_args.kwargs["params"], {
            "measures": ["gross_margin"],
            "group_by": ["field:model", "rollup:event_category"],
            "start_date": "2026-01-01", "end_date": "2026-01-31",
            "bucket": "day", "basis": "recognised", "customer_id": "c1",
            "event_type": "completion", "task_type": "render",
            "task_id": "t1", "include_subtasks": True,
            "where": ["field:model=gpt-4"], "past_limit": True,
            "stop_scope": "customer", "episode_seq": 2,
        })

    @patch("ubb.metering.httpx.Client.get")
    def test_an_unasked_filter_is_absent_rather_than_null(self, mock_get):
        """A query parameter sent as `None` is a parameter sent. The minimal
        question carries its measures and nothing else."""
        mock_get.return_value = MagicMock(status_code=200,
                                          json=lambda: self._an_answer())
        self.client.query_economics(
            measures=[vocabulary.ANALYTICS_MEASURE_RECORDED_EVENTS])
        self.assertEqual(mock_get.call_args.kwargs["params"],
                         {"measures": ["recorded_events"]})

    def test_a_question_naming_no_measure_does_not_compile(self):
        """`measures` is keyword-only and REQUIRED, because it is required on
        the wire: a default measure set is how a caller ends up aggregating
        three different things to draw one line."""
        with self.assertRaises(TypeError):
            self.client.query_economics()

    @patch("ubb.metering.httpx.Client.get")
    def test_it_does_not_hold_its_own_list_of_valid_measures(self, mock_get):
        """`docs/conventions/sdk-wrap.md`: never let the client hold its own
        list of valid values — let the route 422.

        A measure UBB has never heard of reaches the server, which is the only
        thing that knows. A client that raised here would break its callers
        the day UBB coins a fifth measure, and would be a second copy of a set
        the registry already owns.
        """
        mock_get.return_value = MagicMock(status_code=200,
                                          json=lambda: self._an_answer())
        self.client.query_economics(measures=["a_measure_ubb_does_not_have"])
        self.assertEqual(mock_get.call_args.kwargs["params"]["measures"],
                         ["a_measure_ubb_does_not_have"])

    # ---- the answer, and its states ----

    @patch("ubb.metering.httpx.Client.get")
    def test_the_answer_is_parsed_through_the_generated_model(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200,
                                          json=lambda: self._an_answer())
        answer = self.client.query_economics(
            measures=[vocabulary.ANALYTICS_MEASURE_GROSS_MARGIN])
        self.assertIsInstance(answer, EconomicsOut)
        self.assertEqual(answer.period_start, "2026-01-01")
        self.assertEqual(answer.group_by, ["field:model"])
        self.assertEqual(str(answer.basis), "recorded")
        self.assertEqual(answer.economic_data_available_from, "2020-01-01")
        self.assertEqual(answer.measurement_data_available_from, "2025-07-01")

    @patch("ubb.metering.httpx.Client.get")
    def test_a_measure_keeps_its_state_and_its_absent_figure_stays_absent(self, mock_get):
        """⚠ THE STATE IS THE POINT, AND A MISSING FIGURE IS NOT A ZERO.

        A margin UBB cannot attribute at the requested grain has NO figure —
        there is no such thing as a partial margin — and it says so in its
        state. A wrapper that coerced the absent amount to `0` would publish
        "this customer broke exactly even" as a measured fact. Both halves are
        pinned: the state arrives, and the figure is still `None`.
        """
        row = {
            "bucket_start": None,
            "grouping_field_value": ["gpt-4"],
            "grouping_field_value_status": ["known"],
            "measures": [
                {"measure": "gross_margin", "amount_micros": None,
                 "status": vocabulary.MEASURE_STATUS_UNAVAILABLE_AT_REQUESTED_GRAIN},
                {"measure": "supplier_cogs", "amount_micros": 4_200_000,
                 "status": vocabulary.MEASURE_STATUS_INCOMPLETE,
                 "unresolved_event_count": 3},
            ],
        }
        mock_get.return_value = MagicMock(
            status_code=200, json=lambda: self._an_answer(rows=[row]))

        (answered,) = self.client.query_economics(
            measures=[vocabulary.ANALYTICS_MEASURE_GROSS_MARGIN,
                      vocabulary.ANALYTICS_MEASURE_SUPPLIER_COGS]).rows

        margin = measure_on(answered, vocabulary.ANALYTICS_MEASURE_GROSS_MARGIN)
        self.assertIsNone(margin.amount_micros)
        self.assertEqual(str(margin.status),
                         vocabulary.MEASURE_STATUS_UNAVAILABLE_AT_REQUESTED_GRAIN)

        cost = measure_on(answered, vocabulary.ANALYTICS_MEASURE_SUPPLIER_COGS)
        self.assertEqual(cost.amount_micros, 4_200_000)
        self.assertEqual(str(cost.status), vocabulary.MEASURE_STATUS_INCOMPLETE)
        self.assertEqual(cost.unresolved_event_count, 3)

    def test_reading_a_measure_hands_back_the_measure_and_never_the_number(self):
        """The shape is the control. `measure_on` returns the whole measure, so
        there is no call on this surface that yields a figure with its state
        stripped off — which is the one-line way to publish a bound as a
        total."""
        row = EconomicRowOut.from_dict({
            "bucket_start": None, "grouping_field_value": [],
            "grouping_field_value_status": [],
            "measures": [{"measure": "customer_revenue",
                          "amount_micros": 9_000_000,
                          "status": vocabulary.MEASURE_STATUS_KNOWN}],
        })
        found = measure_on(row, vocabulary.ANALYTICS_MEASURE_CUSTOMER_REVENUE)
        self.assertIsInstance(found, EconomicMeasureOut)
        self.assertIsNone(
            measure_on(row, vocabulary.ANALYTICS_MEASURE_GROSS_MARGIN),
            "a measure the row does not carry is absent, never a zero")

    # ---- the axis words, and the discovery read ----

    def test_an_axis_carries_its_own_kind(self):
        """⚠ THE ANSWERS ARE LITERALS HERE, NOT THE CONSTANTS THE FUNCTIONS USE.

        Asserting `group_by_field("model") == f"{ANALYTICS_GROUPING_KIND_FIELD}:model"`
        would restate the implementation one import away and could not fail.
        These say the words. The separate claim — that the prefixes ARE the
        registry's values — is the test below, where comparing against the
        registry is the claim rather than a tautology.
        """
        self.assertEqual(group_by_field("model"), "field:model")
        self.assertEqual(group_by_field("provider"), "field:provider")
        self.assertEqual(group_by_rollup("event_category"), "rollup:event_category")
        self.assertEqual(group_by_rollup("measurement_concept"),
                         "rollup:measurement_concept")

    def test_the_two_prefixes_are_the_registry_s_own_values(self):
        """The agreement, as its own claim: the kind an axis carries is the
        generated vocabulary's, held by reference, so a kind renamed in the
        registry renames it here and a client cannot drift from the server."""
        self.assertEqual(
            {group_by_field("k").split(":")[0], group_by_rollup("k").split(":")[0]},
            vocabulary.ANALYTICS_GROUPING_KIND_VALUES)

    @patch("ubb.metering.httpx.Client.get")
    def test_the_discovery_read_names_its_operation_and_parses_its_rows(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"options": [
            {"key": "model", "kind": "field", "rollup": None, "label": "Model",
             "source_grain": "posting", "supported_surfaces": ["economics"],
             "max_cardinality": 100, "unsupported_measures": []},
            {"key": "event_category", "kind": "rollup",
             "rollup": "event_category", "label": "",
             "source_grain": "posting", "supported_surfaces": ["economics"],
             "max_cardinality": None, "unsupported_measures": [
                 {"measure": "customer_revenue", "reason": "nothing to attribute"}]},
        ]})
        options = self.client.grouping_options()

        self.assertEqual(mock_get.call_args.args[0],
                         "/api/v1/metering/analytics/grouping-options")
        self.assertEqual([o.key for o in options], ["model", "event_category"])
        declared, rolled_up = options
        self.assertIsInstance(declared, GroupingOptionOut)
        self.assertEqual(str(declared.kind),
                         vocabulary.ANALYTICS_GROUPING_KIND_FIELD)
        self.assertEqual(declared.max_cardinality, 100)
        self.assertEqual(str(rolled_up.kind),
                         vocabulary.ANALYTICS_GROUPING_KIND_ROLLUP)
        self.assertEqual([str(u.measure) for u in rolled_up.unsupported_measures],
                         ["customer_revenue"])
        self.assertEqual(
            group_by_field(declared.key), "field:model",
            "a row's key is what goes inside the axis builder")


class BatchRefusesAnUndeclaredKeyTest(unittest.TestCase):
    """`record_batch` refuses a key the recording request does not publish (#505).

    ⚠ **THIS IS THE ONE WRAPPER PATH WHERE THE RENAME WAS SILENT.**
    `record_usage` is keyword-only, so a name it does not take is a `TypeError`
    that names itself. `record_batch` takes DICTS, and UBB drops an undeclared
    body key rather than refusing it — so a batch item carrying a renamed or
    mistyped key recorded an event attributed to nothing, answered 200, and said
    so nowhere. A hundred at a time.
    """

    def setUp(self):
        self.client = MeteringClient(api_key="ubb_live_test123",
                                     base_url="http://localhost:8001")

    def tearDown(self):
        self.client.close()

    @patch("ubb.metering.httpx.Client.post")
    def test_an_undeclared_key_is_refused_before_any_http(self, mock_post):
        """Before the call, not after: the point is that nothing is recorded.

        ⚠ THE MOCK ANSWERS SUCCESSFULLY ON PURPOSE. With the guard removed
        this call has to REACH the server and come back fine, so the test
        fails with `UBBValidationError not raised` — which is the defect.
        Left unconfigured, the mock blows up inside `_http.py` instead and
        the failure describes a mock rather than a missing refusal.
        """
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "results": [{"accepted": True, "event_id": "evt_1"},
                        {"accepted": True, "event_id": "evt_2"}]})
        with self.assertRaises(UBBValidationError) as caught:
            self.client.record_batch([
                {"customer_id": "c1", "idempotency_key": "i1",
                 "provider_cost_micros": 1_000},
                {"customer_id": "c1", "idempotency_key": "i2",
                 "a_key_the_request_does_not_publish": {"model": "gpt-4"}},
            ])
        mock_post.assert_not_called()
        message = str(caught.exception)
        self.assertIn("events[1]", message,
                      "the message names WHICH item, because a batch is a hundred long")
        self.assertIn("a_key_the_request_does_not_publish", message)

    @patch("ubb.metering.httpx.Client.post")
    def test_every_published_key_is_admitted(self, mock_post):
        """The guard must not refuse the request's own vocabulary. Read off the
        generated model, so it cannot drift from what the contract publishes —
        and asserted as a WHOLE BODY, because a guard that admitted most keys
        and dropped one would pass a per-key check."""
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "results": [{"accepted": True, "event_id": "evt_1"}]})
        self.client.record_batch([{
            "customer_id": "c1", "idempotency_key": "i1",
            "provider_cost_micros": 1_000, "claimed_provider_cost_micros": 2_000,
            "currency": "usd", "event_type": "completion", "provider": "openai",
            "measurements": {"tokens": 10}, "metadata": {"run": "nightly"},
            "grouping_fields": {"model": "gpt-4"},
            "task_id": "11111111-1111-1111-1111-111111111111",
            "effective_at": "2026-01-01T00:00:00+00:00",
        }])
        (sent,) = mock_post.call_args.kwargs["json"]["events"]
        self.assertEqual(sent["grouping_fields"], {"model": "gpt-4"})
        self.assertEqual(sent["metadata"], {"run": "nightly"})

    @patch("ubb.metering.httpx.Client.post")
    def test_the_sdk_s_own_alias_is_admitted_and_translated(self, mock_post):
        """`recorded_at` is this SDK's ergonomic name and the request publishes
        `effective_at`. The guard has to admit the alias it itself translates,
        which is why the derived set is the model's fields PLUS that one name."""
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "results": [{"accepted": True, "event_id": "evt_1"}]})
        self.client.record_batch([{
            "customer_id": "c1", "idempotency_key": "i1",
            "recorded_at": datetime(2026, 1, 1, tzinfo=timezone.utc)}])
        (sent,) = mock_post.call_args.kwargs["json"]["events"]
        self.assertNotIn("recorded_at", sent)
        self.assertEqual(sent["effective_at"], "2026-01-01T00:00:00+00:00")

    def test_the_admitted_set_is_the_contract_s_and_not_a_copy(self):
        """The control on the derivation. A hand-typed set here would agree with
        the contract until one of them moved, and the one that moves is the
        contract — it regenerates under CI's drift gate and a literal does not.

        Pinned as a LITERAL because that is what the set IS today; the claim that
        it comes from the model is the assertion below it, where comparing
        against the generated class is the claim rather than a tautology."""
        from ubb.metering import _declared_recording_keys
        from ubb._core.models.record_usage_request import RecordUsageRequest
        from attrs import fields as attrs_fields

        assert _declared_recording_keys() == {
            "customer_id", "idempotency_key", "claimed_provider_cost_micros",
            "currency", "effective_at", "event_type", "grouping_fields",
            "measurements", "metadata", "provider", "provider_cost_micros",
            "task_id", "recorded_at",
        }
        published = {f.name for f in attrs_fields(RecordUsageRequest)
                     if f.name != "additional_properties"}
        assert _declared_recording_keys() - {"recorded_at"} == published
