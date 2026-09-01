"""Synthetic catalogues, for putting the gate through its real entry point.

Every control here builds a whole small repository on disk — a vocabulary
registry, a payload-schemas module and, where it matters, a migration ledger —
and reads it with :func:`tools.webhook_catalogue.assess`, the same function CI
calls. Nothing patches the reader, the rules or the ledger.

The synthetic registries use the **real** ``schema.yaml`` and ``consumers.yaml``
(via :mod:`_helpers`), so a change to the shipped kind table or to the declared
surfaces is felt immediately by every control rather than passing against a
stale copy of the rules.

The synthetic catalogues are small — three or four events — because the rules
under test are about shape, not about scale. What checks the gate against the
real one is ``test_webhook_catalogue.py``'s shipped-tree section, which asserts
on the tree itself rather than on a copy of it. Its SIZE is deliberately not
stated here: it moved from thirty-five to thirty-seven when the two terminal
Task events became four, and a count in prose that no gate reads is a tally
waiting to go stale.
"""

import yaml

from _helpers import write_registry

#: Where a synthetic catalogue lives. Under the `backend` surface's root, so it
#: resolves as a declared consumer exactly as the real one does.
CATALOGUE_PATH = "ubb-platform/apps/platform/events/schemas.py"

#: The webhook name shape, from the shipped registry. Stated here rather than
#: imported so a control can prove the gate reads the registry's pattern — a
#: synthetic registry that widened it would otherwise be untestable.
NAME_PATTERN = r'^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$'

#: A small end-state catalogue: two resource owners and one control family,
#: covering every branch the rules take. `task.killed` is what makes the Task
#: conjunct reachable at all.
DECLARED_EVENTS = (
    "wallet.balance_low",
    "wallet.credited",
    "task.killed",
    "task.expired",
    "wallet_policy.soft_floor_crossed",
)

DECLARED_STATUSES = ("active", "completed", "killed", "expired")

DECLARED_FAMILIES = ("wallet_policy", "customer_spend_pool")

RETIRED_FAMILIES = ("budget",)

DECLARED_PRODUCTS = ("metering", "billing", "referrals")


def concepts(declared=DECLARED_EVENTS, retired=(), statuses=DECLARED_STATUSES,
             families=DECLARED_FAMILIES, retired_families=RETIRED_FAMILIES,
             products=DECLARED_PRODUCTS, pattern=NAME_PATTERN, omit=()):
    """The three concepts the rules are stated over, as a registry document.

    ``omit`` drops one by name, which is how a control reaches the "the oracle
    cannot answer this" branch rather than asserting it from the inside.
    """
    document = {
        "webhook_event_type": {
            "kind": "closed",
            "summary": "Every event this synthetic platform publishes.",
            "token_pattern": pattern,
            "values": list(declared),
            "label_key_prefix": "webhook_event_type",
            "consumers": [{"surface": "backend", "path": CATALOGUE_PATH}],
        },
        "task_status": {
            "kind": "closed",
            "summary": "The durable state a Task is in.",
            "values": list(statuses),
            "label_key_prefix": "task_status",
            "consumers": [],
        },
        "control_family": {
            "kind": "closed",
            "summary": "Which spend control a signal came from.",
            "values": list(families),
            "label_key_prefix": "control_family",
            "consumers": [],
        },
        "tenant_product": {
            "kind": "closed",
            "summary": "The products a tenant has enabled.",
            "values": list(products),
            "label_key_prefix": "tenant_product",
            "consumers": [],
        },
    }
    if retired:
        document["webhook_event_type"]["retired_aliases"] = list(retired)
    if retired_families:
        document["control_family"]["retired_aliases"] = list(retired_families)
    for name in omit:
        document.pop(name, None)
    return document


def catalogue_module(*events, extra=""):
    """A payload-schemas module declaring exactly ``events``.

    Each event is a name, or a ``(class name, EVENT_TYPE source)`` pair. Passing
    source rather than a string is what lets a control express the cases that
    are *about* how the name was written — a computed value, a non-string.
    """
    lines = ['"""A synthetic payload-schema registry."""', "", ""]
    for index, event in enumerate(events):
        if isinstance(event, tuple):
            class_name, expression = event
        else:
            class_name, expression = _class_name(event), repr(event)
        lines += [
            f"class {class_name}:",
            f'    """The payload for {class_name}."""',
            f"    EVENT_TYPE = {expression}",
            "",
            "",
        ]
    return "\n".join(lines) + extra


def write_repository(tmp_path, *, events=DECLARED_EVENTS, ledger=None,
                     **registry_options):
    """Write a whole synthetic repository under ``tmp_path``; return the root.

    The registry is written first and the catalogue file second, deliberately in
    that order: :func:`_helpers.write_registry` creates the declared consumer
    path as a placeholder so the registry compiles, and this overwrites it with
    the module the control is actually about.
    """
    write_registry(tmp_path, concepts={"synthetic.yaml":
                                       concepts(**registry_options)},
                   consumer_files=(CATALOGUE_PATH,))

    target = tmp_path / CATALOGUE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        events if isinstance(events, str) else catalogue_module(*events),
        encoding="utf-8")

    if ledger is not None:
        (tmp_path / "gates").mkdir(parents=True, exist_ok=True)
        (tmp_path / "gates" / "migration-ledger.yaml").write_text(
            ledger if isinstance(ledger, str)
            else yaml.safe_dump(ledger, sort_keys=False),
            encoding="utf-8")

    return tmp_path


def excusing(*entries, expected="wallet.balance_low"):
    """A migration ledger excusing exactly ``(class name, event name)`` under G8."""
    return {
        "version": 1,
        "entries": [
            {"id": f"g8-synthetic-{index}", "gate": "G8",
             "site": f"{CATALOGUE_PATH}::{site}", "expected": expected,
             "found": found, "owner_slice": "slice_8",
             "reason": "a synthetic debt."}
            for index, (site, found) in enumerate(entries)
        ],
    }


def _class_name(event):
    return "".join(part.title() for part in event.replace(".", "_").split("_"))
