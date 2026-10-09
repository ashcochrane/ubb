"""The customer's own script: the glue a customer writes around a rendered
artifact, built from the rendered call-site blocks (#582).

A generated artifact has no main. The Python target is a module and a set of
call-site blocks to paste into the tenant's own code; the shell target is a
file to source and a set of blocks to paste into the tenant's own script. So
the harness writes what a customer would: a script that imports or sources
the module and pastes the blocks into its own code **exactly as rendered**.

What the script is allowed to add is what a customer's code holds and the
artifact cannot (ADR-0008 §5, #158 §5.4):

* the runtime VALUES a block's parameters name — a customer id, an
  idempotency key, a Grouping Field value, a quantity, a supplier's reported
  cost, a supplier's response — assigned to a variable of the parameter's
  own name before the block that reads it;
* the code that goes where a block leaves room for it: the body of the work,
  inside a `with`/`work()` whose body is the block's placeholder (`...` in
  Python, `:` in shell), and what to do when a stop arrives;
* the choices the blocks offer: the close block lists the three ways work
  can end, and the work declares one of them — on a Subtask, whose handle
  the Python block does not name, the same declaration on the Subtask's own
  handle; and two shell blocks run the work — `run_task.sh` and `stop.sh`,
  for a customer who acts on a stop's scope — so the script defines `work()`
  as the first one does and runs it with the second, whose status it passes
  on as its own;
* lines that print what it saw, as `name=value`, for the test to read.

It never changes the text of a rendered line. It places blocks whole, at the
indentation of where they are pasted, inside its own code (a Python
`def main()`, and a `try` that reports a stop at the process's boundary);
the one line it chooses from a block is taken as written; and nothing here
reads or writes a file under `artifact/`.

A unit of work is declared as data (`Work`), so a scenario says what the
customer's code does and not how either target spells it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Union

from _harness import ARTIFACT, CUSTOMER, CUSTOMER_RESPONSES, Artifact

#: How a Python library's response is read (attribute by attribute), as the
#: Blueprint names it.
PYTHON_OBJECT = "python_object"

#: What every unit of work in this suite declares when it ends: the work
#: was delivered.
DELIVERED = "delivered"


@dataclass(frozen=True)
class Response:
    """A supplier's response the customer's code already holds:
    `provider_responses/<fixture>.json`, handed over as the Blueprint says
    the call reads it."""

    fixture: str


@dataclass(frozen=True)
class CustomerId:
    """The id of a customer the scenario created, by its external id."""

    external_id: str


Value = Union[str, int, Response, CustomerId]


@dataclass(frozen=True)
class Record:
    """One call to a supplier, recorded. `event_type` picks the rendered
    block (`None` for the one a scaffold renders before anything is
    selected); `values` are the block's runtime parameters, by name. The
    block's `task_id` is the handle the record sits in, and is set here."""

    event_type: str | None
    values: Mapping[str, Value] = field(default_factory=dict)


@dataclass(frozen=True)
class Subtask:
    """A Subtask the work starts, the records made inside it, and its end."""

    kind: str
    values: Mapping[str, Value] = field(default_factory=dict)
    records: tuple[Record, ...] = ()


@dataclass(frozen=True)
class Work:
    """One unit of work, as the customer's code runs it: started for
    `customer` (an external id the scenario created), with the start's own
    runtime values, what it does in order, and declared delivered at the end."""

    customer: str
    values: Mapping[str, Value] = field(default_factory=dict)
    does: tuple[Union[Record, Subtask], ...] = ()


def tail(key: str | None) -> str:
    """The renderer's own rule for the end of a function's name (#577):
    every character outside `[A-Za-z0-9]` becomes `_`. A record for nothing
    selected is the scaffold's `usage`."""
    if key is None:
        return "usage"
    return "".join(character if character.isascii() and character.isalnum()
                   else "_" for character in key)


def _lines(block: str) -> list[str]:
    return block.rstrip("\n").split("\n")


def _fill(block: str, placeholder: str, inner: list[str]) -> list[str]:
    """The block's lines, with its one placeholder line replaced by `inner`
    at the placeholder's own indentation. Nothing else changes."""
    lines = _lines(block)
    at = [index for index, line in enumerate(lines)
          if line.strip() == placeholder]
    if len(at) != 1:
        raise AssertionError(
            f"expected one {placeholder!r} line in the block:\n{block}")
    line = lines[at[0]]
    indent = line[:len(line) - len(line.lstrip())]
    return (lines[:at[0]] + [indent + entry if entry else entry
                             for entry in inner] + lines[at[0] + 1:])


