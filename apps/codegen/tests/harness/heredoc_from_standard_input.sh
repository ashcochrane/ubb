# The form the renderer writes (#180 §12.1, decided in #578): a jq program
# read by jq from standard input, from a quoted heredoc, in a function that is
# nothing else. What is captured is the function's output, so the heredoc is
# never inside a command substitution.
#
# Run over the kinds of name a tenant can declare: an apostrophe, a dollar
# sign, command-like text, one backtick, a backslash, characters outside
# ASCII, a hyphen, a space and an unbalanced parenthesis. Each is used twice,
# as a key written into the program and as a value handed to jq.
#
# heredoc_as_an_argument.sh beside this file is the form decided against.
apostrophe="it's"
dollar='$HOME'
command='$(touch made-by-a-name)'
backtick='back`tick'
backslash='back\slash\n'
unicode='naïve–日本語'
hyphen='cache-read'
space='cache read tokens'
parenthesis='unbalanced)'

program() {
  jq --compact-output --null-input \
    --arg v1 "$apostrophe" --arg v2 "$dollar" --arg v3 "$command" --arg v4 "$backtick" \
    --arg v5 "$backslash" --arg v6 "$unicode" --arg v7 "$hyphen" --arg v8 "$space" \
    --arg v9 "$parenthesis" \
    --from-file /dev/stdin <<'UBB_JQ'
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
    "unbalanced)": $v9
  }
UBB_JQ
}

carried=$(program) || exit $?
printf 'carried=%s\n' "$carried"
if [ -e made-by-a-name ]; then
  printf 'ran_anything=yes\n'
else
  printf 'ran_anything=no\n'
fi
