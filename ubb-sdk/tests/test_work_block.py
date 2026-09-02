"""A unit of work is started from the SDK and declares how it ended, and a
forgotten declaration is loud and recoverable rather than silently invented
(#422; #187 stories 26–28 and §24; #179 §2).

``start_task`` is one call on the flat client and answers with a handle — the
unit of work UBB registered, or the one the key already claimed — and the
handle is the one place to say how that work ended: ``complete()``,
``fail(outcome_reason)`` or ``cancel()``, three methods over the one close
route. Used as a context manager around the whole run it implements the five
exits #179 §2 rules: an explicit declaration is preserved; a clean exit with
none raises ``TaskOutcomeRequired`` and LEAVES THE WORK OPEN; an ordinary
exception declares ``failed`` with ``execution_failed`` and re-raises; a spend
stop, an interrupt or any other ``BaseException`` propagates with nothing
invented.

Every body below is a transcript of what the server sends —
`api/v1/schemas.py::start_task_out` for a start, the close route's own literal
for a close — with the values SPELLED, deliberately, so a fixture can
contradict a mistake in the constants the client parses against. What the
client SENDS is asserted through `ubb.vocabulary`, because that is the claim:
the wrapper declares the registry's values and never a string somebody typed.
"""
import asyncio
import inspect
import unittest
from unittest.mock import patch, MagicMock

import httpx

import ubb
from ubb import vocabulary
from ubb.exceptions import (
    TaskOutcomeRequired, UBBAPIError, UBBConnectionError, UBBError,
    UBBStopRequested,
)
from ubb.metering import MeteringClient, StartedTask, TERMINAL_TASK_STATUSES
from ubb._core.models.close_task_response import CloseTaskResponse
from ubb._core.models.start_task_response import StartTaskResponse


START_ROUTE = "/api/v1/tasks"
CLOSE_ROUTE = "/api/v1/tasks/task_1/close"


def _started(**overrides) -> dict:
    """What `POST /api/v1/tasks` answers for a fresh registration."""
    body = {
        "task_id": "task_1", "parent_task_id": None, "task_type": "transcode",
        "status": "active", "provider_cost_limit_micros": 5_000_000,
        "agreed_price_micros": None, "external_task_id": "",
        "created_at": "2026-09-02T09:00:00+00:00", "replayed": False,
    }
    body.update(overrides)
    return body


def _closed(**overrides) -> dict:
    """What the close route answers once the declaration landed."""
    body = {
        "task_id": "task_1", "parent_task_id": None, "status": "completed",
        "outcome": "delivered", "replayed": False, "charge_created": False,
        "total_billed_cost_micros": 0, "total_provider_cost_micros": 0,
        "unresolved_event_count": 0, "unpriced_event_count": 0, "event_count": 0,
    }
    body.update(overrides)
    return body


def _stopped_ack() -> dict:
    """A usage acknowledgement whose verdict says stop, task scope: the event
    landed on work that is no longer active."""
    return {
        "event_id": "e1", "suspended": False, "costing_status": "known",
        "pricing_status": "known", "stop": True, "stop_reason": "task_not_active",
        "stop_scope": "task", "task_id": "task_1",
    }


def _answering(mock_post, *bodies: dict) -> None:
    """The wire answers each POST with the next body, in order."""
    mock_post.side_effect = [
        MagicMock(status_code=200, json=(lambda b=body: b)) for body in bodies
    ]


def _sent(mock_post, index: int):
    """``(route, json body)`` of the ``index``-th request that reached the wire."""
    call = mock_post.call_args_list[index]
    return call.args[0], call.kwargs.get("json")


class _ClientCase(unittest.TestCase):
    def setUp(self):
        self.client = MeteringClient(api_key="ubb_live_x",
                                     base_url="http://localhost:8001",
                                     max_retries=0)

    def tearDown(self):
        self.client.close()

    def start(self, mock_post, *later: dict, **overrides) -> StartedTask:
        """A started unit of work, with ``later`` queued as the answers to
        whatever the block sends next."""
        _answering(mock_post, _started(**overrides), *later)
        return self.client.start_task("c1", "nightly-42", task_type="transcode")


