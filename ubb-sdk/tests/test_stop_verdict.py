"""The spend stop raises by default, survives a tenant's own ``except
Exception:``, and a batch report never raises (#421, #179 §1).

One-rule contract, unchanged: every usage report answers 200 and the ack
carries the verdict (``stop`` / ``stop_reason`` / ``stop_scope``). What this
module pins is what the CLIENT does with it. An unconfigured ``record_usage``
raises ``UBBStopRequested`` carrying that ack; the signal derives from
``BaseException`` so a catch-all around a provider loop cannot eat it and keep
spending; ``raise_on_stop=False`` returns the identical ack instead; and
``record_batch`` reports the stop per item and never raises, because one
stopped piece of work in a batch of fifty must not abandon the other
forty-nine.

Every body below carries `costing_status`, which the ack has published since
#317 and which the generated model requires. The literal is written out in each
body rather than sourced from `ubb.vocabulary`, deliberately: these are
transcripts of what the server sends, and a fixture that imported the same
constant the client parses against could not contradict a mistake in it.
"""
import inspect
import unittest
from unittest.mock import patch, MagicMock

import ubb
from ubb.metering import MeteringClient
from ubb.exceptions import UBBAPIError, UBBError, UBBStopRequested
from ubb._core.models.record_usage_response import RecordUsageResponse


def _stopped_ack(**overrides) -> dict:
    """A 200 body whose verdict says stop, customer scope unless overridden."""
    body = {
        "event_id": "e1", "suspended": False,
        "costing_status": "known", "pricing_status": "known",
        "stop": True, "stop_reason": "customer_wide_stop", "stop_scope": "customer",
    }
    body.update(overrides)
    return body


def _ok_ack(**overrides) -> dict:
    body = {
        "event_id": "e1", "suspended": False,
        "costing_status": "known", "pricing_status": "known", "stop": False,
    }
    body.update(overrides)
    return body


def _responding(mock_post, body: dict) -> None:
    mock_post.return_value = MagicMock(status_code=200, json=lambda: body)


class _ClientCase(unittest.TestCase):
    max_retries = 0

    def setUp(self):
        self.client = MeteringClient(api_key="ubb_live_x", base_url="http://localhost:8001",
                                     max_retries=self.max_retries)

    def tearDown(self):
        self.client.close()


class TheStopRaisesByDefaultTest(_ClientCase):
    """An unconfigured client gets the raising path. Nothing is passed on any
    call here beyond the event itself: the default IS the subject."""

    @patch("ubb.metering.httpx.Client.post")
    def test_an_unconfigured_client_raises_on_a_customer_stop(self, mock_post):
        _responding(mock_post, _stopped_ack())
        with self.assertRaises(UBBStopRequested) as cm:
            self.client.record_usage(customer_id="c1", idempotency_key="i1")
        stop = cm.exception
        self.assertEqual(stop.stop_scope, "customer")
        self.assertEqual(stop.stop_reason, "customer_wide_stop")
        self.assertIsNone(stop.task_id)
        self.assertEqual(stop.event_id, "e1")
        self.assertEqual(stop.idempotency_key, "i1")

    @patch("ubb.metering.httpx.Client.post")
    def test_a_task_stop_names_the_task_and_carries_its_totals(self, mock_post):
        """A ceiling crossing rides a 200 — the event landed and billed; the
        signal names the task and carries the post-event totals on the ack."""
        _responding(mock_post, _stopped_ack(
            stop_reason="task_limit", stop_scope="task", task_id="task_1",
            parent_task_id=None,
            task_total_billed_cost_micros=2_000_000,
            task_total_provider_cost_micros=1_100_000))
        with self.assertRaises(UBBStopRequested) as cm:
            self.client.record_usage(customer_id="c1", idempotency_key="i1",
                                     task_id="task_1")
        stop = cm.exception
        self.assertEqual(stop.stop_reason, "task_limit")
        self.assertEqual(stop.stop_scope, "task")
        self.assertEqual(stop.task_id, "task_1")
        self.assertIsInstance(stop.result, RecordUsageResponse)
        self.assertTrue(stop.result.stop)
        self.assertIsNone(stop.result.parent_task_id)
        self.assertEqual(stop.result.task_total_billed_cost_micros, 2_000_000)
        self.assertEqual(stop.result.task_total_provider_cost_micros, 1_100_000)

    @patch("ubb.metering.httpx.Client.post")
    def test_a_stop_for_work_that_is_no_longer_active_raises_too(self, mock_post):
        """An event landing on killed or completed work still records and
        bills (HTTP 200); the verdict is task_not_active, scope task."""
        _responding(mock_post, _stopped_ack(
            stop_reason="task_not_active", stop_scope="task", task_id="task_1"))
        with self.assertRaises(UBBStopRequested) as cm:
            self.client.record_usage(customer_id="c1", idempotency_key="i1",
                                     task_id="task_1")
        self.assertEqual(cm.exception.stop_reason, "task_not_active")
        self.assertEqual(cm.exception.task_id, "task_1")

    @patch("ubb.metering.httpx.Client.post")
    def test_no_stop_means_no_signal(self, mock_post):
        _responding(mock_post, _ok_ack())
        result = self.client.record_usage(customer_id="c1", idempotency_key="i1")
        self.assertFalse(result.stop)

    @patch("ubb.metering.httpx.Client.post")
    def test_the_message_says_the_event_was_recorded(self, mock_post):
        """The signal must never read as a failed submission (#179 §1.3): a
        caller who mistakes it for one retries a completed event."""
        _responding(mock_post, _stopped_ack())
        with self.assertRaises(UBBStopRequested) as cm:
            self.client.record_usage(customer_id="c1", idempotency_key="i1")
        text = str(cm.exception)
        self.assertIn("recorded", text)
        self.assertIn("e1", text)
        self.assertIn("customer", text)


