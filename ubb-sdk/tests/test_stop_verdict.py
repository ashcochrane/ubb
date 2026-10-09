"""The spend stop raises by default, survives a tenant's own ``except
Exception:``, and a batch report never raises (#421, #179 §1).

One-rule contract, unchanged: every usage report answers 200 and the ack
carries the verdict (``stop`` / ``stop_reason`` / ``stop_scope``). What this
module pins is what the CLIENT does with it. An unconfigured ``record_usage``
raises ``UBBStopRequested`` carrying that ack; the signal derives from
``BaseException`` so a catch-all around a provider loop cannot eat it and keep
spending; ``stop_behavior="return"`` returns the identical ack instead; and
``record_batch`` reports the stop per item and never raises, because one
stopped piece of work in a batch of fifty must not abandon the other
forty-nine.

What a stop does is chosen with a NAMED VALUE (#574): the two the registry
declares for ``stop_behavior``, held by the client as the generated
constants. A value outside those two is refused before anything is sent,
because the alternative is a call that records and then silently takes one
of the two paths the caller did not ask for.

Every body below carries `costing_status`, which the ack has published since
#317 and which the generated model requires. The literal is written out in each
body rather than sourced from `ubb.vocabulary`, deliberately: these are
transcripts of what the server sends, and a fixture that imported the same
constant the client parses against could not contradict a mistake in it. The
stop REASON is the exception, and for the opposite reason: the client never
parses against it (an unknown one travels as a plain string), so naming the
registry's constant costs nothing and says which bound the transcript claims
was reached (#457).
"""
import inspect
import unittest
from unittest.mock import patch, MagicMock

import ubb
from ubb.client import UBBClient
from ubb.metering import MeteringClient
from ubb.vocabulary import (
    REASON_CODE_HARD_FLOOR, REASON_CODE_TASK_COGS_CEILING,
    STOP_BEHAVIOR_RAISE, STOP_BEHAVIOR_RETURN, STOP_BEHAVIOR_VALUES,
)
from ubb.exceptions import (
    UBBAPIError, UBBError, UBBStopRequested, UBBValidationError,
)
from ubb._core.models.record_usage_response import RecordUsageResponse


def _stopped_ack(**overrides) -> dict:
    """A 200 body whose verdict says stop, customer scope unless overridden."""
    body = {
        "event_id": "e1", "suspended": False,
        "costing_status": "known", "pricing_status": "known",
        "stop": True, "stop_reason": REASON_CODE_HARD_FLOOR, "stop_scope": "customer",
        # The three are required keys (the owner's review of #612): a hard
        # floor names its mechanism, a zero floor and the balance below it.
        "trigger_source": "usage_ingest", "stop_bound_micros": 0,
        "stop_measured_micros": -250_000,
    }
    body.update(overrides)
    return body