class TheStartIsOneCallTest(_ClientCase):
    """One flat method, one route, and the caller's key is the second
    positional argument — the shape ``record_usage`` already has."""

    @patch("ubb.metering.httpx.Client.post")
    def test_a_start_names_the_route_and_sends_the_key(self, mock_post):
        _answering(mock_post, _started())
        task = self.client.start_task(
            "c1", "nightly-42", task_type="transcode",
            provider_cost_limit_micros=5_000_000, external_task_id="run-7",
            metadata={"report": "weekly"})
        route, body = _sent(mock_post, 0)
        self.assertEqual(route, START_ROUTE)
        self.assertEqual(body, {
            "customer_id": "c1", "idempotency_key": "nightly-42",
            "task_type": "transcode", "provider_cost_limit_micros": 5_000_000,
            "external_task_id": "run-7", "metadata": {"report": "weekly"},
        })
        self.assertIsInstance(task, StartedTask)
        self.assertIsInstance(task.result, StartTaskResponse)
        self.assertEqual(task.task_id, "task_1")
        self.assertEqual(task.task_type, "transcode")
        self.assertIs(task.replayed, False)
        self.assertTrue(task.is_open)
        self.assertIsNone(task.closed)

    @patch("ubb.metering.httpx.Client.post")
    def test_what_the_caller_did_not_say_is_not_sent(self, mock_post):
        """The server tells *not declared* apart from *declared empty* on the
        label and the bag, so a keyword left at its default stays off the
        wire rather than arriving as an empty value."""
        _answering(mock_post, _started())
        self.client.start_task("c1", "nightly-42")
        _, body = _sent(mock_post, 0)
        self.assertEqual(body, {"customer_id": "c1",
                                "idempotency_key": "nightly-42"})

    @patch("ubb.metering.httpx.Client.post")
    def test_contained_work_names_its_parent_through_the_same_call(self, mock_post):
        _answering(mock_post, _started(task_id="sub_1", parent_task_id="task_1"))
        task = self.client.start_task("c1", "nightly-42-1",
                                      parent_task_id="task_1")
        _, body = _sent(mock_post, 0)
        self.assertEqual(body["parent_task_id"], "task_1")
        self.assertEqual(task.parent_task_id, "task_1")
        self.assertEqual(task.task_id, "sub_1")

    def test_the_key_is_required(self):
        """A PIN of the signature rather than evidence for a behaviour: no
        default and no generated one, because a key minted on the line would
        be a new value on every retry, and a retried start a second unit of
        work. It goes red at this address if a default is ever added; what it
        asserts is the parameter by name, not Python's refusal in general."""
        with self.assertRaisesRegex(TypeError, "idempotency_key"):
            self.client.start_task("c1")
        signature = inspect.signature(MeteringClient.start_task)
        self.assertIs(signature.parameters["idempotency_key"].default,
                      inspect.Parameter.empty)

    @patch("ubb.metering.httpx.Client.post")
    def test_a_replayed_start_hands_back_the_original(self, mock_post):
        """The key was already claimed: the answer is the unit of work that
        claim registered, with ITS values standing over whatever this attempt
        sent — the label here differs and the original's is what comes back —
        and ``replayed`` says nothing was created."""
        _answering(mock_post, _started(
            task_id="task_original", external_task_id="the-first-attempt",
            created_at="2026-09-01T23:00:00+00:00", replayed=True))
        task = self.client.start_task("c1", "nightly-42", task_type="transcode",
                                      external_task_id="a-later-attempt")
        self.assertIs(task.replayed, True)
        self.assertEqual(task.task_id, "task_original")
        self.assertEqual(task.external_task_id, "the-first-attempt")
        self.assertEqual(task.created_at, "2026-09-01T23:00:00+00:00")
        self.assertEqual(mock_post.call_count, 1)
        self.assertTrue(task.is_open)


