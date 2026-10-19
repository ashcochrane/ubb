# Where the work is run, if you act on a stop's scope yourself. This is
# not error handling: the event was recorded and charged.
# UBB_STOP_REQUESTED holds the stop as JSON: its scope and reason, what
# applied it, and the bound and the amount measured against it, each null
# where it does not apply. Pass the status on to whatever runs this code.
ubb_run_task work \
  customer_id="$customer_id" \
  idempotency_key="$idempotency_key" \
  environment="$environment" && work_status=$? || work_status=$?
if [ "$work_status" -eq "$UBB_EXIT_STOP_REQUESTED" ]; then
  :
fi
