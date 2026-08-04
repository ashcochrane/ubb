# ==============================================================================
# UBB CODE BUILDER  ·  VERIFICATION
#
# Generated alongside ubb_integration.py. Run it once when you wire the
# integration up, and keep it: it is a test, not a demo, and it is the only
# thing that can catch the two mistakes UBB cannot catch for you.
#
#   python verify_integration.py anthropic-messages captured_response.json
#   python verify_integration.py openai-embeddings  captured_response.json
#
# WHAT THIS PROVES THAT THE CONSOLE CANNOT
#
#   Your Event Type declares WHERE in your provider's response each quantity
#   lives. UBB never sees that response, so it cannot check the declaration —
#   a path that points at the wrong field satisfies every check UBB has and
#   reports the wrong COGS forever.
#
#   This script closes that hole by reading a REAL captured response from your
#   provider and asserting the declared paths resolve in it. Capture one, keep
#   it beside this file, and re-run when you change providers or SDK versions.
#
# WHAT THE CONSOLE PROVES INSTEAD
#
#   That the event landed, and what UBB made of it — cost, statuses, ceiling.
#   Use Developers -> Code Builder -> Verify for that. The two halves are
#   different questions and you want both.
#
# SANDBOX ONLY. This script starts real Tasks and drives one past its ceiling on
# purpose. It refuses to run against a live key.
# ==============================================================================

from __future__ import annotations

import json
import os
import sys
import uuid

from ubb.exceptions import UBBStoppedError

import ubb_integration as integration

# The customer, environment and workspace this script exercises. Sandbox values:
# nothing here is billed to anyone real.
CUSTOMER_ID = os.environ.get("UBB_VERIFY_CUSTOMER_ID", "verify-customer")
ENVIRONMENT = "dev"
WORKSPACE_ID = "verify"

# Every Measurement you declared with source_kind `provider_response`, and the
# path you declared it at. Generated from your published configuration.
#
# serp-search does not appear: its cost is supplied by you and its one
# measurement is a declared constant, so there is no provider response to check.
DECLARED_PATHS = {
    # response shape anthropic.messages.python.v1
    "anthropic-messages": {
        "input_tokens": ["usage", "input_tokens"],
        "output_tokens": ["usage", "output_tokens"],
    },
    # response shape openai.embeddings.rest.v1
    "openai-embeddings": {
        "prompt_tokens": ["usage", "prompt_tokens"],
    },
}

RECORD = {
    "anthropic-messages": integration.record_anthropic_messages,
    "openai-embeddings": integration.record_openai_embeddings,
}

# What this file was generated from. If these no longer match your published
# configuration, this file and ubb_integration.py are stale — regenerate both.
GENERATED_FROM = {
    "report_generation": "2026-08-01",
    "anthropic-messages": "2026-07-30",
    "openai-embeddings": "2026-08-02",
    "serp-search": "2026-07-30",
}

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"  ok    {message}")
    else:
        print(f"  FAIL  {message}")
        failures.append(message)


def resolve(document: dict, segments: list[str]):
    """Walk a declared source_path over a captured response."""
    cursor = document
    for segment in segments:
        if not isinstance(cursor, dict) or segment not in cursor:
            return None
        cursor = cursor[segment]
    return cursor


def require_sandbox_key() -> None:
    key = os.environ.get("UBB_API_KEY", "")
    if not key.startswith("ubb_test_"):
        sys.exit(
            "verify_integration.py refuses to run without a sandbox key. It "
            "starts real Tasks and deliberately drives one past its spend "
            "ceiling. Set UBB_API_KEY to a ubb_test_ key and re-run."
        )


# ------------------------------------------------------------------------------
# 1. The declared mapping resolves in a real provider response
# ------------------------------------------------------------------------------


def verify_mapping(event_type: str, captured_path: str) -> None:
    print(f"\n1. Declared measurement paths for {event_type}, against your captured response")
    with open(captured_path, encoding="utf-8") as handle:
        captured = json.load(handle)
    declared = DECLARED_PATHS[event_type]

    for measurement, segments in declared.items():
        dotted = ".".join(segments)
        value = resolve(captured, segments)
        check(
            value is not None,
            f'"{measurement}" resolves at {dotted}',
        )
        if value is not None:
            check(
                isinstance(value, int) and not isinstance(value, bool),
                f'"{measurement}" is a whole number ({value!r}) as declared',
            )
            check(
                value > 0,
                f'"{measurement}" is greater than zero — a constant zero here is '
                f"the signature of a path pointing at the wrong field",
            )

    # The check UBB cannot make for you, made explicit: two measurements reading
    # the same number almost always means one path is wrong.
    resolved = [resolve(captured, s) for s in declared.values()]
    present = [v for v in resolved if v is not None]
    check(
        len(set(present)) == len(present),
        "each measurement reads a different field of the response",
    )


# ------------------------------------------------------------------------------
# 2. The lifecycle runs, and UBB understood what it was sent
# ------------------------------------------------------------------------------


