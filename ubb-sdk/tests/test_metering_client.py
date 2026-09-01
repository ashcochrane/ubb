import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import httpx
from ubb.metering import MeteringClient
from ubb.exceptions import (
    UBBAuthError, UBBAPIError, UBBConflictError, UBBConnectionError,
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
    OUTCOME_REASON_UPSTREAM_PROVIDER_ERROR, TASK_OUTCOME_DELIVERED,
    TASK_OUTCOME_FAILED, TASK_STATUS_COMPLETED, TASK_STATUS_FAILED,
)
from ubb._core.models.usage_event_out import UsageEventOut
from ubb._core.models.record_usage_response import RecordUsageResponse


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
    def test_record_usage_with_dimensions(self, mock_post):
        """dimensions is distinct from the open bag: declared, rate-card/
        analytics-selecting values, not free-form labels — plumbed the same
        way."""
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_3b", "new_balance_micros": 7_000_000, "suspended": False,
            "costing_status": "known", "pricing_status": "known",
        })
        self.client.record_usage(
            customer_id="cust_1", idempotency_key="i3b",
            provider_cost_micros=1_000_000, dimensions={"service": "alpha"},
        )
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["dimensions"], {"service": "alpha"})

    @patch("ubb.metering.httpx.Client.post")
    def test_record_usage_omitted_dimensions_not_in_body(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {
            "event_id": "evt_3c", "new_balance_micros": 7_000_000, "suspended": False,
            "costing_status": "known", "pricing_status": "known",
        })
        self.client.record_usage(
            customer_id="cust_1", idempotency_key="i3c",
            provider_cost_micros=1_000_000,
        )
        body = mock_post.call_args.kwargs["json"]
        self.assertNotIn("dimensions", body)

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
    def test_get_usage_with_tag_filter(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "data": [], "next_cursor": None, "has_more": False,
        })
        self.client.get_usage(customer_id="cust_1", tag_key="project", tag_value="proj_1")
        call_kwargs = mock_get.call_args
        self.assertEqual(call_kwargs.kwargs["params"]["tag_key"], "project")
        self.assertEqual(call_kwargs.kwargs["params"]["tag_value"], "proj_1")

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

    # ---- usage_analytics ----

    @patch("ubb.metering.httpx.Client.get")
    def test_usage_analytics_url_and_params(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"rows": []})
        result = self.client.usage_analytics(customer_id="c", tag_key="agent")
        call_args = mock_get.call_args
        self.assertEqual(call_args.args[0], "/api/v1/metering/analytics/usage")
        params = call_args.kwargs["params"]
        self.assertEqual(params["customer_id"], "c")
        self.assertEqual(params["tag_key"], "agent")
        self.assertEqual(result, {"rows": []})

    @patch("ubb.metering.httpx.Client.get")
    def test_usage_analytics_dimensions_sent_as_repeated_params(self, mock_get):
        """dimensions list is forwarded as-is so httpx encodes repeated params.

        THE ROW KEY BELOW IS THE ENGINE'S, SPELLED AS THE ENGINE SPELLS IT.
        `/analytics/usage` returns an open dict and this client returns it
        untouched, so the fixture is a transcript rather than a shape the SDK
        chose. Renaming it here would make the test disagree with the server
        while passing, which is the one thing a fixture must never do — the
        key moves when the engine moves it, and this file follows.

        **IT HAS NOW MOVED (#312).** The engine writes `grouping_field_value`,
        which is what the DECLARED margin row has published all along, and this
        transcript follows in the same release rather than a later one. The
        pin that makes this a transcript rather than a guess is
        `api/v1/tests/test_analytics_dimensions.py`, which asserts the whole row
        against the running route.
        """
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "total_events": 1,
            "breakdowns": {"product_id": [{"grouping_field_value": "search",
                                           "event_count": 1,
                                           "total_provider_cost_micros": 300_000,
                                           "total_billed_cost_micros": 500_000}]},
        })
        result = self.client.usage_analytics(
            customer_id="c1",
            dimensions=["product_id", "service_id", "tag:region"],
        )
        call_args = mock_get.call_args
        self.assertEqual(call_args.args[0], "/api/v1/metering/analytics/usage")
        params = call_args.kwargs["params"]
        # dimensions list is passed straight through — httpx will repeat the key
        self.assertEqual(params["dimensions"], ["product_id", "service_id", "tag:region"])
        self.assertEqual(params["customer_id"], "c1")
        # breakdowns dict is returned transparently
        self.assertIn("breakdowns", result)
        self.assertIn("product_id", result["breakdowns"])

    @patch("ubb.metering.httpx.Client.get")
    def test_usage_analytics_no_dimensions_no_key(self, mock_get):
        """When dimensions is omitted the key must not appear in the request params."""
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"total_events": 0})
        self.client.usage_analytics()
        params = mock_get.call_args.kwargs["params"]
        self.assertNotIn("dimensions", params)

    # ---- usage_timeseries ----

    @patch("ubb.metering.httpx.Client.get")
    def test_usage_timeseries_url_and_params(self, mock_get):
        """usage_timeseries sends correct path and query parameters."""
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "granularity": "day",
            "group_by": "",
            "series": [
                {"bucket": "2026-06-01", "provider_cost_micros": 100_000,
                 "billed_cost_micros": 150_000, "markup_micros": 50_000, "event_count": 1},
            ],
        })
        result = self.client.usage_timeseries(
            granularity="day",
            start_date="2026-06-01",
            end_date="2026-07-01",
            customer_id="cust_1",
        )
        call_args = mock_get.call_args
        self.assertEqual(call_args.args[0], "/api/v1/metering/analytics/usage/timeseries")
        params = call_args.kwargs["params"]
        self.assertEqual(params["granularity"], "day")
        self.assertEqual(params["start_date"], "2026-06-01")
        self.assertEqual(params["end_date"], "2026-07-01")
        self.assertEqual(params["customer_id"], "cust_1")
        self.assertNotIn("group_by", params)
        self.assertEqual(result["granularity"], "day")
        self.assertEqual(len(result["series"]), 1)
        self.assertEqual(result["series"][0]["provider_cost_micros"], 100_000)

    @patch("ubb.metering.httpx.Client.get")
    def test_usage_timeseries_group_by_forwarded(self, mock_get):
        """group_by param is forwarded when provided."""
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "granularity": "hour", "group_by": "provider", "series": [],
        })
        self.client.usage_timeseries(granularity="hour", group_by="provider")
        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params["granularity"], "hour")
        self.assertEqual(params["group_by"], "provider")

    @patch("ubb.metering.httpx.Client.get")
    def test_usage_timeseries_omits_none_params(self, mock_get):
        """start_date/end_date/customer_id/group_by are omitted when None."""
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {
            "granularity": "day", "group_by": "", "series": [],
        })
        self.client.usage_timeseries()
        params = mock_get.call_args.kwargs["params"]
        self.assertNotIn("start_date", params)
        self.assertNotIn("end_date", params)
        self.assertNotIn("customer_id", params)
        self.assertNotIn("group_by", params)


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
