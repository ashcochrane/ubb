# Inside the work, before it ends: exactly once. Work that returns
# success having declared nothing is left open, and that is reported.
ubb_close_task \
  task_id="$task_id" \
  outcome="$outcome" || return $?
