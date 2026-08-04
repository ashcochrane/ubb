# Where these calls go in your application

`ubb_integration.py` is a file you drop in and never edit. This page holds the
lines that go into code you *do* edit. Each block is copied on its own, because
in a real application they are rarely in the same file — and often not in the
same process.

**Nothing on this page contains a generated value.** No Task kind, no Event Type,
no measurement name, no path into a provider response. That is deliberate: it is
what lets you replace `ubb_integration.py` wholesale every time your
configuration changes without revisiting any of these call sites.

> On the builder page each block below is its own copy button. This file is the
> prototype's stand-in for that.

---

## 1 · Where the unit of work begins

```python
from ubb_integration import report_generation

with report_generation(
    customer_id=customer.id,
    idempotency_key=report.id,        # YOUR id for this work, stable across retries
    environment=settings.ENVIRONMENT,
    workspace_id=workspace.id,
) as task:
    ...                            # your work goes here
```

`idempotency_key` is the one that repays reading twice. It must be *your*
identifier for this unit of work and it must be the same value every time you
retry it. A fresh value per attempt makes each retry a separate Task.

---

## 2 · After each provider call

```python
from ubb_integration import record_anthropic_messages

response = anthropic.messages.create(...)          # your existing call

record_anthropic_messages(task, response, event_key=response.id, stage="research")
```

The generated function does not call your provider. It takes the response you
already have, so it sits *after* your call and never in front of it.

`event_key` identifies this one provider call. Your provider's own response
identifier is usually the right value: stable if you retry the report, different
for every genuine call.

---

## 3 · Around the whole unit of work

```python
from ubb.exceptions import UBBStoppedError

try:
    generate_report(...)
except UBBStoppedError as stopped:
    if stopped.scope == "customer":
        pause_all_work_for(customer)   # not just this report
    else:
        pass                           # this report is over; the rest continue
```

**This is not error handling.** Every call in block 2 succeeded — HTTP 200, event
recorded, event charged. UBB signals a stop with fields on a successful
response, and the generated code turns those fields into an exception so that
ignoring them takes an edit rather than an oversight.

It belongs here rather than beside each record call because `scope` may be
`customer`, and no single record call knows what else that customer has running.

---

## 4 · Where the work finishes

```python
task.deliver()                                    # you delivered it
task.fail(reason_code="upstream_provider_error")  # it failed
task.cancel(reason_code="user_abandoned")         # you or your user stopped it
```

One of these is required. There is no default and the block will not guess: an
exception inside the block closes the Task as failed, but a clean exit that
declared nothing raises rather than assuming delivery.

---

## 5 · Only if you create Subtasks

```python
from ubb_integration import start_source_research, record_anthropic_messages

research = start_source_research(task, idempotency_key=f"{report.id}-research")
response = anthropic.messages.create(...)
record_anthropic_messages(research, response, event_key=response.id, stage="research")
research.deliver()
```

Pass `research` where you would have passed `task`, and those events attach to
the Subtask and race its own ceiling as well as the parent's.

Attaching events to the parent instead is a normal thing to do, not a fallback.
Do that and there is simply no Subtask — UBB will not invent one from the shape
of your traffic.

---

## When the work spans two processes

A Task started in a web request and finished by a worker cannot use the `with`
block. Use the pieces directly; the handle is plain data.

```python
# web request
task = start_report_generation(
    customer_id=customer.id,
    idempotency_key=report.id,
    environment=settings.ENVIRONMENT,
    workspace_id=workspace.id,
)
queue.enqueue(run_report, report.id, task.task_id)

# worker — same key, so this returns the SAME Task rather than a second one
task = start_report_generation(
    customer_id=customer.id,
    idempotency_key=report.id,
    environment=settings.ENVIRONMENT,
    workspace_id=workspace.id,
)
```

You may pass the handle instead of re-deriving it. Re-deriving it is shown here
because it is the version that survives the queue losing a message.
