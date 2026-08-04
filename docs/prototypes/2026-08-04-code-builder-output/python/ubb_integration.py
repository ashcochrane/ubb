# ==============================================================================
# UBB CODE BUILDER  ·  STATUS: COMPLETE — READY TO RUN
#
# Every declaration this integration needs is published and resolves. Nothing
# below is a placeholder.
#
# GENERATED FILE — do not edit. When your UBB configuration changes, regenerate
# from Developers -> Code Builder -> report_generation (Python) and replace this
# file whole. Your own code never lives in here; see CALL-SITES.md for the lines
# that go into your application.
#
#   Generated      2026-08-04T09:41:07Z
#   Tenant         northwind-research  ·  customer billing mode: postpaid
#   Plan           resolved_code_plan schema 1
#   Renderer       ubb-codegen 0.4.2  ·  target: python / ubb-sdk 4.x
#   Resolved from  task kind     report_generation   published 2026-08-01
#                  subtask kind  source_research     published 2026-08-01
#                  event type    anthropic-messages  published 2026-07-30
#                  event type    openai-embeddings   published 2026-08-02
#                  event type    serp-search         published 2026-07-30
#
# ------------------------------------------------------------------------------
# THREE KINDS OF VALUE APPEAR BELOW AND YOU CAN TELL THEM APART BY THEIR SHAPE.
#
# The shape is the whole convention. There is no marker to search for, no token
# to swap, and nothing here depends on the console's formatting surviving a
# copy and paste.
#
#   a literal         "report_generation"        UBB already knows this, because
#                                                you declared it. It changes when
#                                                you republish, not at run time.
#
#   a parameter       customer_id                UBB cannot know this. You supply
#                                                it per run. Forget one and
#                                                Python raises TypeError at the
#                                                call — never a wrong number
#                                                later.
#
#   os.environ[...]   os.environ["UBB_API_KEY"]  A credential. UBB knows this one
#                                                and deliberately refuses to
#                                                write it into a file you can
#                                                copy or commit. See .env.example.
#
# Two of them routinely share one line. That is correct, not a slip:
#
#       "environment": environment
#        |             |
#        |             this run's value, supplied by you
#        the field name you declared to UBB
# ==============================================================================

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterator

from ubb import UBBClient
from ubb.exceptions import UBBStoppedError

__all__ = [
    "ReportGeneration",
    "SourceResearch",
    "UbbOutcomeNotDeclared",
    "report_generation",
    "start_report_generation",
    "start_source_research",
    "record_anthropic_messages",
    "record_openai_embeddings",
    "record_serp_search",
    "usd_to_micros",
]


# ------------------------------------------------------------------------------
# Client
# ------------------------------------------------------------------------------
# Built on first use rather than at import, so this module can be imported in a
# test process that has no credentials.

_client_singleton: UBBClient | None = None


def _client() -> UBBClient:
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = UBBClient(
            # A credential: the name is generated, the value never is.
            api_key=os.environ["UBB_API_KEY"],
            # NOT a credential — a plain default you may point at a sandbox or a
            # proxy. That is why it is emitted as a literal.
            base_url=os.environ.get("UBB_BASE_URL", "https://api.ubb.dev"),
        )
    return _client_singleton


def usd_to_micros(amount: str | Decimal) -> int:
    """Convert a decimal currency amount to exact integer micros (1 USD = 1_000_000).

    Money crosses this API as whole micros, never as a float. Pass a string or a
    Decimal — ``usd_to_micros("0.014")`` — because ``int(0.014 * 1_000_000)`` is
    a floating-point expression and does not reliably give you 14000.
    """
    return int((Decimal(amount) * 1_000_000).to_integral_value())


class UbbOutcomeNotDeclared(RuntimeError):
    """A ``with report_generation(...)`` block ended without declaring how the
    work finished. See the note on the context manager at the foot of this file."""


# ------------------------------------------------------------------------------
# 1. START  ·  once, when the unit of work begins
# ------------------------------------------------------------------------------