class TheSignalIsRaisedAfterTheWriteTest(_ClientCase):
    """Ordering is contract: commit, acknowledgement, THEN the signal carrying
    it. The client cannot see the commit, but it can prove the ack was parsed
    before anything was raised, and that the raise never re-sends."""

    max_retries = 3

    @patch("ubb.metering.httpx.Client.post")
    def test_the_signal_carries_the_whole_acknowledgement(self, mock_post):
        _responding(mock_post, _stopped_ack(billed_cost_micros=70_000,
                                            new_balance_micros=930_000))
        with self.assertRaises(UBBStopRequested) as cm:
            self.client.record_usage(customer_id="c1", idempotency_key="i1")
        ack = cm.exception.result
        self.assertEqual(ack.event_id, "e1")
        self.assertEqual(ack.billed_cost_micros, 70_000)
        self.assertEqual(ack.new_balance_micros, 930_000)

    @patch("ubb.metering.httpx.Client.post")
    def test_a_stop_is_never_retried(self, mock_post):
        """Retries exist for transport failures. A stop is a successful write
        whose ack asks for something; with three retries configured, the
        request still goes out exactly once.

        NOT EVIDENCE ON ITS OWN. The property holds by two facts at once —
        the raise sits after ``_request`` returns, and ``retry.py`` catches
        only ``Exception`` — so no single edit reddens it; a signal moved
        inside the retry loop would still escape that loop untouched. It is
        here so the claim is stated where a reader looks for it, beside the
        cases that do discriminate."""
        _responding(mock_post, _stopped_ack())
        with self.assertRaises(UBBStopRequested):
            self.client.record_usage(customer_id="c1", idempotency_key="i1")
        self.assertEqual(mock_post.call_count, 1)


