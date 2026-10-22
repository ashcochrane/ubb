# Inside the block, before it ends: exactly one of these. A block that
# ends cleanly having declared nothing raises TaskOutcomeRequired and
# leaves the work open.
task.complete()
task.fail(outcome_reason)
task.cancel()