class TheThreeDeclarationsTest(_ClientCase):
    """``complete()`` / ``fail(outcome_reason)`` / ``cancel()`` — the three
    ways a unit of work ends, each sending the registry's own value for the
    declaration over the one close route. There is no fourth method taking an
    outcome word, and no payload keyword beside them (spec §24)."""

    @patch("ubb.metering.httpx.Client.post")
    def test_complete_declares_delivery(self, mock_post):
        task = self.start(mock_post, _closed())
        ack = task.complete()
        route, body = _sent(mock_post, 1)
        self.assertEqual(route, CLOSE_ROUTE)
        self.assertEqual(body, {"outcome": vocabulary.TASK_OUTCOME_DELIVERED})
        self.assertIsInstance(ack, CloseTaskResponse)
        self.assertIs(task.closed, ack)
        self.assertEqual(task.declared, vocabulary.TASK_OUTCOME_DELIVERED)
        self.assertFalse(task.is_open)

    @patch("ubb.metering.httpx.Client.post")
    def test_fail_sends_the_reason_it_requires(self, mock_post):
        task = self.start(mock_post, _closed(status="failed", outcome="failed"))
        task.fail(vocabulary.OUTCOME_REASON_TIMEOUT,
                  reason_detail="the provider took eleven minutes")
        _, body = _sent(mock_post, 1)
        self.assertEqual(body, {
            "outcome": vocabulary.TASK_OUTCOME_FAILED,
            "outcome_reason": vocabulary.OUTCOME_REASON_TIMEOUT,
            "reason_detail": "the provider took eleven minutes",
        })
        self.assertFalse(task.is_open)

    @patch("ubb.metering.httpx.Client.post")
    def test_fail_without_a_reason_is_refused_before_any_request(self, mock_post):
        """The reason is a required positional: the server refuses a failure
        with no reason, and a wrapper that let the argument be omitted would
        turn that refusal into a round trip. ``unspecified`` is always
        available, so requiring one costs the caller nothing. The signature
        half is a PIN (the parameter, by name); the evidence half is the
        request count — a wrapper that defaulted the reason sends one."""
        task = self.start(mock_post)
        with self.assertRaisesRegex(TypeError, "outcome_reason"):
            task.fail()
        self.assertEqual(mock_post.call_count, 1)
        self.assertTrue(task.is_open)

    @patch("ubb.metering.httpx.Client.post")
    def test_cancel_needs_no_reason(self, mock_post):
        task = self.start(mock_post, _closed(status="cancelled",
                                             outcome="cancelled"))
        task.cancel()
        _, body = _sent(mock_post, 1)
        self.assertEqual(body, {"outcome": vocabulary.TASK_OUTCOME_CANCELLED})
        self.assertFalse(task.is_open)

    @patch("ubb.metering.httpx.Client.post")
    def test_cancel_carries_a_reason_when_one_is_given(self, mock_post):
        task = self.start(mock_post, _closed(status="cancelled",
                                             outcome="cancelled"))
        task.cancel(outcome_reason=vocabulary.OUTCOME_REASON_CUSTOMER_CANCELLED,
                    reason_detail="the customer closed the tab")
        _, body = _sent(mock_post, 1)
        self.assertEqual(body, {
            "outcome": vocabulary.TASK_OUTCOME_CANCELLED,
            "outcome_reason": vocabulary.OUTCOME_REASON_CUSTOMER_CANCELLED,
            "reason_detail": "the customer closed the tab",
        })

    def test_the_handle_has_no_single_close_taking_an_outcome_and_no_payload_word(self):
        """A PIN of two rulings rather than evidence for a behaviour (spec
        §24): the three-method shape is the whole close surface on the handle,
        and a completion takes no business payload under any keyword — the
        word for a tenant's own key-values is ``metadata``, which already
        exists on the unit of work, and no ``outcome=`` / ``result=`` /
        ``payload=`` is coined beside it. A method added later goes red at
        the address that says why it is not wanted."""
        methods = {name for name, member in inspect.getmembers(StartedTask)
                   if callable(member) and not name.startswith("_")}
        self.assertEqual(methods, {"complete", "fail", "cancel"})
        self.assertEqual(
            list(inspect.signature(StartedTask.complete).parameters), ["self"])
        for method in (StartedTask.fail, StartedTask.cancel):
            self.assertEqual(
                set(inspect.signature(method).parameters) - {"self"},
                {"outcome_reason", "reason_detail"})


