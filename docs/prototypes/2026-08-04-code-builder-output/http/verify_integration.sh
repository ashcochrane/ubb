#!/usr/bin/env bash
# ==============================================================================
# UBB CODE BUILDER  ·  VERIFICATION (raw HTTP target)
#
# Generated alongside ubb_integration.sh. Run it once when you wire the
# integration up, and keep it.
#
#   ./verify_integration.sh openai-embeddings captured_response.json
#
# WHAT THIS PROVES THAT THE CONSOLE CANNOT
#
#   Your Event Type declares WHERE in your provider response each quantity
#   lives. UBB never sees that response, so it cannot check the declaration — a
#   path pointing at the wrong field satisfies every check UBB has and reports
#   the wrong COGS indefinitely. This reads a REAL captured response and asserts
#   the declared paths resolve in it.
#
# WHAT THE CONSOLE PROVES INSTEAD
#
#   That the event landed, and what UBB made of it. Developers -> Code Builder
#   -> Verify. You want both halves.
#
# SANDBOX ONLY. This starts real Tasks and drives one past its ceiling on
# purpose. It refuses to run against a live key.
# ==============================================================================

set -u

. "$(dirname "$0")/ubb_integration.sh"

FAILURES=0

check() {
  if [ "$1" = "true" ]; then
    printf '  ok    %s\n' "$2"
  else
    printf '  FAIL  %s\n' "$2"
    FAILURES=$((FAILURES + 1))
  fi
}

case "${UBB_API_KEY:-}" in
  ubb_test_*) ;;
  *)
    printf 'verify_integration.sh refuses to run without a sandbox key. It starts\n'
    printf 'real Tasks and deliberately drives one past its spend ceiling. Set\n'
    printf 'UBB_API_KEY to a ubb_test_ key and re-run.\n' >&2
    exit 1
    ;;
esac

EVENT_TYPE="${1:?usage: ./verify_integration.sh <event-type> <captured-response.json>}"
CAPTURED="${2:?usage: ./verify_integration.sh <event-type> <captured-response.json>}"

# Every Measurement declared with source_kind `provider_response`, and its
# declared path. Generated from your published configuration.
#
# anthropic-messages does not appear: its mapping is declared against a Python
# SDK response shape, so it has no generated code in this target to verify.
# serp-search does not appear: you supply its cost and its one measurement is a
# declared constant, so there is no provider response to check.
case "$EVENT_TYPE" in
  openai-embeddings) DECLARED_PATHS='.usage.prompt_tokens' ;;
  *)
    printf 'No provider-response mapping is generated for %s in this target.\n' \
      "$EVENT_TYPE" >&2
    exit 1
    ;;
esac

printf '\n1. Declared measurement paths for %s, against your captured response\n' \
  "$EVENT_TYPE"
for path in $DECLARED_PATHS; do
  value="$(jq -r "$path // empty" <"$CAPTURED")"
  check "$([ -n "$value" ] && echo true || echo false)" "resolves at $path"
  check "$(printf '%s' "$value" | grep -Eq '^[0-9]+$' && echo true || echo false)" \
    "$path is a whole number ($value) as declared"
  check "$([ "${value:-0}" -gt 0 ] 2>/dev/null && echo true || echo false)" \
    "$path is greater than zero — a constant zero is the signature of a path pointing at the wrong field"
done

printf '\n2. Start, record and close, against the sandbox\n'
export UBB_IDEMPOTENCY_KEY="verify-$$-$(date +%s)"
TASK_ID="$(ubb_start_report_generation)"
check "$([ -n "$TASK_ID" ] && echo true || echo false)" "the Task started and returned an id"

AGAIN="$(ubb_start_report_generation)"
check "$([ "$AGAIN" = "$TASK_ID" ] && echo true || echo false)" \
  "repeating the start returns the same Task, not a second one"

ACK="$(ubb_record_openai_embeddings "$TASK_ID" "$UBB_IDEMPOTENCY_KEY-1" research "$CAPTURED")"
check "$([ "$(printf '%s' "$ACK" | jq -r '.costing_status')" = resolved ] && echo true || echo false)" \
  "UBB costed the event — 'unresolved' means a required measurement did not arrive under its declared name"
check "$([ "$(printf '%s' "$ACK" | jq -r '.ceiling.status')" = within_ceiling ] && echo true || echo false)" \
  "the COGS ceiling reads within_ceiling — 'indeterminate' means UBB cannot fully cost this Task and will not enforce it"

printf '\n3. The stop signal\n'
# The branch easiest to break and hardest to notice: a stop rides a 200
# response. If _ubb_handle_ack stops returning 3, every stop UBB issues is
# discarded in silence and nothing else fails.
export UBB_IDEMPOTENCY_KEY="verify-stop-$$-$(date +%s)"
STOP_TASK_ID="$(ubb_start_report_generation)"
STOPPED=false
for i in 1 2 3; do
  # 4.00 USD against a 5.000000 USD ceiling: the second one crosses it.
  if ! ubb_record_serp_search "$STOP_TASK_ID" "$UBB_IDEMPOTENCY_KEY-$i" research 4000000 >/dev/null; then
    STOPPED=true
    break
  fi
done
check "$STOPPED" "spending past the ceiling made the record function return non-zero"
[ "$STOPPED" = true ] || printf '        Check that _ubb_handle_ack still returns 3 on .stop.requested.\n'

ubb_close_task "$STOP_TASK_ID" failed spend_ceiling_reached "verification run" >/dev/null
ubb_close_task "$TASK_ID" delivered >/dev/null

printf '\n'
if [ "$FAILURES" -gt 0 ]; then
  printf '%s check(s) failed.\n' "$FAILURES"
  exit 1
fi
printf 'All checks passed.\n'