class TheStopSurvivesATenantCatchAllTest(_ClientCase):
    """The single most common line in integration code is ``except
    Exception:``. It must not be able to swallow the one signal that protects
    the customer's money (#179 §1.4)."""

    @patch("ubb.metering.httpx.Client.post")
    def test_except_exception_does_not_swallow_the_stop(self, mock_post):
        _responding(mock_post, _stopped_ack())
        swallowed = False
        with self.assertRaises(UBBStopRequested):
            try:
                self.client.record_usage(customer_id="c1", idempotency_key="i1")
            except Exception:  # the tenant's own catch-all, on purpose
                swallowed = True
        self.assertFalse(swallowed, "a bare `except Exception:` ate the spend stop")

    @patch("ubb.metering.httpx.Client.post")
    def test_an_ordinary_api_failure_is_still_caught_by_that_line(self, mock_post):
        """The control for the case above: the construct catches everything
        this SDK raises for a FAILED call, so the stop escaping it is a
        property of the stop and not of the test."""
        mock_post.return_value = MagicMock(
            status_code=422, headers={},
            text='{"code": "validation_error", "detail": "bad"}',
            json=lambda: {"code": "validation_error", "detail": "bad"})
        caught = None
        try:
            self.client.record_usage(customer_id="c1", idempotency_key="i1")
        except Exception as e:  # the same catch-all as the case above
            caught = e
        self.assertIsInstance(caught, UBBAPIError)
        self.assertIsInstance(caught, UBBError)

    def test_the_signal_sits_outside_exception_and_outside_ubb_error(self):
        """One narrowly defined type, not a parallel hierarchy: every ordinary
        SDK failure stays an ``Exception`` under ``UBBError``; only the stop
        does not."""
        self.assertTrue(issubclass(UBBStopRequested, BaseException))
        self.assertFalse(issubclass(UBBStopRequested, Exception))
        self.assertFalse(issubclass(UBBStopRequested, UBBError))
        self.assertTrue(issubclass(UBBError, Exception))

    def test_it_is_the_only_control_signal_the_package_exports(self):
        """Read off ``ubb.__all__`` rather than a list: a second type outside
        ``Exception`` would be the parallel hierarchy #179 §1.4 refused, and a
        renamed signal shows up here as a set that no longer matches."""
        signals = {
            name for name in ubb.__all__
            if isinstance(getattr(ubb, name), type)
            and issubclass(getattr(ubb, name), BaseException)
            and not issubclass(getattr(ubb, name), Exception)
        }
        self.assertEqual(signals, {"UBBStopRequested"})
        self.assertIs(ubb.UBBStopRequested, UBBStopRequested)

    @patch("ubb.metering.httpx.Client.post")
    def test_except_base_exception_still_catches_it_and_that_is_the_stated_boundary(self, mock_post):
        """#179 §1.4 accepts this: the objective is the common accidental
        failure mode, not technical impossibility. Pinned so the boundary of
        the guarantee is a statement rather than a discovery."""
        _responding(mock_post, _stopped_ack())
        caught = None
        try:
            self.client.record_usage(customer_id="c1", idempotency_key="i1")
        except BaseException as e:  # deliberately the widest net
            caught = e
        self.assertIsInstance(caught, UBBStopRequested)


class OptingOutOfTheRaiseTest(_ClientCase):
    """``raise_on_stop=False`` returns the verdict on the ack. Same object the
    signal carries, no information lost either way."""

    @patch("ubb.metering.httpx.Client.post")
    def test_false_returns_the_identical_verdict_instead_of_raising(self, mock_post):
        _responding(mock_post, _stopped_ack(
            stop_reason="task_limit", stop_scope="task", task_id="task_1"))
        returned = self.client.record_usage(customer_id="c1", idempotency_key="i1",
                                            task_id="task_1", raise_on_stop=False)
        self.assertTrue(returned.stop)
        self.assertEqual(returned.stop_reason, "task_limit")
        self.assertEqual(returned.stop_scope, "task")
        self.assertEqual(returned.task_id, "task_1")

        with self.assertRaises(UBBStopRequested) as cm:
            self.client.record_usage(customer_id="c1", idempotency_key="i1",
                                     task_id="task_1")
        self.assertEqual(cm.exception.result, returned)

    @patch("ubb.metering.httpx.Client.post")
    def test_true_is_what_the_default_already_does(self, mock_post):
        _responding(mock_post, _stopped_ack())
        with self.assertRaises(UBBStopRequested):
            self.client.record_usage(customer_id="c1", idempotency_key="i1",
                                     raise_on_stop=True)


