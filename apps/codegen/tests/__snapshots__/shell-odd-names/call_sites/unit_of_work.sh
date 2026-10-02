# Where the piece of work begins. Everything it does goes inside the
# function, which is handed the work's task_id. Check the status of each
# call yourself: set -e does not apply inside a function run this way.
work() {
  task_id=$1
  :
}
ubb_unit_of_work work \
  customer_id="$customer_id" \
  idempotency_key="$idempotency_key"
