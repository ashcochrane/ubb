# ==============================================================================
# UBB CODE BUILDER  ·  STATUS: INCOMPLETE — NOT READY TO RUN
#
# The shape of this integration is known, but two declarations do not yet
# resolve. Run this file and it stops at the first one with a message naming it.
# It will not send a wrong number anywhere.
#
# MISSING CONFIGURATION
#
#   1. Event Type "anthropic-messages" · Measurement "output_tokens"
#      Declared source_kind is `provider_response` but no source_path is set, so
#      UBB cannot say where in your provider's response this quantity lives.
#      Fix: Catalogue -> Event Types -> anthropic-messages -> output_tokens
#
#   2. Subtask kind "source_research"
#      Draft, never published. Code that starts a draft Subtask kind would be
#      refused at run time, so none is generated.
#      Fix: Catalogue -> Task Kinds -> source_research -> Publish
#
# Both need a tenant admin. Use "Copy configuration request" on the builder page
# to send this list to one, then regenerate.
#
# WARNINGS (this code is generated, and it may still be wrong)
#
#   ! Event Type "anthropic-messages" · Measurement "input_tokens"
#     You declared the path usage.prompt_tokens under response shape
#     anthropic.messages.python.v1. UBB's tested copy of that shape has
#     usage.input_tokens and no usage.prompt_tokens.
#     Your declaration is authoritative and has been generated as you wrote it.
#     If UBB is right, this integration reports the wrong quantity and your COGS
#     will be wrong with nothing to flag it.
#
#   Generated      2026-08-04T09:12:55Z
#   Tenant         northwind-research  ·  customer billing mode: postpaid
#   Plan           resolved_code_plan schema 1
#   Renderer       ubb-codegen 0.4.2  ·  target: python / ubb-sdk 4.x
#   Resolved from  task kind   report_generation   published 2026-08-01
#                  event type  anthropic-messages  published 2026-07-30
# ==============================================================================

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from ubb import UBBClient


def required_configuration(what: str, where: str) -> Any:
    """Stop here, and say exactly what is missing.

    This function exists because your generated code is incomplete. It is not a
    placeholder you edit: configure the thing it names, regenerate, and it will
    be gone.
    """
    raise RuntimeError(
        f"UBB Code Builder output is incomplete: {what}. Configure it at {where}, "
        f"then regenerate this file."
    )


_client_singleton: UBBClient | None = None


def _client() -> UBBClient:
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = UBBClient(
            api_key=os.environ["UBB_API_KEY"],
            base_url=os.environ.get("UBB_BASE_URL", "https://api.ubb.dev"),
        )
    return _client_singleton


@dataclass
class ReportGeneration:
    task_id: str
    customer_id: str
    idempotency_key: str
    outcome_declared: bool = field(default=False, repr=False)

    def deliver(self) -> Any:
        self.outcome_declared = True
        return _client().tasks.close(self.task_id, outcome="delivered")

    def fail(self, *, reason_code: str, reason_detail: str = "") -> Any:
        self.outcome_declared = True
        return _client().tasks.close(
            self.task_id,
            outcome="failed",
            reason_code=reason_code,
            reason_detail=reason_detail,
        )


def start_report_generation(
    *,
    customer_id: str,
    idempotency_key: str,
    environment: str,
    workspace_id: str,
) -> ReportGeneration:
    """Start one report_generation Task. This part is complete."""
    started = _client().tasks.start(
        task_type="report_generation",
        customer_id=customer_id,
        idempotency_key=idempotency_key,
        grouping_fields={
            "environment": environment,
            "workspace_id": workspace_id,
        },
    )
    return ReportGeneration(
        task_id=started.task_id,
        customer_id=customer_id,
        idempotency_key=idempotency_key,
    )


def record_anthropic_messages(
    task: ReportGeneration,
    response: Any,
    *,
    event_key: str,
    stage: str,
) -> Any:
    """Record one anthropic-messages call. INCOMPLETE — see item 1 in the header."""
    return _client().events.record(
        task_id=task.task_id,
        customer_id=task.customer_id,
        event_type="anthropic-messages",
        idempotency_key=event_key,
        measurements={
            # Declared at usage.prompt_tokens. See the WARNING in the header:
            # UBB's tested copy of this response shape does not have that field.
            "input_tokens": response.usage.prompt_tokens,
            # No source_path is declared for this Measurement, and it is required
            # for costing. UBB will not guess a field name for you: guessing here
            # produces code that runs, reports a plausible number, and is wrong.
            "output_tokens": required_configuration(
                'Measurement "output_tokens" on Event Type "anthropic-messages" '
                "has no source_path",
                "Catalogue -> Event Types -> anthropic-messages -> output_tokens",
            ),
        },
        grouping_fields={"stage": stage},
        raise_on_stop=True,
    )


# No source_research functions are generated: that Subtask kind is still a draft.
# See item 2 in the header.