def _resolved(values: Mapping[str, Value],
              customers: Mapping[str, str]) -> dict[str, Value]:
    """`values`, with each customer named by external id replaced by its id."""
    return {name: customers[value.external_id]
            if isinstance(value, CustomerId) else value
            for name, value in values.items()}


def _representation(artifact: Artifact, event_type: str | None) -> str | None:
    """How the Blueprint says the record for `event_type` reads a
    supplier's response."""
    for call in artifact.blueprint["calls"]:
        values = {argument["name"]: argument.get("value")
                  for argument in call["arguments"]}
        if values.get("event_type") == event_type:
            return values.get("event_type.response_shape_representation")
    return None


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------

_PYTHON_HEAD = '''\
# The customer's own script, written by the execution suite (#582). It
# imports the rendered module and runs the rendered call-site blocks, pasted
# as rendered, with the values only the customer's code holds.
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

from ubb import UBBStopRequested

# Where the generated module's warnings go.
logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

RESPONSES = Path(__file__).resolve().parent / @RESPONSES@


def _as_object(value):
    """A Python library's response: its fields read as attributes."""
    if isinstance(value, dict):
        return SimpleNamespace(
            **{key: _as_object(item) for key, item in value.items()})
    if isinstance(value, list):
        return [_as_object(item) for item in value]
    return value


def _response(fixture, representation):
    """The supplier's response this code already holds."""
    document = json.loads(
        (RESPONSES / f"{fixture}.json").read_text(encoding="utf-8"))
    return _as_object(document) if representation == @PYTHON_OBJECT@ else document


def main():
'''

#: What the customer's process reports of a stop, read by name off the
#: acknowledgement `UBBStopRequested` carries, beside the key the event was
#: sent under: the event, the scope and the reason, and how the stop was
#: applied and what it was measured on (#569, carried by #585), whose values
#: `_scenarios._the_stop` asserts. A shell file's metadata is the variable it
#: sets, whole, so it needs no list.
STOP_METADATA = ("event_id", "stop_scope", "stop_reason", "trigger_source",
                 "stop_bound_micros", "stop_measured_micros")

_PYTHON_TAIL = f'''

try:
    main()
except UBBStopRequested as stop:
    # The process's own boundary: say what stopped it, and stop. Each field
    # by name, never through to_dict() (#596).
    print("stop_requested=" + json.dumps(
        {{"idempotency_key": stop.idempotency_key,
          **{{name: getattr(stop.result, name) for name in {STOP_METADATA!r}}}}},
        sort_keys=True), flush=True)
    raise
'''


def _python_value(artifact: Artifact, event_type, value: Value) -> str:
    if isinstance(value, Response):
        return (f"_response({value.fixture!r}, "
                f"{_representation(artifact, event_type)!r})")
    return repr(value)


def _python_assign(artifact, event_type, values) -> list[str]:
    return [f"{name} = {_python_value(artifact, event_type, value)}"
            for name, value in values.items()]


def _python_record(artifact, record: Record, handle: str,
                   customers) -> list[str]:
    return [f"task_id = {handle}.task_id",
            *_python_assign(artifact, record.event_type,
                            _resolved(record.values, customers)),
            *_lines(artifact.block(f"record_{tail(record.event_type)}.py"))]


def _python_close(artifact: Artifact) -> str:
    """The close block's line that declares the work delivered."""
    chosen = [line for line in _lines(artifact.block("close.py"))
              if line.strip() == "task.complete()"]
    if len(chosen) != 1:
        raise AssertionError(
            f"the close block offers no task.complete():\n"
            f"{artifact.block('close.py')}")
    return chosen[0]