class _CapturedResponse:
    """Wraps the captured JSON so the generated code can read it exactly as it
    reads your provider's real response object."""

    def __init__(self, document: dict) -> None:
        for key, value in document.items():
            setattr(self, key, _CapturedResponse(value) if isinstance(value, dict) else value)


# The declared response shape decides what the generated record function expects:
# a client object it reads with attributes, or a decoded JSON body it reads with
# subscripts. Same declaration, two access syntaxes — see ubb_integration.py.
SHAPE_IS_CLIENT_OBJECT = {
    "anthropic-messages": True,   # anthropic.messages.python.v1
    "openai-embeddings": False,   # openai.embeddings.rest.v1
}


def verify_lifecycle(event_type: str, captured_path: str) -> None:
    print("\n2. Start, record and close, against the sandbox")
    with open(captured_path, encoding="utf-8") as handle:
        document = json.load(handle)
    response = (
        _CapturedResponse(document) if SHAPE_IS_CLIENT_OBJECT[event_type] else document
    )

    run_key = f"verify-{uuid.uuid4()}"
    task = integration.start_report_generation(
        customer_id=CUSTOMER_ID,
        idempotency_key=run_key,
        environment=ENVIRONMENT,
        workspace_id=WORKSPACE_ID,
    )
    check(bool(task.task_id), "the Task started and returned an id")

    # Repeating a start with the same key must return the same Task, not a
    # second one. If this fails, every retry in your application is creating
    # duplicate work.
    again = integration.start_report_generation(
        customer_id=CUSTOMER_ID,
        idempotency_key=run_key,
        environment=ENVIRONMENT,
        workspace_id=WORKSPACE_ID,
    )
    check(again.task_id == task.task_id, "repeating the start returns the same Task")

    ack = RECORD[event_type](
        task,
        response,
        event_key=f"{run_key}-1",
        stage="research",
    )

    check(
        ack.costing_status == "resolved",
        f"UBB costed the event (costing_status={ack.costing_status!r}) — "
        f"`unresolved` means a required measurement did not arrive under its "
        f"declared name",
    )
    check(
        sorted(ack.measurements_received) == sorted(DECLARED_PATHS[event_type]),
        f"UBB received exactly the declared measurements "
        f"({sorted(ack.measurements_received)})",
    )
    check(
        ack.grouping_fields_received.get("environment") == ENVIRONMENT,
        "task-scoped Grouping Fields were attached to the Task",
    )
    check(
        ack.grouping_fields_received.get("stage") == "research",
        "event-scoped Grouping Fields were attached to the event",
    )
    check(
        ack.ceiling.status == "within_ceiling",
        f"the COGS ceiling reads {ack.ceiling.status!r} — `indeterminate` means "
        f"UBB cannot fully cost this Task and will not enforce the ceiling",
    )

    closed = task.deliver()
    check(closed.outcome == "delivered", "the Task closed with the outcome it was given")


# ------------------------------------------------------------------------------
# 3. The stop signal actually reaches your code
# ------------------------------------------------------------------------------
# This is the branch that is easiest to break and hardest to notice: a stop rides
# a 200 response, so removing `raise_on_stop=True` from ubb_integration.py loses
# every stop UBB issues without failing anything. This test fails if that happens.


def verify_stop_branch() -> None:
    print("\n3. The stop signal")
    run_key = f"verify-stop-{uuid.uuid4()}"
    task = integration.start_report_generation(
        customer_id=CUSTOMER_ID,
        idempotency_key=run_key,
        environment=ENVIRONMENT,
        workspace_id=WORKSPACE_ID,
    )

    stopped = False
    # The sandbox Task carries the same 5.000000 USD ceiling as production. Each
    # of these deliberately reports a cost above it.
    for index in range(3):
        try:
            integration.record_serp_search(
                task,
                event_key=f"{run_key}-{index}",
                reported_cost_micros=integration.usd_to_micros("4.00"),
                stage="research",
            )
        except UBBStoppedError as verdict:
            stopped = True
            check(True, f"a stop reached your code (scope={verdict.scope!r})")
            check(
                verdict.scope in ("task", "customer"),
                "the stop names a scope, so you know what to abandon",
            )
            break

    check(stopped, "spending past the ceiling raised UBBStoppedError")
    if not stopped:
        print(
            "        Check that record_serp_search still passes raise_on_stop=True.\n"
            "        Without it the ack still carries the verdict and your code "
            "ignores it."
        )

    task.fail(reason_code="spend_ceiling_reached", reason_detail="verification run")


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in DECLARED_PATHS:
        sys.exit(
            "usage: python verify_integration.py <event-type> <captured-response.json>\n"
            f"  event types with a provider-response mapping: "
            f"{', '.join(DECLARED_PATHS)}\n"
            "Capture one real response from that provider and save it as JSON."
        )
    event_type, captured_path = sys.argv[1], sys.argv[2]
    require_sandbox_key()
    print(
        "Verifying the generated integration for report_generation.\n"
        "Generated from: "
        + ", ".join(f"{k} @ {v}" for k, v in GENERATED_FROM.items())
    )
    verify_mapping(event_type, captured_path)
    verify_lifecycle(event_type, captured_path)
    verify_stop_branch()

    print()
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
