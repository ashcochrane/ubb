"""Shared setup for the events app's tests (`docs/conventions/testing.md`).

Two doors the webhook-rename modules share rather than copy:

- :func:`stub_webhook_client` — the patched `httpx.Client` answering 200 to
  any POST, so a case can drive the real fan-out (`deliver_webhook`) and
  assert on the delivery attempts it records.
- :func:`as_it_was_spelled` — the name a row carried for one of today's event
  constants BEFORE `events/0009` moved the five control events under their
  families (#464). A frozen migration keeps the spelling it ran with, so a
  test planting a row for one — or holding its map to the constants — reads
  the old spelling off `0009`'s own reverse rather than spelling a retired
  word, which no living file may do. The billing suite carries its own copy
  of this three-line reader: a product test importing a kernel TEST helper
  is the boundary `gating/tests/test_patrol_pins.py` names.
"""
import importlib
from unittest.mock import MagicMock

THE_CATALOGUE_RENAME = importlib.import_module(
    "apps.platform.events.migrations."
    "0009_five_control_events_move_under_their_families")


def as_it_was_spelled(current):
    """The pre-`0009` spelling of today's event constant ``current`` — the
    constant itself where `0009` renamed nothing to it."""
    return THE_CATALOGUE_RENAME.REVERSE.get(current, current)


def stub_webhook_client(mock_client_class):
    """Wire the patched `httpx.Client` to answer 200 to any POST."""
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.post.return_value = MagicMock(status_code=200, text="OK")
    mock_client_class.return_value = client
    return client
