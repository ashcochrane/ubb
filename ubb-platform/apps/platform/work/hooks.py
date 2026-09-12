"""Terminal-transition listeners: the kernel tells whichever products asked
that a unit of work has reached a terminal state, and none of them can veto
it (slice 6 §5, #460 — the platform-hooks channel of ADR-001 rule 3, the
fourth in `CLAUDE.md`'s list, on the seat-roster registry's shape in
`apps/platform/customers/hooks.py`).

WHY A REGISTRY, AND NOT AN IMPORT OR AN OUTBOX EVENT. Every terminal
transition — a close, a kill, an expiry, and the three cascades — is a kernel
state change, and the kernel may not import a product (ADR-001 rule 2). The
product that needs to hear it — billing, releasing the wallet reservation a
unit's start encumbered — needs to hear it IN THE SAME TRANSACTION, or a
crashed process leaves a unit terminal with money still held; the outbox is
asynchronous by default and cannot promise that. So: a product registers a
listener in its `AppConfig.ready()`, the kernel calls every listener
synchronously at the mutation site, and no products installed means no
listeners means a no-op. Listeners are called in registration order, and
registration is idempotent because `ready()` can run more than once.

A LISTENER IS A NOTIFICATION AND NEVER A VETO (#141 §6.4). The row is
already written when a listener is called, and nothing a listener does can
un-write it: the transition is the kernel's fact, and a product's reaction
to it is the product's own concern.

⚠ WHAT THE ROW CARRIES AT THAT MOMENT is the state, the cause and the
control — not yet the announcement. The listeners run inside the flip,
and the announcing lanes stamp the outbox id and the mechanism
(`STOP_MECHANISM_KEY`) on the row AFTER the flip returns; a cascaded piece
carries its mechanism already, because the cascade writes it in the same
UPDATE as the state. So a listener reads the transition off the
`TerminalTransition` it is handed and the row's own columns, and never
the mechanism or the announcement, which are not there yet.

⚠ WHAT HAPPENS WHEN A LISTENER RAISES — A DELIBERATE DEPARTURE FROM THE
ROSTER REGISTRY. The roster registry lets an exception propagate, and that
is safe there only because its one listener defers its real work to
`transaction.on_commit` and so never raises at the call site. A listener
here does its work INSIDE the caller's transaction — that is the whole reason
this channel exists — so an exception propagating out of it would roll the
terminal transition back with it: the unit would stay active, the
announcement would never be written, and a product's bug would have vetoed
a kernel fact. So every listener runs under its own savepoint, and an
exception is CAUGHT and logged loudly (`work.terminal_listener_failed`)
rather than re-raised. The savepoint is what makes the catch sound: a
database error inside a listener poisons the enclosing transaction unless
it is rolled back to one, and a listener that raised after writing half of
what it meant to write must not leave that half behind. The next listener
still runs. What the failed listener owed is left undone, on purpose — the
product that owed it owns the backstop (for the reservation, a sweep over
terminal work still holding one), which is a cheaper and more honest repair
than a kernel that refuses to finish because a product could not.

Nothing in this module reads or writes a row of its own.
"""
import logging
from dataclasses import dataclass

from django.db import transaction

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TerminalTransition:
    """What a listener is told beside the row: the terminal state entered,
    what was recorded about why, and whether containment wrote it.

    The row carries all of this too, split between a column and a metadata
    bag; it travels here as one object so a listener acts on what the
    transition SAID rather than on what it can dig out of the row it was
    handed, and so the shape a listener depends on is this dataclass and not
    the row's storage layout.
    """

    #: The terminal state the unit entered (one of `TERMINAL_TASK_STATUSES`).
    status: str
    #: The CALLER-declared reason — a close's closed-set word, or the
    #: `parent_closed` a close's cascade writes. Empty where nobody declared
    #: one.
    outcome_reason: str = ""
    #: UBB's own stop cause (`work.reasons`) — a ceiling, a window, a parent's
    #: end. Empty for a close, and for the crash sweeper's unannounced expiry,
    #: which names no window.
    stop_reason: str = ""
    #: True where containment wrote this transition — the parent's end
    #: reaching the work still running inside it — rather than anything the
    #: unit did or anything declared about it.
    cascaded: bool = False


_listeners = []


def register_terminal_transition_listener(fn):
    """Register ``fn(task, transition)`` to run on every terminal transition.
    Idempotent (AppConfig.ready() can run more than once)."""
    if fn not in _listeners:
        _listeners.append(fn)


def notify_terminal_transition(task, transition):
    """Invoke every registered listener synchronously, in registration order,
    with the row as the flip left it and the `TerminalTransition` it made.

    Called inside the flip's transaction, after the row is written: each
    listener runs under a savepoint of that transaction, and one that raises
    is logged and skipped — see the module docstring for why that is the
    handling and why the savepoint is what makes it sound.
    """
    for fn in _listeners:
        try:
            with transaction.atomic():
                fn(task, transition)
        except Exception:
            logger.exception("work.terminal_listener_failed", extra={"data": {
                "task_id": str(task.id), "status": transition.status,
                "listener": getattr(fn, "__qualname__", repr(fn))}})
