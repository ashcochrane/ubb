#!/usr/bin/env bash
# ==============================================================================
# UBB CODE BUILDER  ·  STATUS: INCOMPLETE — PART OF THIS FILE WILL NOT RUN
#
# Two of your three Event Types generated completely. One did not, because its
# provider-response mapping is declared against a shape this target cannot read.
#
# MISSING CONFIGURATION
#
#   1. Event Type "anthropic-messages" — no mapping for the raw HTTP target
#      Its measurements are declared against response shape
#      anthropic.messages.python.v1, which is the shape of a Python SDK OBJECT.
#      This target only ever sees JSON, and the two use different field names
#      for the same numbers.
#
#      UBB will not translate between them: renaming a provider field is a guess
#      about your provider, and a wrong guess here reports a wrong quantity that
#      nothing downstream can detect.
#
#      Fix: add a mapping against a JSON response shape (for example
#      anthropic.messages.rest.v1) at
#      Catalogue -> Event Types -> anthropic-messages -> Response mapping.
#      Or generate the Python target instead, where the existing mapping is
#      complete.
#
# Everything else below is complete and ready to run.
#
#   Generated      2026-08-04T09:41:07Z
#   Tenant         northwind-research  ·  customer billing mode: postpaid
#   Plan           resolved_code_plan schema 1
#   Renderer       ubb-codegen 0.4.2  ·  target: http / curl
#   Resolved from  task kind     report_generation   published 2026-08-01
#                  subtask kind  source_research     published 2026-08-01
#                  event type    anthropic-messages  published 2026-07-30  BLOCKED
#                  event type    openai-embeddings   published 2026-08-02
#                  event type    serp-search         published 2026-07-30
#
#   Requires curl and jq.  Source it:  . ./ubb_integration.sh
#
# ------------------------------------------------------------------------------
# THREE KINDS OF VALUE APPEAR BELOW AND YOU CAN TELL THEM APART BY THEIR SHAPE.
#
#   a literal          "report_generation"     UBB already knows this, because
#                                              you declared it.
#
#   ${NAME:?...}       ${UBB_CUSTOMER_ID:?...} UBB cannot know this. You supply
#                                              it. Leave it unset and the shell
#                                              stops with the message shown —
#                                              never an empty string in a
#                                              request body.
#
#   ${UBB_API_KEY:?}   the credential          UBB knows this one and refuses to
#                                              write it into a file you can copy
#                                              or commit. See .env.example.
#
# The Python target uses required function parameters for the middle class. This
# is the same idea in a language that has no parameters: whatever construct the
# target has for "you must supply this, and I will not proceed without it".
# ==============================================================================

# NOT a credential — the API host, a plain default you may override.
UBB_BASE_URL="${UBB_BASE_URL:-https://api.ubb.dev}"

_ubb_auth() {
  printf 'Authorization: Bearer %s' \
    "${UBB_API_KEY:?Set UBB_API_KEY. Developers -> API Keys.}"
}

ubb_required_configuration() {
  printf 'UBB Code Builder output is incomplete: %s\n' "$1" >&2
  printf 'Configure it at %s, then regenerate this file.\n' "$2" >&2
  return 78
}

# ------------------------------------------------------------------------------
# 1. START  ·  once, when the unit of work begins
# ------------------------------------------------------------------------------
# Echoes the new task id. Capture it — every later call needs it, and it does
# not exist until this call returns, so it can never be a literal in this file.
#
#   TASK_ID="$(ubb_start_report_generation)"

ubb_start_report_generation() {
  curl -sS -X POST "$UBB_BASE_URL/api/v1/tasks" \
    -H "$(_ubb_auth)" \
    -H 'Content-Type: application/json' \
    -d "$(
      jq -n \
        --arg customer_id "${UBB_CUSTOMER_ID:?Set UBB_CUSTOMER_ID to the customer this work is for.}" \
        --arg idempotency_key "${UBB_IDEMPOTENCY_KEY:?Set UBB_IDEMPOTENCY_KEY to YOUR stable identifier for this unit of work. Do not generate a fresh one per attempt: a retried start with a new key is a SECOND Task.}" \
        --arg environment "${UBB_ENVIRONMENT:?Set UBB_ENVIRONMENT. Grouping Field required by report_generation at task scope.}" \
        --arg workspace_id "${UBB_WORKSPACE_ID:?Set UBB_WORKSPACE_ID. Grouping Field required by report_generation at task scope.}" \
        '{
           # Declared on your Task kind, published 2026-08-01. Starting under
           # this kind pins, for this run: pricing mode event_priced, COGS
           # ceiling 5.000000 USD, silence 900s, duration 21600s.
           task_type: "report_generation",
           customer_id: $customer_id,
           idempotency_key: $idempotency_key,
           # Grouping Fields required at task scope: supplied once, here. The
           # keys are names you declared; the values come from this run.
           grouping_fields: {
             environment: $environment,
             workspace_id: $workspace_id
           }
         }'
    )" | jq -r '.task_id'
}