class ABatchReportNeverRaisesTest(_ClientCase):
    """A batch is fifty independent facts. One stopped item must not abandon
    the other forty-nine: the report carries the stop per item, says whether
    any item asked for one, and names the earliest that did (#179 §1.6)."""

    def _batch_of(self, mock_post, items: list[dict]) -> None:
        _responding(mock_post, {
            "results": items,
            "accepted": sum(1 for i in items if i.get("accepted")),
            "rejected": sum(1 for i in items if not i.get("accepted")),
        })

    @staticmethod
    def _accepted(event_id: str, **verdict) -> dict:
        item = {"accepted": True, "event_id": event_id, "suspended": False,
                "costing_status": "known", "pricing_status": "known",
                "stop": False, "stop_reason": None, "stop_scope": None}
        item.update(verdict)
        return item

    @staticmethod
    def _rejected(code: str) -> dict:
        """The server's constant verdict for a rejected item: nothing was
        recorded, so nothing can have stopped (`api/v1/metering_endpoints.py`,
        `_rejected`)."""
        return {"accepted": False, "code": code, "detail": "refused",
                "stop": False, "stop_reason": None, "stop_scope": None}

    @patch("ubb.metering.httpx.Client.post")
    def test_a_stopped_item_among_unstopped_ones_is_reported_not_raised(self, mock_post):
        self._batch_of(mock_post, [
            self._accepted("evt_0"),
            self._accepted("evt_1", stop=True, stop_reason="task_limit",
                           stop_scope="task", task_id="task_1"),
            self._rejected("effective_at_too_old"),
            self._accepted("evt_3"),
        ])
        result = self.client.record_batch([
            {"customer_id": "c1", "idempotency_key": f"k{i}"} for i in range(4)
        ])
        self.assertEqual([r.event_id for r in result.results],
                         ["evt_0", "evt_1", None, "evt_3"])
        self.assertEqual([r.stop for r in result.results], [False, True, False, False])
        stopped = result.results[1]
        self.assertEqual(stopped.stop_reason, "task_limit")
        self.assertEqual(stopped.stop_scope, "task")
        self.assertEqual(stopped.data["task_id"], "task_1")
        self.assertTrue(result.stop)
        self.assertEqual(result.first_stop_index, 1)
        self.assertEqual((result.accepted, result.rejected), (3, 1))

    @patch("ubb.metering.httpx.Client.post")
    def test_the_earliest_stopped_item_is_the_one_named(self, mock_post):
        """Two stops, neither at position zero, so an aggregate that answered
        'the last one' or 'the first item' is told apart from the earliest."""
        self._batch_of(mock_post, [
            self._accepted("evt_0"),
            self._accepted("evt_1"),
            self._accepted("evt_2", stop=True, stop_reason="task_limit",
                           stop_scope="task"),
            self._accepted("evt_3", stop=True, stop_reason="customer_wide_stop",
                           stop_scope="customer"),
        ])
        result = self.client.record_batch([
            {"customer_id": "c1", "idempotency_key": f"k{i}"} for i in range(4)
        ])
        self.assertEqual(result.first_stop_index, 2)
        self.assertEqual(result.results[result.first_stop_index].stop_scope, "task")

    @patch("ubb.metering.httpx.Client.post")
    def test_a_batch_with_no_stop_says_so(self, mock_post):
        """Three shapes of 'no stop', and each reads as exactly False: an
        accepted item saying so, a rejected item (the server's constant
        trio), and an accepted item that OMITS the key — the contract's
        ``stop`` is optional with a false default, so an ack may leave it
        out, and a reader that passed the raw value through would hand a
        caller ``None`` for that one."""
        without_the_key = self._accepted("evt_2")
        del without_the_key["stop"]
        self._batch_of(mock_post, [self._accepted("evt_0"),
                                   self._rejected("validation_error"),
                                   without_the_key])
        result = self.client.record_batch([
            {"customer_id": "c1", "idempotency_key": f"k{i}"} for i in range(3)
        ])
        self.assertFalse(result.stop)
        self.assertIsNone(result.first_stop_index)
        for item in result.results:
            self.assertIs(item.stop, False)

    def test_the_batch_has_no_raising_knob_at_all(self):
        """A PIN, not evidence for the claim above: the signature is unchanged
        by this ticket and this passes against the previous code too. It is
        here so a knob added to the batch call later goes red at the address
        that says the non-raising posture is not a default a caller flips."""
        params = inspect.signature(MeteringClient.record_batch).parameters
        self.assertEqual(set(params), {"self", "events"})