def python_script(artifact: Artifact, work: Work,
                  customers: Mapping[str, str]) -> str:
    """The customer's Python for `work`."""
    body = ['print(f"task_id={task.task_id}", flush=True)']
    for part in work.does:
        if isinstance(part, Record):
            body += _python_record(artifact, part, "task", customers)
            continue
        inside = ['print(f"subtask_id={subtask.task_id}", flush=True)']
        for record in part.records:
            inside += _python_record(artifact, record, "subtask", customers)
        # The close block is written for the work's own handle; a Subtask's
        # is `subtask`, and the customer declares its end the same way.
        inside.append("subtask.complete()")
        body += [*_python_assign(artifact, None,
                                 _resolved(part.values, customers)),
                 *_fill(artifact.block(f"start_subtask_{tail(part.kind)}.py"),
                        "...", inside)]
    body.append(_python_close(artifact))

    run = _fill(artifact.block("stop.py"), "...",
                _fill(artifact.block("unit_of_work.py"), "...", body))
    start = _python_assign(artifact, None, _resolved(
        {"customer_id": CustomerId(work.customer), **work.values}, customers))
    head = (_PYTHON_HEAD.replace("@RESPONSES@", repr(CUSTOMER_RESPONSES))
            .replace("@PYTHON_OBJECT@", repr(PYTHON_OBJECT)))
    return (head
            + "\n".join(f"    {line}" if line else ""
                        for line in [*start, *run])
            + "\n" + _PYTHON_TAIL)


# ---------------------------------------------------------------------------
# Shell
# ---------------------------------------------------------------------------

_SHELL_HEAD = f'''\
# The customer's own script, written by the execution suite (#582). It
# sources the rendered file and runs the rendered call-site blocks, pasted
# as rendered, with the values only the customer's code holds.
. ./{ARTIFACT}/ubb_integration.sh
'''


def _shell_word(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _shell_value(value: Value) -> str:
    if isinstance(value, Response):
        return _shell_word(f"{CUSTOMER}/{CUSTOMER_RESPONSES}/{value.fixture}.json")
    return _shell_word(str(value))


def _shell_assign(values) -> list[str]:
    return [f"{name}={_shell_value(value)}" for name, value in values.items()]


def _shell_record(artifact, record: Record, handle: str,
                  customers) -> list[str]:
    return [f"task_id={handle}",
            *_shell_assign(_resolved(record.values, customers)),
            *_lines(artifact.block(f"ubb_record_{tail(record.event_type)}.sh"))]


def _shell_close(artifact: Artifact, handle: str) -> list[str]:
    return [f"task_id={handle}", f"outcome={_shell_word(DELIVERED)}",
            *_lines(artifact.block("close.sh"))]


def _shell_work(artifact: Artifact, work: Work, customers) -> list[str]:
    """`work()` from the run_task block, its placeholder filled, and
    nothing after its closing brace: the stop block runs it."""
    body = ['printf \'task_id=%s\\n\' "$task_id"']
    for part in work.does:
        if isinstance(part, Record):
            body += _shell_record(artifact, part, "$1", customers)
            continue
        body += [*_shell_assign(_resolved(part.values, customers)),
                 *_lines(artifact.block(
                     f"ubb_start_subtask_{tail(part.kind)}.sh")),
                 'printf \'subtask_id=%s\\n\' "$subtask_id"']
        for record in part.records:
            body += _shell_record(artifact, record, "$subtask_id", customers)
        body += _shell_close(artifact, "$subtask_id")
        body.append("task_id=$1")
    body += _shell_close(artifact, "$1")

    lines = _fill(artifact.block("run_task.sh"), ":", body)
    closing = [index for index, line in enumerate(lines) if line == "}"]
    if len(closing) != 1:
        raise AssertionError(f"expected one closing brace:\n{lines}")
    return lines[:closing[0] + 1]


def shell_script(artifact: Artifact, work: Work,
                 customers: Mapping[str, str]) -> str:
    """The customer's shell for `work`: the work, run by the stop block,
    whose status is passed on as the script's own."""
    start = _shell_assign(_resolved(
        {"customer_id": CustomerId(work.customer), **work.values}, customers))
    when_stopped = ['printf \'stop_requested=%s\\n\' "$UBB_STOP_REQUESTED"']
    return "\n".join([
        _SHELL_HEAD.rstrip("\n"),
        *start,
        *_shell_work(artifact, work, customers),
        *_fill(artifact.block("stop.sh"), ":", when_stopped),
        'printf \'status=%s\\n\' "$work_status"',
        'exit "$work_status"',
    ]) + "\n"