@dataclass
class ReportGeneration:
    """A started Task. Keep it: every later call needs it.

    ``task_id`` does not exist until UBB creates it, so it can never appear as a
    literal in a generated file. This object is how it travels from the start
    call to the record and close calls, which normally live somewhere else
    entirely in your application. It is plain data and safe to pass between
    processes.

    Closing lives here rather than in a free function because it is the one call
    that has to know whether an outcome was already declared.
    """

    task_id: str
    customer_id: str
    idempotency_key: str
    outcome_declared: bool = field(default=False, repr=False)

    # -- closing ---------------------------------------------------------------
    # `outcome` is required and has no default. UBB will not guess it, because
    # the forgiving answer and the answer that moves money are the same word.
    #
    # Your Task kind report_generation is `event_priced`, so closing does not
    # itself create a charge — its events were priced as they were recorded. The
    # outcome is still the honest record of how the work ended, it is what your
    # failure rates are computed from, and if this Task kind is ever republished
    # as priced-as-a-whole then `delivered` becomes the outcome that charges.
    # Regenerate this file when that happens.
    #
    # Closing a parent cascades any still-running Subtasks to `cancelled` —
    # never to the parent's outcome, so their own failure rates stay honest.

    def deliver(self) -> Any:
        """The work was delivered."""
        self.outcome_declared = True
        return _client().tasks.close(self.task_id, outcome="delivered")

    def fail(self, *, reason_code: str, reason_detail: str = "") -> Any:
        """The work failed. ``reason_code`` is required and comes from UBB's
        closed list; ``unspecified`` is a member of it, so there is always an
        honest answer available. ``reason_detail`` is free text for display and
        is never grouped on."""
        self.outcome_declared = True
        return _client().tasks.close(
            self.task_id,
            outcome="failed",
            reason_code=reason_code,
            reason_detail=reason_detail,
        )

    def cancel(self, *, reason_code: str = "unspecified") -> Any:
        """The work was abandoned deliberately — by a user, or by you."""
        self.outcome_declared = True
        return _client().tasks.close(
            self.task_id, outcome="cancelled", reason_code=reason_code
        )