# ------------------------------------------------------------------------------
# 2. RECORD  ·  once per provider call
# ------------------------------------------------------------------------------
# READ THIS BEFORE YOU EDIT ANY OF THESE FUNCTIONS.
#
# UBB never refuses an event in order to stop you. These calls return 200 and the
# event IS recorded and charged. The instruction to stop rides FIELDS on that
# successful response, so checking the HTTP status tells you nothing about it.
#
# That is why each function inspects `.stop.requested` on a response it already
# knows succeeded, and returns 3 when a stop is present. Handle that return code
# — see CALL-SITES.md — and do not replace it with a check on curl's exit status
# or on the HTTP code.
#
# The Python target gets this for free by raising an exception. Shell has no
# equivalent, so it is spelled out. This is the one place where the two targets
# genuinely differ in shape rather than in syntax.

_ubb_handle_ack() {
  local ack="$1"
  if [ "$(printf '%s' "$ack" | jq -r '.stop.requested')" = "true" ]; then
    printf 'UBB stop: scope=%s reason=%s\n' \
      "$(printf '%s' "$ack" | jq -r '.stop.scope')" \
      "$(printf '%s' "$ack" | jq -r '.stop.reason_code')" >&2
    return 3
  fi
  printf '%s' "$ack"
}

# ---- anthropic-messages · BLOCKED -------------------------------------------
# Generated as a stub on purpose. Your measurements for this Event Type are
# declared against a Python SDK response shape and this target reads JSON; UBB
# will not guess the JSON field names. See item 1 in the header.
#
# The rest of this function — the Task attribution, the idempotency key, the
# Grouping Field — is known and would generate fine. It is withheld because
# emitting a call that is right about everything except the numbers is worse
# than emitting nothing.

ubb_record_anthropic_messages() {
  ubb_required_configuration \
    'Event Type "anthropic-messages" has no provider-response mapping for the raw HTTP target' \
    'Catalogue -> Event Types -> anthropic-messages -> Response mapping'
}

# ---- openai-embeddings · complete -------------------------------------------
# Usage: ubb_record_openai_embeddings <task-id> <event-key> <stage> <response.json>
#
# The last argument is the response body your provider returned, as JSON.
# Nothing generated here calls your provider: UBB does not own your provider
# client and will not write code against it.

ubb_record_openai_embeddings() {
  local task_id="${1:?task id}" event_key="${2:?event key}" stage="${3:?stage}" response_file="${4:?provider response JSON}"
  local ack
  ack="$(
    curl -sS -X POST "$UBB_BASE_URL/api/v1/metering/usage" \
      -H "$(_ubb_auth)" \
      -H 'Content-Type: application/json' \
      -d "$(
        jq -n \
          --arg task_id "$task_id" \
          --arg customer_id "${UBB_CUSTOMER_ID:?Set UBB_CUSTOMER_ID.}" \
          --arg event_key "$event_key" \
          --arg stage "$stage" \
          --slurpfile response "$response_file" \
          '{
             task_id: $task_id,
             customer_id: $customer_id,
             # Declared Event Type, published 2026-08-02. Provider: openai.
             event_type: "openai-embeddings",
             idempotency_key: $event_key,
             # Costing method `calculated`: you send quantities, UBB prices them
             # against your Cost Rates. There is no field to send money in.
             #
             # Declared required_for_costing. Omit it and the event records with
             # NO cost (costing_status: unresolved) — which is not costing zero,
             # and leaves any ceiling over it reading `indeterminate` instead of
             # stopping anything.
             #
             # The name is yours. The path is the response shape you declared,
             # openai.embeddings.rest.v1:
             measurements: {
               # int · tokens · declared at usage.prompt_tokens
               prompt_tokens: $response[0].usage.prompt_tokens
             },
             # Grouping Field required at event scope, so it is supplied per
             # call. Declared values: research · drafting · review.
             grouping_fields: { stage: $stage }
           }'
      )"
  )" || return $?
  _ubb_handle_ack "$ack"
}

# ---- serp-search · complete --------------------------------------------------
# Usage: ubb_record_serp_search <task-id> <event-key> <stage> <cost-in-micros>
#
# MONEY IS EXACT INTEGER MICROS. 1 USD = 1000000, so 0.014 USD is 14000. Do that
# conversion where you have real arithmetic, not in the shell, and never from a
# floating point value.

