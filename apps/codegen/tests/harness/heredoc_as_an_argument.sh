# The form the renderer does NOT write (#180 §12.1, decided in #578): a jq
# program handed to jq as an argument, out of a quoted heredoc through `cat`.
# Kept, and run by the suite, so that the comparison is executed and not
# remembered. heredoc_from_standard_input.sh beside this file is the form
# chosen, over the same names.
#
# On every shell the suite runs under, this carries every name unchanged, as
# the other form does. What decided against it is that a program handed over
# as an argument is INSIDE A COMMAND SUBSTITUTION by construction, and bash
# 3.2 — what macOS ships as bash and as sh — reads the text of a heredoc there
# as shell. The one backtick in the names below ends this file for it:
#
#   $ docker run --rm -v "$PWD/apps/codegen/tests/harness:/h:ro" bash:3.2 \
#       sh -c 'apk add -q jq && bash /h/heredoc_as_an_argument.sh'
#   /h/heredoc_as_an_argument.sh: line 30: bad substitution: no closing `)' in "$(cat <<'UBB_JQ'
#
# and the other file, run the same way, prints what it prints everywhere.
apostrophe="it's"
dollar='$HOME'
command='$(touch made-by-a-name)'
backtick='back`tick'
backslash='back\slash\n'
unicode='naïve–日本語'
hyphen='cache-read'
space='cache read tokens'
parenthesis='unbalanced)'
delimiter='UBB_JQ'

program() {
  jq --compact-output --null-input \
    --arg v1 "$apostrophe" --arg v2 "$dollar" --arg v3 "$command" --arg v4 "$backtick" \
    --arg v5 "$backslash" --arg v6 "$unicode" --arg v7 "$hyphen" --arg v8 "$space" \
    --arg v9 "$parenthesis" --arg v10 "$delimiter" \
    "$(cat <<'UBB_JQ'
  # event_type = "it's a $5 chat-completion" · provider "o'reilly & co"
  {
    # measurements = "it's"
    "it's": $v1,
    # measurements = "$HOME"
    "$HOME": $v2,
    # measurements = "$(touch made-by-a-name)"
    "$(touch made-by-a-name)": $v3,
    # measurements = "back`tick"
    "back`tick": $v4,
    "back\\slash\\n": $v5,
    "naïve–日本語": $v6,
    "cache-read": $v7,
    "cache read tokens": $v8,
    "unbalanced)": $v9,
    # measurements = "UBB_JQ"
    "UBB_JQ": $v10
  }
UBB_JQ
)"
}

carried=$(program) || exit $?
printf 'carried=%s\n' "$carried"
if [ -e made-by-a-name ]; then
  printf 'ran_anything=yes\n'
else
  printf 'ran_anything=no\n'
fi