class TheFiveExitsTest(_ClientCase):
    """The wrapper declares an outcome only where control flow is evidence
    for it (#179 §2.2). Each case counts what reached the wire, because the
    claim in every row is about what was — and was not — sent."""

    @patch("ubb.metering.httpx.Client.post")
    def test_an_explicit_declaration_is_preserved(self, mock_post):
        with self.start(mock_post, _closed()) as task:
            task.complete()
        self.assertEqual(mock_post.call_count, 2)
        self.assertFalse(task.is_open)

    @patch("ubb.metering.httpx.Client.post")
    def test_a_clean_exit_with_no_declaration_raises_and_leaves_the_work_open(self, mock_post):
        """Nothing is sent and nothing is invented: only the start reached the
        wire, the handle is still open, and the signal carries it so a later
        explicit declaration lands — the exception reports a missing
        declaration; it does not destroy the thing that is missing one."""
        with self.assertRaises(TaskOutcomeRequired) as cm:
            with self.start(mock_post, _closed()) as task:
                pass
        missing = cm.exception
        self.assertEqual(mock_post.call_count, 1)   # the start, and only it
        self.assertTrue(task.is_open)
        self.assertIsNone(task.declared)
        self.assertIs(missing.task, task)
        self.assertEqual(missing.task_id, "task_1")
        self.assertEqual(missing.task_type, "transcode")
        self.assertEqual(missing.status, vocabulary.TASK_STATUS_ACTIVE)
        text = str(missing)
        self.assertIn("task_1", text)
        self.assertIn("open", text)
        for declaration in ("complete()", "fail(", "cancel()"):
            self.assertIn(declaration, text)
        # RECOVERABLE: the declaration the block forgot still lands.
        missing.task.complete()
        route, body = _sent(mock_post, 1)
        self.assertEqual(route, CLOSE_ROUTE)
        self.assertEqual(body, {"outcome": vocabulary.TASK_OUTCOME_DELIVERED})
        self.assertFalse(task.is_open)

    @patch("ubb.metering.httpx.Client.post")
    def test_a_replayed_start_on_ended_work_owes_no_declaration(self, mock_post):
        """A retry after a lost response can hand back a unit of work that
        already ended. It is not open, so a clean exit raises nothing and
        sends nothing — raising here would demand a declaration on work that
        already has one."""
        with self.start(mock_post, status="completed", replayed=True) as task:
            pass
        self.assertFalse(task.is_open)
        self.assertEqual(mock_post.call_count, 1)

    @patch("ubb.metering.httpx.Client.post")
    def test_an_ordinary_exception_declares_failed_with_execution_failed_and_re_raises(self, mock_post):
        """An unhandled ``Exception`` escaping the block is evidence the work
        failed: the wrapper declares exactly that — ``failed``, reason
        ``execution_failed``, the exception's type as the sentence beside it
        — and the caller's own exception is what propagates."""
        with self.assertRaises(ValueError) as cm:
            with self.start(mock_post, _closed(status="failed",
                                               outcome="failed")) as task:
                raise ValueError("the provider returned garbage")
        self.assertEqual(str(cm.exception), "the provider returned garbage")
        self.assertEqual(mock_post.call_count, 2)
        route, body = _sent(mock_post, 1)
        self.assertEqual(route, CLOSE_ROUTE)
        self.assertEqual(body, {
            "outcome": vocabulary.TASK_OUTCOME_FAILED,
            "outcome_reason": vocabulary.OUTCOME_REASON_EXECUTION_FAILED,
            "reason_detail": "ValueError",
        })
        self.assertEqual(task.declared, vocabulary.TASK_OUTCOME_FAILED)
        self.assertFalse(task.is_open)

    @patch("ubb.metering.httpx.Client.post")
    def test_an_exception_after_an_explicit_declaration_declares_nothing_more(self, mock_post):
        """"If still open" is the guard: work already declared delivered is
        not re-declared failed because something broke after the fact."""
        with self.assertRaises(RuntimeError):
            with self.start(mock_post, _closed()) as task:
                task.complete()
                raise RuntimeError("after the fact")
        self.assertEqual(mock_post.call_count, 2)
        _, body = _sent(mock_post, 1)
        self.assertEqual(body["outcome"], vocabulary.TASK_OUTCOME_DELIVERED)

    @patch("ubb.metering.httpx.Client.post")
    def test_when_reporting_the_failure_also_fails_the_original_stays_primary(self, mock_post):
        """#179 §2.3: a developer debugging a broken workflow must not be
        handed a UBB transport error in place of their own stack trace. The
        secondary failure is attached to the original as a note, never raised
        in its place."""
        mock_post.side_effect = [
            MagicMock(status_code=200, json=lambda: _started()),
            httpx.ConnectError("UBB is unreachable"),
        ]
        with self.assertRaises(ValueError) as cm:
            with self.start_without_answers() as task:
                raise ValueError("the work broke")
        self.assertEqual(str(cm.exception), "the work broke")
        self.assertEqual(mock_post.call_count, 2)
        notes = " ".join(getattr(cm.exception, "__notes__", []))
        self.assertIn("UBB", notes)
        self.assertIn(UBBConnectionError.__name__, notes)
        # Nothing reached UBB, so nothing was declared: the handle is still
        # open, and the failure can be reported again once UBB is back.
        self.assertIsNone(task.declared)
        self.assertTrue(task.is_open)

    @patch("ubb.metering.httpx.Client.post")
    def test_a_refused_declaration_is_not_followed_by_a_second_one(self, mock_post):
        """A declaration the server refuses — here a close against work UBB
        already ended — raises out of the call as an ordinary error, and the
        block's exit does NOT then declare ``failed`` on top of it: an
        explicit terminal call was made, and its refusal is the caller's to
        handle. Exactly two requests reach the wire — the start and the
        refused close — which is what recording the declaration BEFORE the
        request goes out buys."""
        # The problem+json body `api/v1/problems.py::problem_response`
        # renders for the close route's 409, extensions and all.
        refused = {
            "type": "https://ubb.dev/errors/task_already_terminal",
            "title": "This unit of work has already ended, and differently",
            "status": 409, "code": "task_already_terminal",
            "detail": "this unit is already killed and cannot be closed as "
                      "delivered",
            "task_status": "killed", "charge_created": False,
        }
        mock_post.side_effect = [
            MagicMock(status_code=200, json=lambda: _started()),
            MagicMock(status_code=409, headers={}, text=str(refused),
                      json=lambda: refused),
        ]
        with self.assertRaises(UBBAPIError) as cm:
            with self.start_without_answers() as task:
                task.complete()
        self.assertEqual(cm.exception.code, "task_already_terminal")
        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(task.declared, vocabulary.TASK_OUTCOME_DELIVERED)
        self.assertIsNone(task.closed)
        self.assertFalse(task.is_open)

    @patch("ubb.metering.httpx.Client.post")
    def test_a_declaration_that_never_reached_ubb_is_not_a_declaration(self, mock_post):
        """The other side of the case above. A refusal is a declaration UBB
        answered; a connection failure means nothing arrived, so the handle
        is still open — and a caller who swallows that failure and lets the
        block end cleanly is told so rather than left with open work and no
        signal, which is the quiet option #179 §2.5 rejected. The forgotten
        declaration then lands on the same handle; a close is idempotent, so
        one that did arrive and lost its answer replays rather than doubles."""
        mock_post.side_effect = [
            MagicMock(status_code=200, json=lambda: _started()),
            httpx.ConnectError("UBB is unreachable"),
            MagicMock(status_code=200, json=lambda: _closed()),
        ]
        with self.assertRaises(TaskOutcomeRequired) as cm:
            with self.start_without_answers() as task:
                try:
                    task.complete()
                except UBBConnectionError:
                    pass  # the caller's own catch, on purpose
        self.assertIsNone(task.declared)
        self.assertTrue(task.is_open)
        self.assertEqual(mock_post.call_count, 2)   # the start, the lost close
        cm.exception.task.complete()
        self.assertEqual(mock_post.call_count, 3)
        self.assertFalse(task.is_open)

    def start_without_answers(self) -> StartedTask:
        """A start whose later answers the test has already queued itself."""
        return self.client.start_task("c1", "nightly-42", task_type="transcode")

    # ---- what is NOT evidence of business failure: one case per kind ----

    def _propagates_untouched(self, mock_post, signal: BaseException):
        with self.assertRaises(type(signal)) as cm:
            with self.start(mock_post, _closed()) as task:
                raise signal
        self.assertIs(cm.exception, signal)
        self.assertEqual(mock_post.call_count, 1)   # the start, and only it
        self.assertTrue(task.is_open)
        self.assertIsNone(task.declared)

    @patch("ubb.metering.httpx.Client.post")
    def test_a_keyboard_interrupt_propagates_with_no_fabricated_outcome(self, mock_post):
        """A Ctrl-C during work that had in fact delivered must not write
        ``failed`` onto it (#179 §2.6)."""
        self._propagates_untouched(mock_post, KeyboardInterrupt())

    @patch("ubb.metering.httpx.Client.post")
    def test_a_system_exit_propagates_with_no_fabricated_outcome(self, mock_post):
        self._propagates_untouched(mock_post, SystemExit(1))

    @patch("ubb.metering.httpx.Client.post")
    def test_a_cancellation_propagates_with_no_fabricated_outcome(self, mock_post):
        self._propagates_untouched(mock_post, asyncio.CancelledError())

    @patch("ubb.metering.httpx.Client.post")
    def test_a_spend_stop_raised_inside_the_block_propagates_unchanged(self, mock_post):
        """The stop is UBB's own signal, raised by ``record_usage`` inside the
        block, and it is evidence of a stop and of nothing about whether the
        work delivered: the wrapper never marks it failed. Driven through the
        real recording path rather than raised by hand, so the classification
        is proved structural — the signal sits outside ``Exception`` and no
        exclusion list is consulted."""
        _answering(mock_post, _started(), _stopped_ack())
        with self.assertRaises(UBBStopRequested) as cm:
            with self.client.start_task("c1", "nightly-42") as task:
                self.client.record_usage("c1", "e1", task_id=task.task_id)
        self.assertEqual(cm.exception.stop_reason, "task_not_active")
        self.assertEqual(mock_post.call_count, 2)   # the start and the event
        self.assertEqual(_sent(mock_post, 1)[0], "/api/v1/metering/usage")
        self.assertTrue(task.is_open)
        self.assertIsNone(task.declared)


