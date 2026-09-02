from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # the annotations only; this module stays free of the core
    from ubb._core.models.record_usage_response import RecordUsageResponse
    from ubb.metering import StartedTask


class UBBError(Exception):
    pass

class UBBAuthError(UBBError):
    pass

class UBBAPIError(UBBError):
    """An error response from the API (RFC 9457 problem+json, #78).

    ``code`` is the stable snake_case registry code — the machine contract;
    ``detail`` is prose and may change wording without notice."""
    def __init__(self, status_code: int, detail: str = "", code: str | None = None):
        self.status_code = status_code
        self.detail = detail
        self.code = code
        self.retry_after: float | None = None
        super().__init__(f"API error {status_code}"
                         + (f" [{code}]" if code else "") + f": {detail}")

class UBBValidationError(UBBError):
    """Client-side input validation failure (e.g., micros not divisible by 10_000)."""
    pass

class UBBConnectionError(UBBError):
    """Cannot reach the API (network error or timeout)."""
    def __init__(self, message: str, original: Exception | None = None):
        self.original = original
        super().__init__(message)

# A MISSING DECLARATION IS AN ORDINARY ERROR, NOT A CONTROL SIGNAL (#422,
# spec §24, #179 §2.4–§2.5). It reports an integration defect — a work block
# ended without saying how the work ended — and it is wanted in production,
# not only in development, because both quiet options were rejected: closing
# as `cancelled` puts a tenant-declared word onto work nobody declared
# anything about (and strips a charge that may have been earned), and leaving
# the work open silently holds a concurrency slot and any prepaid reservation
# until expiry, with no signal at all for a tenant that is not enforcing.
# Raising while leaving the work open is truthful about the unknown ending,
# visible at once, and recoverable.
#
# It sits under `UBBError` like every other failure this SDK raises: the ONE
# type outside `Exception` is the spend stop below, and `test_stop_verdict.py`
# pins that set at exactly one. #179 §2.4 also asks this to carry the unit's
# expiry time; the registration does not publish one, so it carries what the
# wire does — the handle, and through it the identity and the last state
# this client saw.
class TaskOutcomeRequired(UBBError):
    """A work block ended cleanly and nothing declared how the work ended.

    Raised by the handle ``start_task`` returns when its ``with`` block exits
    without an exception and none of ``complete()``, ``fail(...)`` or
    ``cancel()`` was called on it. THE UNIT OF WORK IS STILL OPEN on UBB's
    side: nothing was sent and nothing was invented, because the forgiving
    answer and the answer that moves money are the same word and UBB will not
    guess between them. Declare it explicitly — ``exc.task.complete()``,
    ``exc.task.fail(outcome_reason)`` or ``exc.task.cancel()`` land exactly
    as they would have inside the block.

    ``task`` is the handle itself; ``task_id``, ``task_type`` and ``status``
    (the last state this client saw for it) read straight off it."""
    def __init__(self, task: StartedTask):
        self.task = task
        super().__init__(
            f"Unit of work {task.task_id} left its block without a declared "
            f"outcome. It is still open on UBB's side — nothing was sent and "
            f"nothing was invented. Call complete(), fail(outcome_reason) or "
            f"cancel() on it explicitly.")

    @property
    def task_id(self) -> str:
        return self.task.task_id

    @property
    def task_type(self) -> str:
        return self.task.task_type

    @property
    def status(self) -> str:
        return self.task.status

# The spend stop is the ONE type in this SDK outside `Exception`, and it is
# deliberately not a `UBBError` (#179 §1.4, #421). `UBBStoppedError` used to
# sit under `UBBError`, which meant a tenant's `except Exception: continue`
# around a provider loop ate the stop and kept spending — and excluding it by
# name inside UBB's own code cannot reach tenant code. Python draws this line
# already for `KeyboardInterrupt`, `SystemExit` and `CancelledError`. One narrow
# type, never the start of a parallel hierarchy: `test_stop_verdict.py` reads
# the set of such types off `ubb.__all__` and pins it at exactly this one.
# The convenience attributes below are properties over `result` rather than
# copies, so the signal and the acknowledgement it carries cannot disagree.
class UBBStopRequested(BaseException):
    """UBB recorded the event and is asking you to stop spending for a scope.

    Raised by ``record_usage`` BY DEFAULT when the acknowledgement carries a
    stop verdict (``stop=True``): the work crossed its supplier-cost ceiling
    or floor snapshot (scope "task"), the event landed on work that is no
    longer active, or the customer crossed a floor or ceiling of their own
    (scope "customer"). THE EVENT WAS RECORDED AND CHARGED. The write
    committed, the acknowledgement was built, and only then was this raised,
    carrying it — so it is a control signal about the NEXT call and never a
    failed submission. Do not resend the event; stop sending work for
    ``stop_scope``.

    It derives from ``BaseException`` — not ``Exception``, not ``UBBError`` —
    for the reason ``KeyboardInterrupt`` does: your own ``except Exception:``
    around a provider loop cannot swallow it and carry on spending. Catch it
    by name, once, at the outermost boundary that can honour its scope; a
    helper that knows about one call has neither the authority nor the
    context to halt everything for a customer. A bare ``except:`` or
    ``except BaseException:`` still catches it — re-raise anything outside
    ``Exception`` unless you are handling this signal by name. Every
    ordinary SDK failure stays an ``Exception`` under ``UBBError``.

    ``result`` is the whole acknowledgement (a ``RecordUsageResponse``, the
    exact object ``raise_on_stop=False`` would have returned), so nothing is
    lost by catching this; ``event_id``, ``stop_scope``, ``stop_reason`` and
    ``task_id`` read straight off it, and ``idempotency_key`` is the one you
    sent, so a handler can log what happened and reconcile without a second
    request. ``record_batch`` never raises this — it reports the stop per
    item."""
    def __init__(self, result: RecordUsageResponse, *, idempotency_key: str):
        self.result = result
        self.idempotency_key = idempotency_key
        super().__init__(
            f"UBB requested a stop for {self.stop_scope or 'an unnamed scope'}"
            f" ({self.stop_reason or 'spend ceiling reached'}). Event "
            f"{self.event_id} was recorded and charged; do not resend it")

    @property
    def event_id(self) -> str:
        return self.result.event_id

    @property
    def stop_scope(self) -> str | None:
        return self.result.stop_scope

    @property
    def stop_reason(self) -> str | None:
        return self.result.stop_reason

    @property
    def task_id(self) -> str | None:
        return self.result.task_id

class UBBWebhookVerificationError(UBBError):
    """Webhook signature verification failed.

    Raised by ubb.webhooks.verify_webhook / verify_webhook_legacy for a bad
    signature, a timestamp outside the tolerance window, or a malformed
    signature header. Treat the delivery as untrusted and respond non-2xx.
    """
    pass


# The per-code API exception hierarchy is GENERATED from openapi/error-codes.json
# (ubb/codegen/generate_exceptions.py) and committed under the ratchet. Importing
# it here re-exports every status-family parent (ConflictError, …) and per-code
# leaf (InsufficientBalanceError, …) from ``ubb.exceptions``. The import sits at
# the bottom so UBBAPIError is already defined when the generated module (which
# subclasses it) imports back — a benign, resolved circular import.
from ubb._exceptions_generated import *  # noqa: E402,F401,F403
from ubb._exceptions_generated import ConflictError  # noqa: E402

# Backwards-compatible alias: 409 Conflict was ``UBBConflictError`` before the
# registry-derived hierarchy landed; it is now exactly ``ConflictError``.
UBBConflictError = ConflictError
