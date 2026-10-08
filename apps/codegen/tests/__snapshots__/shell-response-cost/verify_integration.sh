# Checks the paths you declared against a response your supplier really
# returned. UBB never sees that response, so only you can run this.
# It calls nothing: no supplier and no UBB. Save one real response as
# JSON and pass it:
#   sh verify_integration.sh EVENT_TYPE captured-response.json
# configuration_fingerprint = "sha256:cae4658e45eb7e7516e4a6d87733f15c84beb72d94649642222937e87e38636f"

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
    "grounded.search": {
      # measurements.input_tokens.source_path = ["usageMetadata","promptTokenCount"] · event_type "grounded.search"
      "input_tokens": ["usageMetadata","promptTokenCount"]
    }
  } as $declared
  # Every supplier cost read off a response, by Event Type: where, what it
  # represents, and its currency or where that is read. A cost of zero is
  # a cost: what is checked is that each value is there, is what a cost
  # may be, and converts.
  | {
    "grounded.search": "_ubb_check_record_grounded_search"
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
            | (($resolved.at | type) == "number") as $number
            | check($number; $quantity; "is a number"),
              ( select($number)
                | check($resolved.at != 0; $quantity; "is not zero (a constant zero is what a path to the wrong field reads)") ),
              check(
                ([ $paths | to_entries[] | select(.key != $quantity and .value == $path) ]
                 | length) == 0;
                $quantity; "is read from a path no other quantity is read from") ) ] as $lines
      | ([ $lines[] | select(startswith("  " + "FAIL")) ] | length) as $failures
      | ($failures | tostring), ($costs[$event_type] // "-"), $lines[]
    end
UBB_JQ
}

# What checks a supplier's cost read off a response: the runnable file's
# own programs and functions, which read, pin and convert it here exactly
# as they do there, and one check of each Event Type that reads a cost.
UBB_EXIT_VALUE_REFUSED=65

_ubb_jq_cost_record_grounded_search() {
  jq --raw-output --raw-input --slurp \
    --from-file /dev/stdin "$1" <<'UBB_JQ'
  # Reads one value off the response as the response wrote it, and prints
  # what kind of value it is: for a string or an integer, with its text. A
  # response Python's json would not read is not read here either, and a
  # number is never read for what it is worth, because that loses how it
  # was written.
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
    else ($parsed[0] | ubb_at(["usageMetadata","totalCost"])) as $found
    | ($found.value | type) as $type
    | if ($found.found | not) then "missing"
      elif $type == "null" then "null"
      elif $type == "boolean" then "flag"
      elif $type == "string" then
        (if ($found.value | explode | map(select(. == 0)) | length) > 0
         then "other" else "string:" + $found.value end)
      elif $type == "number" then
        (try [ubb_as_written($parts; $inside) | fromjson] catch null) as $copy
        | (if $copy == null then null else ($copy[0] | ubb_at(["usageMetadata","totalCost"])).value end) as $token
        | if ($token | type) == "string" and ($token | ubb_whole)
          then "integer:" + $token else "float" end
      else "other" end
    end
  end
UBB_JQ
}

# A cost a supplier reports is converted to whole micros once, here, on
# its digits as text: no arithmetic is done on the amount, so nothing can
# round it. An amount finer than a micro is refused, never rounded, as
# UBB_EXIT_VALUE_REFUSED.
_ubb_known_currency() {
  case $1 in
    [Aa][Uu][Dd]) _ubb_currency=aud; _ubb_shift=4 ;;
    [Bb][Rr][Ll]) _ubb_currency=brl; _ubb_shift=4 ;;
    [Cc][Aa][Dd]) _ubb_currency=cad; _ubb_shift=4 ;;
    [Cc][Hh][Ff]) _ubb_currency=chf; _ubb_shift=4 ;;
    [Cc][Zz][Kk]) _ubb_currency=czk; _ubb_shift=4 ;;
    [Dd][Kk][Kk]) _ubb_currency=dkk; _ubb_shift=4 ;;
    [Ee][Uu][Rr]) _ubb_currency=eur; _ubb_shift=4 ;;
    [Gg][Bb][Pp]) _ubb_currency=gbp; _ubb_shift=4 ;;
    [Hh][Kk][Dd]) _ubb_currency=hkd; _ubb_shift=4 ;;
    [Ii][Nn][Rr]) _ubb_currency=inr; _ubb_shift=4 ;;
    [Mm][Xx][Nn]) _ubb_currency=mxn; _ubb_shift=4 ;;
    [Nn][Oo][Kk]) _ubb_currency=nok; _ubb_shift=4 ;;
    [Nn][Zz][Dd]) _ubb_currency=nzd; _ubb_shift=4 ;;
    [Pp][Ll][Nn]) _ubb_currency=pln; _ubb_shift=4 ;;
    [Ss][Ee][Kk]) _ubb_currency=sek; _ubb_shift=4 ;;
    [Ss][Gg][Dd]) _ubb_currency=sgd; _ubb_shift=4 ;;
    [Uu][Ss][Dd]) _ubb_currency=usd; _ubb_shift=4 ;;
    [Zz][Aa][Rr]) _ubb_currency=zar; _ubb_shift=4 ;;
    *)
      printf '%s %s\n' "$1" 'is not a currency UBB holds' >&2
      return "$UBB_EXIT_VALUE_REFUSED"
      ;;
  esac
}