class TheMissingOutcomeSignalIsAnOrdinaryErrorTest(unittest.TestCase):
    """``TaskOutcomeRequired`` is an integration defect reported in
    production, not a control signal: it sits under ``UBBError`` like every
    other failure this SDK raises, so the one type outside ``Exception`` stays
    the spend stop (`test_stop_verdict` pins that set at exactly one)."""

    def test_it_is_an_exception_under_ubb_error(self):
        self.assertTrue(issubclass(TaskOutcomeRequired, UBBError))
        self.assertTrue(issubclass(TaskOutcomeRequired, Exception))

    def test_the_handle_and_the_signal_are_exported(self):
        self.assertIs(ubb.TaskOutcomeRequired, TaskOutcomeRequired)
        self.assertIs(ubb.StartedTask, StartedTask)
        self.assertIs(ubb.StartTaskResponse, StartTaskResponse)
        for name in ("TaskOutcomeRequired", "StartedTask", "StartTaskResponse"):
            self.assertIn(name, ubb.__all__)


class TheLifecycleStatesAreConstantsTest(unittest.TestCase):
    """Story 28: the integrator branches on a name rather than a string they
    typed. The values themselves are generated into ``ubb.vocabulary``; what
    this client adds is the one derived set it needs and hands on — every
    state a unit of work can have ended in — read off the registry's closed
    set rather than listed a second time."""

    def test_the_terminal_set_is_every_state_but_the_live_one(self):
        """The PROPERTIES of the set, not a restatement of its derivation —
        restating `VALUES - {ACTIVE}` here could only catch the comprehension
        being replaced by a literal."""
        self.assertNotIn(vocabulary.TASK_STATUS_ACTIVE, TERMINAL_TASK_STATUSES)
        self.assertEqual(len(TERMINAL_TASK_STATUSES), 5)
        for state in (vocabulary.TASK_STATUS_COMPLETED,
                      vocabulary.TASK_STATUS_FAILED,
                      vocabulary.TASK_STATUS_CANCELLED,
                      vocabulary.TASK_STATUS_KILLED,
                      vocabulary.TASK_STATUS_EXPIRED):
            self.assertIn(state, TERMINAL_TASK_STATUSES)