def start_report_generation(
    *,
    customer_id: str,
    idempotency_key: str,
    environment: str,
    workspace_id: str,
) -> ReportGeneration:
    """Start one report_generation Task and return a handle to it."""
    started = _client().tasks.start(
        # Declared on your Task kind, published 2026-08-01. Starting under this
        # kind pins, for this run:
        #   pricing mode  event_priced   (events are priced as they are recorded)
        #   COGS ceiling  5.000000 USD
        #   silence       900 s          (no event for this long -> expired)
        #   duration      21600 s        (absolute maximum age -> expired)
        task_type="report_generation",
        customer_id=customer_id,
        # REQUIRED, and it must be YOUR identifier for this unit of work, stable
        # across every retry of the same work.
        #
        # Do not generate one on this line. `uuid4()` here is a new value on
        # every attempt, so a retried start becomes a SECOND Task — and where a
        # Task kind is priced as a whole, a second Task is a second charge.
        #
        # Repeat the same key and UBB returns the same Task (200), including
        # from another process — that is also how a worker re-attaches to a Task
        # a web request started. Repeat it against a different Task kind or
        # customer and UBB refuses (409): the key is claimed permanently.
        idempotency_key=idempotency_key,
        # Grouping Fields your Task kind requires at `task` scope — constant for
        # the whole run, so they are supplied once, here. The keys are names you
        # declared; the values are this run's.
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


# ------------------------------------------------------------------------------
# 2. RECORD  ·  once per provider call, wherever that call happens
# ------------------------------------------------------------------------------
# One function per Event Type you selected. Neither of them calls your provider:
# they take the response you already have. UBB does not own your provider client
# and will not write code against it.
#
# Both accept a Subtask handle in place of the parent handle — see section 3.


def record_anthropic_messages(
    task: ReportGeneration | SourceResearch,
    response: Any,
    *,
    event_key: str,
    stage: str,
) -> Any:
    """Record one anthropic-messages call against ``task``.

    ``response`` is the object your Anthropic client returned.
    ``event_key`` is your identifier for this individual provider call, stable
    across retries of it — the provider's own response identifier is usually the
    natural choice.
    """
    return _client().events.record(
        task_id=task.task_id,
        customer_id=task.customer_id,
        # Declared Event Type, published 2026-07-30. Provider: anthropic.
        event_type="anthropic-messages",
        idempotency_key=event_key,
        # Your Event Type declares costing method `calculated`: you send
        # quantities and UBB prices them against your Cost Rates. There is no
        # field here to send money in, deliberately.
        #
        # Both measurements are declared `required_for_costing`. Omit one and
        # this event records with no cost at all (`costing_status: unresolved`),
        # which is not the same as costing zero: it is COGS you can no longer
        # attribute, and any ceiling standing over it reports `indeterminate`
        # rather than stopping anything.
        #
        # The names are yours. The expressions read the response shape you
        # declared, anthropic.messages.python.v1:
        measurements={
            # int · tokens · declared at usage.input_tokens
            "input_tokens": response.usage.input_tokens,
            # int · tokens · declared at usage.output_tokens
            "output_tokens": response.usage.output_tokens,
        },
        # Grouping Field required at `event` scope, so it is supplied per call
        # rather than at start. Declared values: research · drafting · review.
        grouping_fields={"stage": stage},
        # See the note in record_serp_search. This is the stop signal, and it is
        # the one keyword in this file you must not remove.
        raise_on_stop=True,
    )


def record_openai_embeddings(
    task: ReportGeneration | SourceResearch,
    response: Any,
    *,
    event_key: str,
    stage: str,
) -> Any:
    """Record one openai-embeddings call against ``task``.

    ``response`` is the decoded JSON body your provider returned.
    """
    return _client().events.record(
        task_id=task.task_id,
        customer_id=task.customer_id,
        # Declared Event Type, published 2026-08-02. Provider: openai.
        event_type="openai-embeddings",
        idempotency_key=event_key,
        # This Event Type declares its mapping against the response shape
        # openai.embeddings.rest.v1 — the raw JSON body rather than a client
        # object — so the same declaration renders as subscripts here and as
        # attributes above. That is a difference in access syntax, which the
        # renderer owns. The field NAMES are yours in both cases: UBB never
        # translates one spelling of a provider field into another.
        measurements={
            # int · tokens · declared at usage.prompt_tokens
            "prompt_tokens": response["usage"]["prompt_tokens"],
        },
        grouping_fields={"stage": stage},
        raise_on_stop=True,
    )


def record_serp_search(
    task: ReportGeneration | SourceResearch,
    *,
    event_key: str,
    reported_cost_micros: int,
    stage: str,
) -> Any:
    """Record one serp-search call against ``task``.

    ``reported_cost_micros`` is what this search cost you, in exact micros —
    build it with ``usd_to_micros("0.014")``, never from a float.
    """
    return _client().events.record(
        task_id=task.task_id,
        customer_id=task.customer_id,
        # Declared Event Type, published 2026-07-30. Provider: serpapi.
        event_type="serp-search",
        idempotency_key=event_key,
        # Your Event Type declares costing method `reported`: UBB does not
        # compute this cost, it records the figure you supply AS your COGS.
        #
        # There is no rate on this Event Type to check that figure against, so
        # UBB cannot tell a right number from a wrong one and will not pretend
        # to. A wrong number here is a wrong margin, silently, for as long as it
        # goes unnoticed.
        reported_cost_micros=reported_cost_micros,
        # Quantities still count on a `reported` Event Type. This one is declared
        # `constant`, value 1: it is recorded and you can group and report on it,
        # but it never moves money — here the cost above is the money.
        measurements={"searches": 1},
        grouping_fields={"stage": stage},
        # THE STOP SIGNAL. UBB never refuses an event in order to stop you: the
        # call above returns 200 and the event IS recorded and charged. The
        # instruction to stop rides fields on that successful response, so no
        # amount of ordinary error handling will surface it.
        #
        # `raise_on_stop=True` turns those fields into a UBBStoppedError, which
        # is control flow you cannot forget to read. Catch it once, around the
        # whole unit of work, not here: a stop may be scoped to this Task or to
        # the entire customer, and only the caller knows what to abandon.
        #
        # Delete this keyword and every stop UBB issues is discarded in silence.
        # verify_integration.py exercises exactly this branch — keep it green.
        raise_on_stop=True,
    )


# ------------------------------------------------------------------------------
# 3. SUBTASK  ·  optional, and only where you say so
# ------------------------------------------------------------------------------
# You told the builder that this integration creates source_research Subtasks,
# so they are generated. UBB will never infer a Subtask boundary from event
# timing or from which provider you called: enforcement invented over a
# structure you never asserted is enforcement you cannot predict.
#
# Attaching events straight to the parent Task is a first-class choice, not a
# fallback. That is why the record functions above take either handle.


@dataclass
class SourceResearch:
    """A started source_research Subtask. Pass it to the record functions in
    place of the parent handle to attribute events to this Subtask instead."""

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


def start_source_research(
    parent: ReportGeneration,
    *,
    idempotency_key: str,
) -> SourceResearch:
    """Start a source_research Subtask under ``parent``."""
    started = _client().tasks.start(
        # Declared Subtask kind, published 2026-08-01. Its own COGS ceiling is
        # 2.000000 USD; whatever it spends also rolls up into the parent's
        # 5.000000 USD ceiling, one hop.
        task_type="source_research",
        parent_task_id=parent.task_id,
        customer_id=parent.customer_id,
        # Its own identity, on the same terms as the parent's: your value, stable
        # across retries, claimed permanently.
        idempotency_key=idempotency_key,
        # Task-scoped Grouping Fields are inherited from the parent. Nothing to
        # repeat here.
    )
    return SourceResearch(
        task_id=started.task_id,
        customer_id=parent.customer_id,
        idempotency_key=idempotency_key,
    )


# ------------------------------------------------------------------------------
# 4. THE WHOLE LIFECYCLE IN ONE BLOCK  ·  where the work fits in one place
# ------------------------------------------------------------------------------
# Use this where a unit of work starts and finishes inside one function. Where it
# does not — a Task started in a web request and closed by a worker — call
# start_report_generation() and task.deliver() directly. The handle is plain data
# and the start call is safe to repeat with the same key.
#
# ON EXIT THIS BLOCK INFERS ONLY THE OUTCOME THAT COSTS NOTHING.
#
# An exception closes the Task as `failed`, because failing is never the
# charging answer and inferring it is therefore safe. A clean exit that never
# declared an outcome is NOT closed as delivered: it raises, and the Task is
# left to expire on the ceilings it was started with, which also never charges.
# Generated code does not declare delivery on your behalf.


@contextmanager
def report_generation(
    *,
    customer_id: str,
    idempotency_key: str,
    environment: str,
    workspace_id: str,
) -> Iterator[ReportGeneration]:
    task = start_report_generation(
        customer_id=customer_id,
        idempotency_key=idempotency_key,
        environment=environment,
        workspace_id=workspace_id,
    )
    try:
        yield task
    except UBBStoppedError as stopped:
        # UBB stopped this work. The event carrying the verdict was still
        # recorded and charged; what you do now is stop spending.
        # `stopped.scope` is "task" (this unit only) or "customer" (everything
        # for them) — a customer-wide stop means abandoning other work too, which
        # this block cannot do for you.
        if not task.outcome_declared:
            task.fail(reason_code="spend_ceiling_reached", reason_detail=str(stopped))
        raise
    except Exception as exc:
        if not task.outcome_declared:
            task.fail(reason_code="upstream_provider_error", reason_detail=str(exc))
        raise
    else:
        if not task.outcome_declared:
            raise UbbOutcomeNotDeclared(
                "report_generation finished without declaring an outcome. Call "
                "task.deliver(), task.fail(reason_code=...) or task.cancel() "
                "before the block ends. This Task has been left open and will "
                "expire on its own ceilings; it has NOT been recorded as "
                "delivered."
            )
