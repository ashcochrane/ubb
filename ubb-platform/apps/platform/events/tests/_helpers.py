"""Shared setup for the events app's tests (`docs/conventions/testing.md`).

- :func:`retired_event_names` — every webhook event name the vocabulary
  registry retires, read off the registry itself
  (`domain-vocabulary/concepts/webhooks.yaml`, `webhook_event_type`'s
  `retired_aliases`). A test that needs a retired name — to prove it is not
  published, or that a subscription naming one is refused — reads it here
  rather than spelling it, which no living file may do; the registry is the
  one copy the forbidden-term sweep reads too.

Before the cutover (#190) this module read the old spellings off
`events/0009`'s own reverse map, and carried the patched-client door the
rename modules shared; both left with the migrations they served.
"""
from pathlib import Path

#: The registry file declaring the webhook event names. Five parents up:
#: tests -> events -> platform -> apps -> ubb-platform -> the root.
WEBHOOK_REGISTRY = (Path(__file__).resolve().parents[5]
                    / "domain-vocabulary" / "concepts" / "webhooks.yaml")


def retired_event_names():
    """`webhook_event_type`'s retired aliases, in the registry's order.

    Line-walked rather than parsed: the platform's lock carries no YAML
    parser. Comment lines between the entries are skipped; the walk ends at
    the concept's next key.
    """
    lines = WEBHOOK_REGISTRY.read_text(encoding="utf-8").splitlines()
    at = lines.index("  retired_aliases:", lines.index("webhook_event_type:")) + 1
    names = []
    while at < len(lines) and lines[at].startswith("    "):
        entry = lines[at].strip()
        if entry.startswith("- "):
            names.append(entry.removeprefix("- ").strip())
        at += 1
    assert names, f"no retired alias was read from {WEBHOOK_REGISTRY}"
    return tuple(names)
