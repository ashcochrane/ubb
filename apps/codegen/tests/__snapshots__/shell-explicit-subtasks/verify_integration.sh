# Checks the paths you declared against a response your supplier really
# returned. UBB never sees that response, so only you can run this.
# It calls nothing: no supplier and no UBB. Save one real response as
# JSON and pass it:
#   sh verify_integration.sh EVENT_TYPE captured-response.json
# configuration_fingerprint = "sha256:61abec36f08fca846bee13d212367ccab77625dca341dec3a75076ae67ebd869"

# Checks that jq can do what this script asks of it. It contacts nothing
# and creates nothing.
command -v jq >/dev/null 2>&1 || {
  printf '%s\n' 'This file requires jq, and none is installed.' >&2
  exit 69
}
ubb_probe=0
jq --null-input --arg probe_text 1 --slurpfile probe_file /dev/null --raw-output --raw-input --slurp \
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
    ([foreach (1, 2) as $probe_item (0; . + $probe_item; .)]),
    (try 1 catch 2),
    (if false then [add, empty, endswith("probe"), explode, fromjson, has("probe"), keys_unsorted, last, length, map(.), not, range(0; 1), select(true), split("probe"), startswith("probe"), to_entries, tojson, tostring, type] else 1 end)
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
    "gemini.generate": {
      # measurements.candidate_tokens.source_path = ["usage_metadata","candidates_token_count"] · event_type "gemini.generate"
      "candidate_tokens": ["usage_metadata","candidates_token_count"],
      # measurements.prompt_tokens.source_path = ["usageMetadata","promptTokenCount"] · event_type "gemini.generate"
      "prompt_tokens": ["usageMetadata","promptTokenCount"]
    }
  } as $declared
  # Every supplier cost read off a response, by Event Type: where, what it
  # represents, and its currency or where that is read. A cost of zero is
  # a cost: what is checked is that each value is there, is what a cost
  # may be, and converts.
  | {
    "gemini.generate": "_ubb_check_record_gemini_generate"
  } as $costs
  | def resolve($path):
      reduce $path[] as $segment ({"found": true, "at": .};
        if .found and (.at | type) == "object" and (.at | has($segment))
        then {"found": true, "at": .at[$segment]}
        else {"found": false, "at": null} end);
    def check($passed; $quantity; $message):
      "  " + (if $passed then "ok  " else "FAIL" end)
      + " " + ($quantity | tojson) + " " + $message;
    ($declared + $costs) as $known
    | if ($known | length) == 0
    then "nothing", "-", "No selected Event Type reads a quantity or a cost off a response. There is nothing to check."
    elif $given != "2" or ($known | has($event_type) | not)
    then "usage", "-", "usage: sh verify_integration.sh EVENT_TYPE captured-response.json", "Event Types with a quantity or a cost read off a response:",
      ($known | keys_unsorted[] | "  " + tojson)
    else
      ($declared[$event_type] // {}) as $paths
      | [ $paths | to_entries[] | .key as $quantity | .value as $path
        | ($captured[0] | resolve($path)) as $resolved
        | check($resolved.found; $quantity; "resolves in the captured response"),
          ( select($resolved.found)
            | check(
                ([ $paths | to_entries[] | select(.key != $quantity and .value == $path) ]
                 | length) == 0;
                $quantity; "is read from a path no other quantity is read from") ) ] as $lines
      | ([ $lines[] | select(startswith("  " + "FAIL")) ] | length) as $failures
      | ($failures | tostring), ($costs[$event_type] // "-"), $lines[]
    end
UBB_JQ
}

# What checks a value read off a response: the runnable file's own
# programs and functions, which read a quantity, and read, pin and
# convert a cost, here exactly as they do there; and one check of each
# Event Type that reads either.
UBB_EXIT_VALUE_REFUSED=65

_ubb_jq_quantity_record_gemini_generate_1() {
  jq --raw-output --raw-input --slurp \
    --from-file /dev/stdin "$1" <<'UBB_JQ'
  # Reads one value off the response as the response wrote it, and prints
  # what kind of value it is: for a string or an integer, with its text. A
  # response holding a number Python's json does not read is not read, and
  # no number is read for what it is worth, because that loses how it was
  # written.
  def ubb_escapes_next:
    if endswith("\\") then
      explode as $c
      | ([range(0; $c | length) | select($c[.] != 92)] | last) as $kept
      | ((($c | length) - (if $kept == null then 0 else $kept + 1 end)) % 2) == 1
    else false end;
  def ubb_inside_flags:
    [foreach .[] as $part ([false, false];
      [.[1], (if .[1] then ($part | ubb_escapes_next) else true end)];
      .[0])];
  def ubb_without($character):
    split($character) | add // "";
  def ubb_marked($character):
    split($character)
    | if length == 0 then ""
      else [.[0], (.[1:][] | ("\u0001" + $character + "\u0001"), .)] | add end;
  def ubb_scalars_quoted:
    ubb_without(" ") | ubb_without("\t") | ubb_without("\n") | ubb_without("\r")
    | ubb_marked(",") | ubb_marked(":") | ubb_marked("[") | ubb_marked("]") | ubb_marked("{") | ubb_marked("}")
    | split("\u0001")
    | map(if . == "" or . == "," or . == ":" or . == "[" or . == "]" or . == "{" or . == "}"
      then . else "\"" + . + "\"" end)
    | add // "";
  def ubb_as_written($parts; $inside):
    [range(0; $parts | length) as $at
      | (if $at > 0 then "\"" else empty end),
        (if $inside[$at] then $parts[$at] else ($parts[$at] | ubb_scalars_quoted) end)]
    | add;
  def ubb_python_reads($parts; $inside):
    ([range(0; $parts | length) as $at | if $inside[$at] then empty else $parts[$at] end] | add // ""
      | ubb_without(" ") | ubb_without("\t") | ubb_without("\n") | ubb_without("\r")
      | ubb_marked(",") | ubb_marked(":") | ubb_marked("[") | ubb_marked("]") | ubb_marked("{") | ubb_marked("}")
      | "\u0001" + . + "\u0001"
      | ubb_without("\u0001true\u0001") | ubb_without("\u0001false\u0001") | ubb_without("\u0001null\u0001") | ubb_without("\u0001NaN\u0001") | ubb_without("\u0001Infinity\u0001") | ubb_without("\u0001-Infinity\u0001")) as $scalars
    | ([range(0; $parts | length) as $at | if $inside[$at] then $parts[$at] else empty end] | add // "") as $strings
    | ([["a", "b", "c", "d", "f", "g", "h", "i", "j", "k", "l", "m", "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z", "A", "B", "C", "D", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "(", ")", "\u0000", "\ufeff", "\u0001+", "\u0001.", "\u0001-.", ".\u0001", ".e", ".E", "\u000100", "\u0001-00", "\u000101", "\u0001-01", "\u000102", "\u0001-02", "\u000103", "\u0001-03", "\u000104", "\u0001-04", "\u000105", "\u0001-05", "\u000106", "\u0001-06", "\u000107", "\u0001-07", "\u000108", "\u0001-08", "\u000109", "\u0001-09"][]
      | select(. as $pattern | $scalars | split($pattern) | length > 1)] | length) == 0
    and ($strings | split("\u0000") | length) < 2;
  def ubb_at($path):
    reduce $path[] as $segment ({"found": true, "value": .};
      if .found and (.value | type) == "object" and (.value | has($segment))
      then {"found": true, "value": .value[$segment]}
      else {"found": false, "value": null} end);
  def ubb_whole:
    explode
    | (if .[0] == 45 then .[1:] else . end)
    | length > 0 and (map(select(. < 48 or . > 57)) | length) == 0
      and (length == 1 or .[0] != 48);
  . as $text
  | (try [fromjson] catch null) as $parsed
  | if $parsed == null then "unreadable"
    else ($text | split("\"")) as $parts
    | ($parts | ubb_inside_flags) as $inside
    | if (ubb_python_reads($parts; $inside) | not) then "unreadable"
    else ($parsed[0] | ubb_at(["usage_metadata","candidates_token_count"])) as $found
    | ($found.value | type) as $type
    | if ($found.found | not) then "missing"
      elif $type == "null" then "null"
      elif $type == "boolean" then "flag"
      elif $type == "string" then
        (if ($found.value | explode | map(select(. == 0)) | length) > 0
         then "other" else "string:" + $found.value end)
      elif $type == "number" then
        (try [ubb_as_written($parts; $inside) | fromjson] catch null) as $copy
        | (if $copy == null then null else ($copy[0] | ubb_at(["usage_metadata","candidates_token_count"])).value end) as $token
        | if ($token | type) == "string" and ($token | ubb_whole)
          then "integer:" + $token else "float" end
      else "other" end
    end
  end
UBB_JQ
}

_ubb_jq_quantity_record_gemini_generate_2() {
  jq --raw-output --raw-input --slurp \
    --from-file /dev/stdin "$1" <<'UBB_JQ'
  # Reads one value off the response as the response wrote it, and prints
  # what kind of value it is: for a string or an integer, with its text. A
  # response holding a number Python's json does not read is not read, and
  # no number is read for what it is worth, because that loses how it was
  # written.
  def ubb_escapes_next:
    if endswith("\\") then
      explode as $c
      | ([range(0; $c | length) | select($c[.] != 92)] | last) as $kept
      | ((($c | length) - (if $kept == null then 0 else $kept + 1 end)) % 2) == 1
    else false end;
  def ubb_inside_flags:
    [foreach .[] as $part ([false, false];
      [.[1], (if .[1] then ($part | ubb_escapes_next) else true end)];
      .[0])];
  def ubb_without($character):
    split($character) | add // "";
  def ubb_marked($character):
    split($character)
    | if length == 0 then ""
      else [.[0], (.[1:][] | ("\u0001" + $character + "\u0001"), .)] | add end;
  def ubb_scalars_quoted:
    ubb_without(" ") | ubb_without("\t") | ubb_without("\n") | ubb_without("\r")
    | ubb_marked(",") | ubb_marked(":") | ubb_marked("[") | ubb_marked("]") | ubb_marked("{") | ubb_marked("}")
    | split("\u0001")
    | map(if . == "" or . == "," or . == ":" or . == "[" or . == "]" or . == "{" or . == "}"
      then . else "\"" + . + "\"" end)
    | add // "";
  def ubb_as_written($parts; $inside):
    [range(0; $parts | length) as $at
      | (if $at > 0 then "\"" else empty end),
        (if $inside[$at] then $parts[$at] else ($parts[$at] | ubb_scalars_quoted) end)]
    | add;
  def ubb_python_reads($parts; $inside):
    ([range(0; $parts | length) as $at | if $inside[$at] then empty else $parts[$at] end] | add // ""
      | ubb_without(" ") | ubb_without("\t") | ubb_without("\n") | ubb_without("\r")
      | ubb_marked(",") | ubb_marked(":") | ubb_marked("[") | ubb_marked("]") | ubb_marked("{") | ubb_marked("}")
      | "\u0001" + . + "\u0001"
      | ubb_without("\u0001true\u0001") | ubb_without("\u0001false\u0001") | ubb_without("\u0001null\u0001") | ubb_without("\u0001NaN\u0001") | ubb_without("\u0001Infinity\u0001") | ubb_without("\u0001-Infinity\u0001")) as $scalars
    | ([range(0; $parts | length) as $at | if $inside[$at] then $parts[$at] else empty end] | add // "") as $strings
    | ([["a", "b", "c", "d", "f", "g", "h", "i", "j", "k", "l", "m", "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z", "A", "B", "C", "D", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "(", ")", "\u0000", "\ufeff", "\u0001+", "\u0001.", "\u0001-.", ".\u0001", ".e", ".E", "\u000100", "\u0001-00", "\u000101", "\u0001-01", "\u000102", "\u0001-02", "\u000103", "\u0001-03", "\u000104", "\u0001-04", "\u000105", "\u0001-05", "\u000106", "\u0001-06", "\u000107", "\u0001-07", "\u000108", "\u0001-08", "\u000109", "\u0001-09"][]
      | select(. as $pattern | $scalars | split($pattern) | length > 1)] | length) == 0
    and ($strings | split("\u0000") | length) < 2;
  def ubb_at($path):
    reduce $path[] as $segment ({"found": true, "value": .};
      if .found and (.value | type) == "object" and (.value | has($segment))
      then {"found": true, "value": .value[$segment]}
      else {"found": false, "value": null} end);
  def ubb_whole:
    explode
    | (if .[0] == 45 then .[1:] else . end)
    | length > 0 and (map(select(. < 48 or . > 57)) | length) == 0
      and (length == 1 or .[0] != 48);
  . as $text
  | (try [fromjson] catch null) as $parsed
  | if $parsed == null then "unreadable"
    else ($text | split("\"")) as $parts
    | ($parts | ubb_inside_flags) as $inside
    | if (ubb_python_reads($parts; $inside) | not) then "unreadable"
    else ($parsed[0] | ubb_at(["usageMetadata","promptTokenCount"])) as $found
    | ($found.value | type) as $type
    | if ($found.found | not) then "missing"
      elif $type == "null" then "null"
      elif $type == "boolean" then "flag"
      elif $type == "string" then
        (if ($found.value | explode | map(select(. == 0)) | length) > 0
         then "other" else "string:" + $found.value end)
      elif $type == "number" then
        (try [ubb_as_written($parts; $inside) | fromjson] catch null) as $copy
        | (if $copy == null then null else ($copy[0] | ubb_at(["usageMetadata","promptTokenCount"])).value end) as $token
        | if ($token | type) == "string" and ($token | ubb_whole)
          then "integer:" + $token else "float" end
      else "other" end
    end
  end
UBB_JQ
}

# A quantity is passed as text and sent as text: an exact decimal, digits
# with an optional leading minus and an optional fraction, and whole
# where it is declared an integer. It is carried exactly at any length,
# never through a number, or refused as UBB_EXIT_VALUE_REFUSED.
_ubb_exact() {
  _ubb_digits=${1#-}
  case $_ubb_digits in
    '' | *[!0-9.]* | .* | *. | *.*.*) return 1 ;;
  esac
  case $2:$_ubb_digits in
    integer:*.*[!0]*) return 2 ;;
  esac
  return 0
}

_ubb_check() {
  if [ "$1" -eq 0 ]; then
    _ubb_verdict='ok  '
  else
    _ubb_verdict='FAIL'
    ubb_failures=$((ubb_failures + 1))
  fi
  printf '  %s "%s" %s\n' "$_ubb_verdict" "$2" "$3"
}

_ubb_check_record_gemini_generate() {
  _ubb_read=$(_ubb_jq_quantity_record_gemini_generate_1 "$1") || _ubb_read=unreadable
  case $_ubb_read in
    missing | unreadable) ;;
    *)
      _ubb_exactly=1
      case $_ubb_read in
        string:* | integer:*)
          _ubb_exact "${_ubb_read#*:}" integer && _ubb_exactly=0 ;;
      esac
      _ubb_check "$_ubb_exactly" 'candidate_tokens' 'is an integer or a decimal string, as a recorded quantity must be'
      ;;
  esac
  _ubb_read=$(_ubb_jq_quantity_record_gemini_generate_2 "$1") || _ubb_read=unreadable
  case $_ubb_read in
    missing | unreadable) ;;
    *)
      _ubb_exactly=1
      case $_ubb_read in
        string:* | integer:*)
          _ubb_exact "${_ubb_read#*:}" integer && _ubb_exactly=0 ;;
      esac
      _ubb_check "$_ubb_exactly" 'prompt_tokens' 'is an integer or a decimal string, as a recorded quantity must be'
      ;;
  esac
}

ubb_report=$(ubb_checked "$@") || exit $?

{
  IFS= read -r ubb_verdict
  IFS= read -r ubb_then
  while IFS= read -r ubb_line; do
    printf '%s\n' "$ubb_line"
  done
} <<UBB_REPORT
$ubb_report
UBB_REPORT
case $ubb_verdict in
  nothing) exit 0 ;;
  usage) exit 2 ;;
esac
ubb_failures=$ubb_verdict
[ "$ubb_then" = - ] || "$ubb_then" "$2"
if [ "$ubb_failures" -gt 0 ]; then
  printf '%s %s\n' "$ubb_failures" 'check(s) failed.'
  exit 1
fi
printf '%s\n' 'Every check passed.'
exit 0
