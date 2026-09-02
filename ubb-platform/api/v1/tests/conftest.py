"""Fixtures shared by the live-server tests in this package.

A live-server test drives the real `ubb` SDK over HTTP against a running
Django server, because a mocked-httpx unit test lets a wire-level mismatch
ship undetected. The one thing every such test needs neutralised is the same,
so it lives here rather than in the module that first needed it
(`docs/conventions/testing.md`: shared setup helpers sit beside the tests
that use them).
"""
import pytest


@pytest.fixture
def _no_outbox_dispatch():
    """Neutralize the transactional-outbox Celery dispatch for this test.

    record_usage — and, since #410, starting or closing a unit of work — writes
    an OutboxEvent and fires
    ``transaction.on_commit(lambda: process_single_event.delay(...))`` (see
    apps/platform/events/outbox.py). Under live_server there is no Celery
    worker / broker, so that ``.delay()`` tries to publish to the real AMQP
    broker and raises ``kombu.exceptions.OperationalError`` (ConnectionRefused)
    on the commit hook -> the request returns HTTP 500.

    Flipping the global ``app.conf.task_always_eager`` is unreliable across the
    full suite: earlier tests mutate that global Celery state, and the on-commit
    hook runs on the live_server thread, so the flag is not guaranteed to be in
    effect at dispatch time. Patching the dispatch symbol to a no-op removes the
    broker dependency entirely and is deterministic regardless of global state.
    Because live_server runs in this same process, the patch applies to the
    server thread too.

    This does NOT weaken a test: the HTTP response (routing, the state written,
    and the SDK response contract) is computed synchronously before commit;
    only the fire-and-forget async fan-out is suppressed.
    """
    from unittest.mock import patch

    with patch("apps.platform.events.tasks.process_single_event.delay"):
        yield
