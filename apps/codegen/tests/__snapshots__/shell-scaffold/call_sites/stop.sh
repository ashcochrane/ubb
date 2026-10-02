# Directly after whatever runs the work, where you can act on a stop's
# scope. This is not error handling: the event was recorded and charged.
# UBB_STOP_REQUESTED holds the stop's scope and reason, as JSON.
if [ "$?" -eq "$UBB_EXIT_STOP_REQUESTED" ]; then
  :
  return "$UBB_EXIT_STOP_REQUESTED"
fi