_ubb_trim() {
  _ubb_trimmed=${1#"${1%%[![:space:]]*}"}
  _ubb_trimmed=${_ubb_trimmed%"${_ubb_trimmed##*[![:space:]]}"}
}

_ubb_pin_currency() {
  _ubb_trim "$1"
  _ubb_pinned=$_ubb_trimmed
  _ubb_trim "$2"
  _ubb_supplied=$_ubb_trimmed
  if [ -z "$_ubb_pinned" ] && [ -z "$_ubb_supplied" ]; then
    printf '%s\n' 'this cost is denominated in no currency' >&2
    return "$UBB_EXIT_VALUE_REFUSED"
  fi
  if [ -n "$_ubb_pinned" ]; then
    _ubb_known_currency "$_ubb_pinned" || return $?
    _ubb_pinned=$_ubb_currency
  fi
  if [ -n "$_ubb_supplied" ]; then
    _ubb_known_currency "$_ubb_supplied" || return $?
    _ubb_supplied=$_ubb_currency
  fi
  if [ -n "$_ubb_pinned" ] && [ -n "$_ubb_supplied" ] && [ "$_ubb_pinned" != "$_ubb_supplied" ]; then
    printf '%s: %s, %s\n' 'the supplier reported this cost in another currency than the declared one' "$_ubb_supplied" "$_ubb_pinned" >&2
    return "$UBB_EXIT_VALUE_REFUSED"
  fi
  _ubb_currency=${_ubb_pinned:-$_ubb_supplied}
}

_ubb_to_micros() {
  case $2 in
    micros) _ubb_shift=0 ;;
    minor_units) _ubb_known_currency "$3" || return $? ;;
    major_units_decimal) _ubb_shift=6 ;;
    *)
      printf '%s %s\n' "$2" 'is not an amount representation' >&2
      return "$UBB_EXIT_VALUE_REFUSED"
      ;;
  esac
  _ubb_trim "$1"
  _ubb_text=$_ubb_trimmed
  while :; do
    case $_ubb_text in
      *_*) _ubb_text=${_ubb_text%%_*}${_ubb_text#*_} ;;
      *) break ;;
    esac
  done
  _ubb_sign=
  case $_ubb_text in
    -*) _ubb_sign=-; _ubb_text=${_ubb_text#-} ;;
    +*) _ubb_text=${_ubb_text#+} ;;
  esac
  _ubb_exponent=0
  _ubb_exponent_sign=
  case $_ubb_text in
    *[eE]*)
      _ubb_exponent=${_ubb_text#*[eE]}
      _ubb_text=${_ubb_text%%[eE]*}
      case $_ubb_exponent in
        -*) _ubb_exponent_sign=-; _ubb_exponent=${_ubb_exponent#-} ;;
        +*) _ubb_exponent=${_ubb_exponent#+} ;;
      esac
      ;;
  esac
  case $_ubb_text in
    *.*) _ubb_whole=${_ubb_text%%.*}; _ubb_fraction=${_ubb_text#*.} ;;
    *) _ubb_whole=$_ubb_text; _ubb_fraction= ;;
  esac
  _ubb_digits=$_ubb_whole$_ubb_fraction
  case $_ubb_digits in
    '' | *[!0-9]*)
      printf '%s %s\n' "$1" 'is not a number' >&2
      return "$UBB_EXIT_VALUE_REFUSED"
      ;;
  esac
  case $_ubb_exponent in
    '' | *[!0-9]*)
      printf '%s %s\n' "$1" 'is not a number' >&2
      return "$UBB_EXIT_VALUE_REFUSED"
      ;;
  esac
  while :; do
    case $_ubb_digits in
      0?*) _ubb_digits=${_ubb_digits#0} ;;
      *) break ;;
    esac
  done
  while :; do
    case $_ubb_exponent in
      0?*) _ubb_exponent=${_ubb_exponent#0} ;;
      *) break ;;
    esac
  done
  case $_ubb_exponent in
    ???????*)
      printf '%s %s\n' "$1" 'is not an amount of money that can be held: its exponent is out of range' >&2
      return "$UBB_EXIT_VALUE_REFUSED"
      ;;
  esac
  _ubb_scale=$((${_ubb_exponent_sign}${_ubb_exponent} - ${#_ubb_fraction}))
  while [ "$_ubb_scale" -lt 0 ]; do
    case $_ubb_digits in
      ?*0) _ubb_digits=${_ubb_digits%0}; _ubb_scale=$((_ubb_scale + 1)) ;;
      *) break ;;
    esac
  done
  if [ "$_ubb_scale" -gt 40 ] || [ "$_ubb_scale" -lt -40 ]; then
    printf '%s %s\n' "$1" 'is not an amount of money that can be held: its exponent is out of range' >&2
    return "$UBB_EXIT_VALUE_REFUSED"
  fi
  _ubb_scale=$((_ubb_scale + _ubb_shift))
  if [ "$_ubb_scale" -lt 0 ] && [ "$_ubb_digits" != 0 ]; then
    printf '%s %s\n' "$1" 'is not a whole number of micros, and a reported cost is never rounded' >&2
    return "$UBB_EXIT_VALUE_REFUSED"
  fi
  while [ "$_ubb_scale" -gt 0 ] && [ "$_ubb_digits" != 0 ]; do
    _ubb_digits=${_ubb_digits}0
    _ubb_scale=$((_ubb_scale - 1))
  done
  case $_ubb_digits in
    ????????????????????*)
      printf '%s %s\n' "$1" 'is more micros than can be held' >&2
      return "$UBB_EXIT_VALUE_REFUSED"
      ;;
    ???????????????????)
      _ubb_low=${_ubb_digits#??????????}
      _ubb_middle=${_ubb_digits#?}
      _ubb_middle=${_ubb_middle%?????????}
      _ubb_high=${_ubb_digits%??????????????????}
      if [ "$_ubb_high" -gt 9 ] ||
        { [ "$_ubb_high" -eq 9 ] && [ "$_ubb_middle" -gt 223372036 ]; } ||
        { [ "$_ubb_high" -eq 9 ] && [ "$_ubb_middle" -eq 223372036 ] && [ "$_ubb_low" -gt 854775807 ]; }; then
        printf '%s %s\n' "$1" 'is more micros than can be held' >&2
        return "$UBB_EXIT_VALUE_REFUSED"
      fi
      ;;
  esac
  [ "$_ubb_digits" != 0 ] || _ubb_sign=
  _ubb_micros=$_ubb_sign$_ubb_digits
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

_ubb_check_record_grounded_search() {
  _ubb_read=$(_ubb_jq_cost_record_grounded_search "$1") || _ubb_read=unreadable
  case $_ubb_read in
    missing | unreadable) _ubb_found=1 ;;
    *) _ubb_found=0 ;;
  esac
  _ubb_check "$_ubb_found" provider_response_cost_micros 'resolves in the captured response'
  _ubb_admissible=1
  if [ "$_ubb_found" -eq 0 ]; then
    case $_ubb_read in
      string:* | integer:*) _ubb_admissible=0; _ubb_amount=${_ubb_read#*:} ;;
    esac
    _ubb_check "$_ubb_admissible" provider_response_cost_micros 'is an integer or a decimal string, as a reported cost must be'
  fi
  _ubb_pin_currency 'usd' '' 2>/dev/null || return 0
  [ "$_ubb_admissible" -eq 0 ] || return 0
  _ubb_converts=1
  _ubb_to_micros "$_ubb_amount" 'major_units_decimal' "$_ubb_currency" 2>/dev/null && _ubb_converts=0
  _ubb_check "$_ubb_converts" provider_response_cost_micros 'converts to whole micros exactly'
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
