# Checks the paths you declared against a response your supplier really
# returned. UBB never sees that response, so only you can run this.
# It calls nothing: no supplier and no UBB. Save one real response as
# JSON and pass it:
#   sh verify_integration.sh EVENT_TYPE captured-response.json
# configuration_fingerprint = "sha256:c7ff841fa1b662136da3277b261442c0c085bc82923bd2c9fd6757a09fabfb44"

# Checks that jq can do what this script asks of it. It contacts nothing
# and creates nothing.
command -v jq >/dev/null 2>&1 || {
  printf '%s\n' 'This file requires jq, and none is installed.' >&2
  exit 69
}
ubb_probe=0
jq --null-input --arg probe_text 1 --slurpfile probe_file /dev/null --raw-output \
  --from-file /dev/stdin >/dev/null 2>&1 <<'UBB_JQ' || ubb_probe=$?
  # A program of this file's own form: read from standard input, holding
  # comments, passing each option and using each form its programs use, and
  # naming each function they call in a branch that is never taken.
  def probe_definition($first; $second): $first + $second;
  [
    $probe_text,
    $probe_file,
    probe_definition(1; 2),
    (1 as $probe_value | $probe_value),
    (if false then 1 elif false then 2 else 3 end),
    (reduce (1, 2) as $probe_item (0; . + $probe_item)),
    (if false then [has("probe"), keys_unsorted, length, not, select(true), startswith("probe"), to_entries, tojson, tostring, type] else 1 end)
  ]
UBB_JQ
[ "$ubb_probe" -eq 0 ] || {
  printf '%s\n' 'The installed jq cannot run the programs this file hands it. jq 1.5 or later can.' >&2
  exit 69
}

ubb_checked() {
  jq --raw-output --null-input \
    --arg event_type "${1-}" \
    --arg given "$#" \
    --slurpfile captured "${2:-/dev/null}" \
    --from-file /dev/stdin <<'UBB_JQ'
  # Every quantity read off a response, by Event Type, and where.
  {
  } as $declared
  | def resolve($path):
      reduce $path[] as $segment ({"found": true, "at": .};
        if .found and (.at | type) == "object" and (.at | has($segment))
        then {"found": true, "at": .at[$segment]}
        else {"found": false, "at": null} end);
    def check($passed; $quantity; $message):
      "  " + (if $passed then "ok  " else "FAIL" end)
      + " " + ($quantity | tojson) + " " + $message;
    if ($declared | length) == 0
    then "0", "No selected Event Type reads a quantity off a response. There is nothing to check."
    elif $given != "2" or ($declared | has($event_type) | not)
    then "2", "usage: sh verify_integration.sh EVENT_TYPE captured-response.json", "Event Types with a quantity read off a response:",
      ($declared | keys_unsorted[] | "  " + tojson)
    else
      $declared[$event_type] as $paths
      | [ $paths | to_entries[] | .key as $quantity | .value as $path
        | ($captured[0] | resolve($path)) as $resolved
        | check($resolved.found; $quantity; "resolves in the captured response"),
          ( select($resolved.found)
            | (($resolved.at | type) == "number") as $number
            | check($number; $quantity; "is a number"),
              ( select($number)
                | check($resolved.at != 0; $quantity; "is not zero (a constant zero is what a path to the wrong field reads)") ),
              check(
                ([ $paths | to_entries[] | select(.key != $quantity and .value == $path) ]
                 | length) == 0;
                $quantity; "is read from a path no other quantity is read from") ) ] as $lines
      | ([ $lines[] | select(startswith("  " + "FAIL")) ] | length) as $failures
      | if $failures > 0
        then "1", $lines[], (($failures | tostring) + " " + "check(s) failed.")
        else "0", $lines[], "Every check passed." end
    end
UBB_JQ
}

ubb_report=$(ubb_checked "$@") || exit $?

{
  IFS= read -r ubb_verdict
  while IFS= read -r ubb_line; do
    printf '%s\n' "$ubb_line"
  done
} <<UBB_REPORT
$ubb_report
UBB_REPORT
exit "$ubb_verdict"