ubb_record_serp_search() {
  local task_id="${1:?task id}" event_key="${2:?event key}" stage="${3:?stage}" cost_micros="${4:?reported cost in micros}"
  local ack
  ack="$(
    curl -sS -X POST "$UBB_BASE_URL/api/v1/metering/usage" \
      -H "$(_ubb_auth)" \
      -H 'Content-Type: application/json' \
      -d "$(
        jq -n \
          --arg task_id "$task_id" \
          --arg customer_id "${UBB_CUSTOMER_ID:?Set UBB_CUSTOMER_ID.}" \
          --arg event_key "$event_key" \
          --arg stage "$stage" \
          --argjson cost_micros "$cost_micros" \
          '{
             task_id: $task_id,
             customer_id: $customer_id,
             # Declared Event Type, published 2026-07-30. Provider: serpapi.
             event_type: "serp-search",
             idempotency_key: $event_key,
             # Costing method `reported`: UBB does not compute this cost, it
             # records the figure you supply AS your COGS. There is no rate on
             # this Event Type to check it against, so UBB cannot tell a right
             # number from a wrong one and will not pretend to.
             reported_cost_micros: $cost_micros,
             # Quantities still count on a `reported` Event Type. This one is
             # declared `constant`, value 1: recorded and groupable, but it never
             # moves money — here the cost above is the money.
             measurements: { searches: 1 },
             grouping_fields: { stage: $stage }
           }'
      )"
  )" || return $?
  _ubb_handle_ack "$ack"
}

# ------------------------------------------------------------------------------
# 3. SUBTASK  ·  optional, and only where you say so
# ------------------------------------------------------------------------------
# You told the builder this integration creates source_research Subtasks. UBB
# will never infer a Subtask boundary from event timing or from which provider
# you called. Attaching events straight to the parent is a first-class choice,
# not a fallback: pass the parent task id to the record functions instead.
#
# Usage: SUB_ID="$(ubb_start_source_research "$TASK_ID" "$TASK_ID-research")"

ubb_start_source_research() {
  local parent_task_id="${1:?parent task id}"
  local idempotency_key="${2:?an idempotency key for this Subtask — your value, stable across retries}"
  curl -sS -X POST "$UBB_BASE_URL/api/v1/tasks" \
    -H "$(_ubb_auth)" \
    -H 'Content-Type: application/json' \
    -d "$(
      jq -n \
        --arg parent_task_id "$parent_task_id" \
        --arg customer_id "${UBB_CUSTOMER_ID:?Set UBB_CUSTOMER_ID.}" \
        --arg idempotency_key "$idempotency_key" \
        '{
           # Declared Subtask kind, published 2026-08-01. Own COGS ceiling
           # 2.000000 USD; what it spends also rolls up into the 5.000000 USD
           # ceiling of the parent, one hop. Task-scoped Grouping Fields are
           # inherited from the parent.
           task_type: "source_research",
           parent_task_id: $parent_task_id,
           customer_id: $customer_id,
           idempotency_key: $idempotency_key
         }'
    )" | jq -r '.task_id'
}

# ------------------------------------------------------------------------------
# 4. CLOSE  ·  once, and it must say how the work ended
# ------------------------------------------------------------------------------
# `outcome` is required and has no default. UBB will not guess it, because the
# forgiving answer and the answer that moves money are the same word.
#
# report_generation is `event_priced`, so closing does not itself create a
# charge. The outcome is still the honest record of how the work ended, and if
# this Task kind is ever republished as priced-as-a-whole then `delivered`
# becomes the outcome that charges. Regenerate this file when that happens.
#
# Closing a parent cascades still-running Subtasks to `cancelled` — never to the
# outcome of the parent, so their own failure rates stay honest.
#
# Usage: ubb_close_task <task-id> delivered
#        ubb_close_task <task-id> failed upstream_provider_error "connection reset"
#        ubb_close_task <task-id> cancelled user_abandoned

ubb_close_task() {
  local task_id="${1:?task id}"
  local outcome="${2:?outcome is required: delivered, failed or cancelled. There is no default.}"
  local reason_code="${3:-}" reason_detail="${4:-}"
  curl -sS -X POST "$UBB_BASE_URL/api/v1/tasks/$task_id/close" \
    -H "$(_ubb_auth)" \
    -H 'Content-Type: application/json' \
    -d "$(
      jq -n \
        --arg outcome "$outcome" \
        --arg reason_code "$reason_code" \
        --arg reason_detail "$reason_detail" \
        '{ outcome: $outcome, reason_code: $reason_code, reason_detail: $reason_detail }'
    )"
}