def _ok_ack(**overrides) -> dict:
    body = {
        "event_id": "e1", "suspended": False,
        "costing_status": "known", "pricing_status": "known", "stop": False,
        "trigger_source": None, "stop_bound_micros": None, "stop_measured_micros": None,
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
        self.assertEqual(stop.stop_reason, REASON_CODE_HARD_FLOOR)
        self.assertIsNone(stop.task_id)
        self.assertEqual(stop.event_id, "e1")
        self.assertEqual(stop.idempotency_key, "i1")

    @patch("ubb.metering.httpx.Client.post")
    def test_a_task_stop_names_the_task_and_carries_its_totals(self, mock_post):
        """A ceiling crossing rides a 200 — the event landed and billed; the
        signal names the task and carries the post-event totals on the ack."""
        _responding(mock_post, _stopped_ack(
            stop_reason=REASON_CODE_TASK_COGS_CEILING, stop_scope="task", task_id="task_1",
            parent_task_id=None,
            task_total_billed_cost_micros=2_000_000,
            task_total_provider_cost_micros=1_100_000))
        with self.assertRaises(UBBStopRequested) as cm:
            self.client.record_usage(customer_id="c1", idempotency_key="i1",
                                     task_id="task_1")
        stop = cm.exception
        self.assertEqual(stop.stop_reason, REASON_CODE_TASK_COGS_CEILING)
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
    def test_the_signal_says_how_the_stop_was_applied_and_measured(self, mock_post):
        """#569: the mechanism, the bound and the amount measured read
        straight off the acknowledgement the signal carries — properties
        over ``result``, so the two cannot disagree."""
        _responding(mock_post, _stopped_ack(
            stop_reason=REASON_CODE_TASK_COGS_CEILING, stop_scope="task",
            task_id="task_1", trigger_source="usage_ingest",
            stop_bound_micros=5_000_000, stop_measured_micros=5_500_000))
        with self.assertRaises(UBBStopRequested) as cm:
            self.client.record_usage(customer_id="c1", idempotency_key="i1",
                                     task_id="task_1")
        stop = cm.exception
        self.assertEqual(stop.trigger_source, "usage_ingest")
        self.assertEqual(stop.stop_bound_micros, 5_000_000)
        self.assertEqual(stop.stop_measured_micros, 5_500_000)
        self.assertEqual(
            (stop.trigger_source, stop.stop_bound_micros, stop.stop_measured_micros),
            (stop.result.trigger_source, stop.result.stop_bound_micros,
             stop.result.stop_measured_micros))

    @patch("ubb.metering.httpx.Client.post")
    def test_a_real_zero_floor_is_zero_and_a_verdict_with_no_bound_is_none(self, mock_post):
        _responding(mock_post, _stopped_ack(
            trigger_source="enforcement_patrol", stop_bound_micros=0,
            stop_measured_micros=-1))
        with self.assertRaises(UBBStopRequested) as floor:
            self.client.record_usage(customer_id="c1", idempotency_key="i1")
        self.assertEqual(floor.exception.stop_bound_micros, 0)
        self.assertIsNotNone(floor.exception.stop_bound_micros)

        _responding(mock_post, _stopped_ack(
            stop_reason="task_not_active", stop_scope="task",
            trigger_source=None, stop_bound_micros=None,
            stop_measured_micros=None))
        with self.assertRaises(UBBStopRequested) as ended:
            self.client.record_usage(customer_id="c1", idempotency_key="i2")
        self.assertIsNone(ended.exception.trigger_source)
        self.assertIsNone(ended.exception.stop_bound_micros)
        self.assertIsNone(ended.exception.stop_measured_micros)

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


class ChoosingWhatAStopDoesTest(_ClientCase):
    """``stop_behavior`` names what a stop does: ``return`` hands back the
    verdict on the ack, ``raise`` is what the default already does. Same
    object either way, no information lost."""

    @patch("ubb.metering.httpx.Client.post")
    def test_return_hands_back_the_identical_verdict_instead_of_raising(self, mock_post):
        _responding(mock_post, _stopped_ack(
            stop_reason=REASON_CODE_TASK_COGS_CEILING, stop_scope="task", task_id="task_1"))
        returned = self.client.record_usage(customer_id="c1", idempotency_key="i1",
                                            task_id="task_1",
                                            stop_behavior=STOP_BEHAVIOR_RETURN)
        self.assertTrue(returned.stop)
        self.assertEqual(returned.stop_reason, REASON_CODE_TASK_COGS_CEILING)
        self.assertEqual(returned.stop_scope, "task")
        self.assertEqual(returned.task_id, "task_1")

        with self.assertRaises(UBBStopRequested) as cm:
            self.client.record_usage(customer_id="c1", idempotency_key="i1",
                                     task_id="task_1")
        self.assertEqual(cm.exception.result, returned)

    @patch("ubb.metering.httpx.Client.post")
    def test_raise_is_what_the_default_already_does(self, mock_post):
        _responding(mock_post, _stopped_ack())
        with self.assertRaises(UBBStopRequested):
            self.client.record_usage(customer_id="c1", idempotency_key="i1",
                                     stop_behavior=STOP_BEHAVIOR_RAISE)

    @patch("ubb.metering.httpx.Client.post")
    def test_the_two_values_are_the_words_a_caller_types(self, mock_post):
        """Written as LITERALS, on purpose and only here. Generated code and
        the documentation spell the value as a string, so what this pins is
        the spelling a caller's source carries — every other case names the
        generated constant, which would follow a registry edit silently."""
        _responding(mock_post, _stopped_ack())
        returned = self.client.record_usage(customer_id="c1", idempotency_key="i1",
                                            stop_behavior="return")
        self.assertTrue(returned.stop)
        with self.assertRaises(UBBStopRequested):
            self.client.record_usage(customer_id="c1", idempotency_key="i1",
                                     stop_behavior="raise")

    @patch("ubb.metering.httpx.Client.post")
    def test_neither_value_changes_an_acknowledgement_that_carries_no_stop(self, mock_post):
        _responding(mock_post, _ok_ack())
        for behavior in sorted(STOP_BEHAVIOR_VALUES):
            with self.subTest(stop_behavior=behavior):
                result = self.client.record_usage(
                    customer_id="c1", idempotency_key="i1", stop_behavior=behavior)
                self.assertFalse(result.stop)

    def test_the_default_is_the_raising_value_on_both_clients(self):
        for client in (MeteringClient, UBBClient):
            with self.subTest(client=client.__name__):
                parameter = inspect.signature(
                    client.record_usage).parameters["stop_behavior"]
                self.assertEqual(parameter.default, STOP_BEHAVIOR_RAISE)


class AValueOutsideTheTwoIsRefusedTest(_ClientCase):
    """The concept is closed at two values. Anything else is refused inside
    the SDK's own error family, BEFORE any HTTP: a call that recorded the
    event and then took a path the caller never named would be the silent
    option, and here the silent option is the one that keeps spending."""

    #: What a caller plausibly sends by mistake: the two booleans the
    #: keyword replaced, a near-miss spelling, the wrong case, nothing — and
    #: an unhashable one, which a set lookup would answer with a
    #: ``TypeError`` of its own rather than with this refusal.
    REFUSED = (True, False, None, "", "Raise", "RETURN", "ignore", "returns",
               ["raise"])

    @patch("ubb.metering.httpx.Client.post")
    def test_it_is_refused_before_anything_is_sent(self, mock_post):
        _responding(mock_post, _stopped_ack())
        for value in self.REFUSED:
            with self.subTest(stop_behavior=value):
                with self.assertRaises(UBBError) as cm:
                    self.client.record_usage(customer_id="c1", idempotency_key="i1",
                                             stop_behavior=value)
                self.assertIsInstance(cm.exception, UBBValidationError)
                self.assertIn(repr(value), str(cm.exception))
                for accepted in STOP_BEHAVIOR_VALUES:
                    self.assertIn(repr(accepted), str(cm.exception))
        mock_post.assert_not_called()

    @patch("ubb.metering.httpx.Client.post")
    def test_the_facade_refuses_it_the_same_way(self, mock_post):
        facade = UBBClient(api_key="ubb_live_x", base_url="http://localhost:8001",
                           max_retries=0)
        self.addCleanup(facade.close)
        with self.assertRaises(UBBValidationError):
            facade.record_usage("c1", "i1", stop_behavior="ignore")
        mock_post.assert_not_called()

    @patch("ubb.metering.httpx.Client.post")
    def test_the_boolean_it_replaced_is_gone_from_both_clients(self, mock_post):
        """Not renamed beside the new keyword and not kept as an alias: a
        caller still passing the boolean gets Python's own ``TypeError``
        naming it, before anything is sent — the loudest answer available,
        and the one an alias that quietly mapped it would have hidden."""
        facade = UBBClient(api_key="ubb_live_x", base_url="http://localhost:8001",
                           max_retries=0)
        self.addCleanup(facade.close)
        for client in (self.client, facade):
            with self.subTest(client=type(client).__name__):
                with self.assertRaises(TypeError) as cm:
                    client.record_usage("c1", "i1", raise_on_stop=False)
                self.assertIn("raise_on_stop", str(cm.exception))
        mock_post.assert_not_called()


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
                "stop": False, "stop_reason": None, "stop_scope": None,
                "trigger_source": None, "stop_bound_micros": None,
                "stop_measured_micros": None}
        item.update(verdict)
        return item

    @staticmethod
    def _rejected(code: str) -> dict:
        """The server's constant verdict for a rejected item: nothing was
        recorded, so nothing can have stopped (`api/v1/metering_endpoints.py`,
        `_rejected`) — and nothing applied, bounded or measured a stop."""
        return {"accepted": False, "code": code, "detail": "refused",
                "stop": False, "stop_reason": None, "stop_scope": None,
                "trigger_source": None, "stop_bound_micros": None,
                "stop_measured_micros": None}

    @patch("ubb.metering.httpx.Client.post")
    def test_each_item_carries_how_its_stop_was_applied_typed(self, mock_post):
        """#569: the three facts ride every item, read off its typed model —
        a ceiling's mechanism and figures, a Pool stop's, a real zero floor
        as 0, and None on an unstopped or rejected item."""
        self._batch_of(mock_post, [
            self._accepted("evt_0", stop=True,
                           stop_reason=REASON_CODE_TASK_COGS_CEILING,
                           stop_scope="task", trigger_source="usage_ingest",
                           stop_bound_micros=5_000_000,
                           stop_measured_micros=5_500_000),
            self._accepted("evt_1", stop=True, stop_reason=REASON_CODE_HARD_FLOOR,
                           stop_scope="customer",
                           trigger_source="charge_projection",
                           stop_bound_micros=0, stop_measured_micros=-3_000_000),
            self._accepted("evt_2", trigger_source=None, stop_bound_micros=None,
                           stop_measured_micros=None),
            self._rejected("validation_error"),
        ])
        result = self.client.record_batch([
            {"customer_id": "c1", "idempotency_key": f"k{i}"} for i in range(4)
        ])
        facts = [(r.trigger_source, r.stop_bound_micros, r.stop_measured_micros)
                 for r in result.results]
        self.assertEqual(facts, [("usage_ingest", 5_000_000, 5_500_000),
                                 ("charge_projection", 0, -3_000_000),
                                 (None, None, None), (None, None, None)])
        self.assertIs(type(result.results[1].stop_bound_micros), int)

    @patch("ubb.metering.httpx.Client.post")
    def test_a_stopped_item_among_unstopped_ones_is_reported_not_raised(self, mock_post):
        self._batch_of(mock_post, [
            self._accepted("evt_0"),
            self._accepted("evt_1", stop=True, stop_reason=REASON_CODE_TASK_COGS_CEILING,
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
        self.assertEqual(stopped.stop_reason, REASON_CODE_TASK_COGS_CEILING)
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
            self._accepted("evt_2", stop=True, stop_reason=REASON_CODE_TASK_COGS_CEILING,
                           stop_scope="task"),
            self._accepted("evt_3", stop=True, stop_reason=REASON_CODE_HARD_FLOOR,
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
