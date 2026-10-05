# ADR-0017: A generated shell file is sourced, takes its values by name, and returns a stop as a status

**Status:** accepted
**Date:** 2026-10-02
**Decision records:** the consolidated Code Builder specification on #184 (four comments,
2026-09-25) — §6 the artifact, §7 the classes as shapes, §9 the runtime contract, §10 the Shell /
raw HTTP target · `docs/plans/2026-08-04-renderer-and-preview-decision.md` (#180 §1 to §3, and
§12.1, the question this closes) · the owner's rulings on PR #597 (ADR-0016 §9) · the owner's
review of PR #598 (2026-10-02), recorded in §10
**Companion:** ADR-0016 is the package this target is the second target of, and its §2, §3, §5,
§6 and §8 hold here unchanged; ADR-0015 is the document it renders; ADR-0008 §5 names the gates
(G23 to G26) this suite is the renderer's half of

## Context

ADR-0016 recorded `ubb-codegen` and its Python target, and left the shell target to this one
(#578). The specification settled what a shell file must do: run, with curl and jq; probe for what
it needs before it does anything; take its jq programs through a quoted heredoc; return a stop as
the reserved status 20 and never through a subshell; send only keys the contract publishes; hold
no host.

It left to the build how. Python gets its guarantees from the language: a required keyword
parameter, a `BaseException` no catch-all swallows, a `Decimal`, an SDK that knows the routes.
Shell has none of them, and a tenant's generated file is sourced into a script UBB never sees. So
each guarantee had to be given a shape here, and each shape is a name or a status a tenant's
script depends on from the day it ships (ADR-0007 §3).

## Decision

### 1. The runnable file is POSIX shell, written to be sourced, and it owns nothing of the shell it is sourced into

`ubb_integration.sh` is sourced: `. ./ubb_integration.sh`. It is the POSIX shell language and
nothing a particular shell adds, and the only programs it runs are `jq` and `curl`. Everything
else it uses — `printf`, `[`, `command` — is the shell's own in every shell it was run under, and
the suite runs it with nothing but those two on `PATH`. That is what "requires curl, jq" means.

It **sets no shell option, never calls `exit`, and holds no variable that is not spelled `UBB_…`
or `_ubb_…`**. Sourcing it defines functions and assigns constants and does nothing else: no
tool is looked for, nothing is read from the environment, nothing is sent. A tenant's `set -e` or
`set -u` is theirs, and the file behaves the same with either or neither, because every status is
tested where it is produced and every variable is assigned before it is read. The call-site
blocks hold to the same: none of them has a line a shell option decides whether is reached.

**Preflight is lazy, and probes capability.** The first thing a call does is check, once, that jq
is present and can run this file's own programs, and that curl is present and has
`--fail-with-body`. A probe runs the construct the file is about to use and reads no version
string. **Preflight succeeds if and only if this jq can run this file's programs** (owner's review
of #602): the jq probe is derived from the file's programs as rendered — it passes each option they
pass, uses each keyword form they use, and names each function they call inside a branch that is
never taken, so jq must resolve every one to compile the probe and runs none — and asks for nothing
else. The options, forms and functions it knows are one closed table (`src/shell/probe.ts`): a
program asking jq for anything outside it refuses to render. The probe contacts nothing, creates
nothing, and no declared name reaches it; what differs between two files' probes is only which
entries of that table their programs use. A call that is NOT READY refuses before preflight, so a
scaffold says what is missing on a machine with neither tool.

*Amended by #582.* The probe first asked only for a program from standard input that holds
comments, and was the same for every file. jq 1.3 and 1.4 do both and have no `--argjson` or
`--slurpfile` (both arrived in 1.5), so on them the file passed preflight, started a unit of work,
and failed at its first program with a status that blamed the value. A pinned image of jq 1.4, run
against the real application (`tests/code_builder_execution/`), found it. The probe is now derived
as above. Run against jq 1.3, 1.4, 1.5 and 1.7.1, gojq and jaq for all twenty committed shell
files, its verdict matched whether that jq could compile the file's programs every time — gojq, for
one, runs every runnable file but has no `keys_unsorted`, which only the verify script uses, and is
refused there alone. The refusal names jq 1.5 or later as the version that runs every file the
renderer writes, and a lifecycle is run on jq 1.5.

The verify script is the one file that is run and not sourced, so it ends with `exit`. It needs
jq and not curl.

### 2. A value goes in by name, and comes out in a variable

**A runtime value is a `name=value` argument**, under exactly the name the Blueprint gives:

```
ubb_record_chat_completion customer_id="$customer_id" idempotency_key="$key" \
  task_id="$task_id" response=response.json searches=2
```

Positional arguments were rejected: a call with five of them is five chances to pass one in the
place of another, and nothing would say so. Environment variables, which the prototype used, were
rejected too: they make a function's inputs a property of the whole process.

One left out, **or passed empty**, is refused with `UBB_EXIT_USAGE` before anything is sent,
naming it. Empty counts because that is what a missing value is in shell: an unset variable
expands to nothing. One the call does not have is refused the same way, and only its name is
printed.

**A parameter's name is used exactly as given, and the runnable file never has a variable of
that name.** It is `_ubb_p_<name>` in shell and `$p_<name>` in jq. So a quantity coded `PATH`,
`IFS`, `status` or `then` gives a parameter of that name that is none of the things the word
already means to a shell or to jq: there is no list of reserved words to keep, because no declared
name is ever in a position where one would matter. A call-site block does READ a variable of the
parameter's name — `searches="$searches"` — since that variable is the tenant's own to hold the
value in; it assigns none.

**The name is the Blueprint's, and never assumed to be the name of the field it fills.** The
boundary knows a Task's outcome was declared by whatever the close's parameter for the Task is
called, and a Subtask block passes the work's id under whatever the parent's parameter is called.

**What a call leaves behind is in a variable**, because a function returns a status and nothing
else. There are three, and they are results the file sets, not settings a tenant supplies:

- **`UBB_TASK_ID`** is the id of the work the last start created.
- **`UBB_RESPONSE`** is the response to the most recent call, and the next call overwrites it.
- **`UBB_STOP_REQUESTED`** is the stop the most recent record met, or the Task `ubb_run_task`
  ran: the stop's metadata as one line of JSON (§4), not a flag. It is empty where none was met.
  **Every call that can return a stop — a record, and `ubb_run_task` — clears it before it does
  anything else**, before a refusal and before preflight, so what it holds is never an earlier
  call's: a call that was refused met no stop and says none. A start that succeeds clears it too:
  a new Task has no stop of the last one's.

**None of them is exported.** They are the shell's and not the environment's: a child process
does not see them, and nothing a tenant runs inherits a stop it did not meet.

That is why a tenant never calls a function of the file inside `$( )` or a pipeline — both run
it in a subshell, where what it set is lost — and why the file never does so either: the only
functions it runs there are the ones that set nothing (§3).

**How a value is passed to jq is decided by a declared fact** (ADR-0016 §3, extended by one). A
shell argument is always text, so: a keyed entry that declares a `value_type` is a number, checked
as a whole number of at most fifteen digits and carried exactly or refused; one that declares a
`source_path` is the path of a FILE holding the supplier's JSON response, and what is read off it
is held to the same: a whole number, or nothing is sent; a field that declares an
`amount_representation` is a cost (§6); everything else is a JSON string.

The names a call site depends on are `ubb_start_task`, `ubb_run_task`, `ubb_close_task`,
`ubb_start_subtask_<name>` and `ubb_record_<name>`, with `<name>` and the collision rule exactly
ADR-0016 §2's — one rule for both targets, in `src/names.ts`. The three fixed ones are named for
the Task, the domain's own noun for what they start, run and close.

### 3. A jq program is read by jq from standard input, from a quoted heredoc that is never inside a substitution

#180 §12.1 left two forms open and asked for both to be run:

```
jq … --from-file /dev/stdin <<'UBB_JQ'        the program on standard input
jq … "$(cat <<'UBB_JQ' … UBB_JQ)"             the program as an argument
```

**Both were run**, over an apostrophe, a dollar sign, command-like text, a backtick, a backslash,
characters outside ASCII, a hyphen, a space, an unbalanced parenthesis and the delimiter itself,
as keys written into the program and as values handed to it. On dash, bash 5.2, zsh and busybox
ash (and bash 4.4, in a probe), with jq 1.6, 1.7, 1.7.1 and 1.8.2, both carry every name
unchanged, expand nothing and run nothing.

**bash 3.2 separates them, and it is not a museum piece: it is what macOS ships as `bash` and as
`sh`.** It reads the text of a heredoc that sits inside a command substitution as shell, and one
backtick in a declared name is enough:

```
bad substitution: no closing `)' in "$(cat <<'UBB_JQ'
```

A program handed to jq as an argument is inside a command substitution by construction, so the
second form cannot be written safely for that shell at all. **The first is chosen.** It needs
`/dev/stdin`, which is exactly what preflight probes.

**And the same evidence decides where the chosen form may sit.** Capturing jq's output in place —
`body=$(jq … <<'UBB_JQ' … )` — puts the heredoc inside a substitution again and fails on bash 3.2
the same way. So **every program is a function of its own that is nothing else** (`_ubb_jq_…`):
one jq command with its program on standard input. What is captured is that function's output,
and the heredoc sits where every shell reads it as text. No heredoc is ever opened inside `$( )`.

The second form is kept as a committed script beside the first, over the same names, with the
bash 3.2 transcript at its head. The suite runs both under `sh` and `bash` on every run, so the
comparison is executed where both parse and recorded where one does not.

**A declared name reaches a file in two places, with one encoder each.** In a jq program it is a
jq string literal, which is a JSON string: the JSON encoder is the jq encoder, and since it escapes
the backslash no name can open jq's `\(…)` interpolation. Every key of an object is a quoted
string and never a bare word. In shell code it is a single-quoted word, used only where a name is
printed.

**No line of a program can be the line that ends it.** Every line of a heredoc's body is
indented and the delimiter is not, and every character that could end a line is escaped before a
name is written. That is structure, not a rule a later edit must remember: a key that IS the
delimiter, and one that holds it on a line of its own, both render and run.

Runtime values reach a program only as `--arg`, `--argjson` or `--slurpfile`. A response is handed
to the program that reads it the same way, as an argument, which is also what gives a malformed or
an empty response one failure whichever jq reads it: read as jq's input, the two fail differently
on jq 1.6 and 1.7, and an empty one does not fail on 1.6 at all.

### 4. A stop is a status, set in the caller's shell, and every other failure is another status

A stop arrives on a successful response. The record that is answered with one leaves the stop's
metadata in `UBB_STOP_REQUESTED` and returns `UBB_EXIT_STOP_REQUESTED`, which is 20. The literal
is written once, as the value of that constant.

**The metadata is one line of JSON**, an object of the fields the acknowledgement and the request
publish today under their own names: `event_id`, `idempotency_key`, `stop_scope`, `stop_reason`.
The key is the one the event was sent under, which the acknowledgement does not repeat. A
task-scoped and a customer-scoped stop share the status and differ here. The fields #569 will
publish are added to that object by #585; nothing is derived or filled in.

**`ubb_run_task` is the boundary.** It starts the Task, runs the one command it is given with
the Task's id as its argument, and then reads three things: the status that command returned,
whether a stop was met while it ran, and whether the Task's outcome was declared.

- **20, or a stop was met**: it logs the stop — one sentence, then `stop_requested` and the
  metadata — declares nothing, and returns 20. It never turns a stop into success or into a
  failure, and that does not rest on the tenant: work that never looked at the status its record
  returned, went on and returned success is still answered with 20. The metadata it leaves in
  `UBB_STOP_REQUESTED` is the stop its Task met, whatever a later record inside the work left
  there.
- **a failure, with no outcome declared**: it **declares nothing**. The status is returned
  exactly as the work returned it, the Task is left open, and one line on standard error says
  both: no outcome was declared for it, and the Task is open. A status above 128, a signal's, is
  the same case and is passed on the same way.
- **success, with no outcome declared**: it leaves the Task open and returns `UBB_EXIT_USAGE`,
  saying so. It does not guess an outcome, and it does not stay quiet.
- **an outcome was declared**: the work's status is returned as it is, and nothing is said.

**The file writes no terminal outcome of its own.** `ubb_close_task outcome=failed …`, called by
the tenant, is the one way a failure is declared, and the only close a generated file sends is one
a tenant's script called. The rule behind it is the owner's (§10): UBB writes a terminal business
outcome only where it has unambiguous evidence for it, and **a shell status is not that**. A
function whose last command is a test that came out false returns a failure nobody meant; a
`grep` that found nothing returns 1; and a Task declared `failed` cannot be reopened. So #184
§9's rule for the SDK's wrapper — an exception leaving the block is evidence, and declares
`failed` — is **not** carried over to this target. The Python target keeps it: an exception is
evidence a status is not.

**Nothing on the stop's path is ever run in a subshell.** What the file runs inside `$( )` is a
program function (§3) or the credential piped to curl, and nothing else; no function is ever in a
pipeline. A program function sets nothing and returns jq's status, so there is nothing of it for
a subshell to lose: the function that reads an acknowledgement captures the program's output and
then, itself called as a plain command, sets the metadata and returns 20. So what a function set
is still there for its caller, and its status is the one the caller sees.

**`set -e` is not the mechanism.** Every status is tested where it is produced. The boundary runs
the tenant's command on the left of `&&`, where a shell ignores `set -e` for everything inside
it, and the call-site block says so: inside the work, each call's status is checked by hand. The
block that acts on a stop takes the status of the work the same way, so the line that reads it is
reached with `set -e` on.

**Every other failure of the file's own is a named constant too**, each the `sysexits.h` value
for what it is: `UBB_EXIT_USAGE` (64, a parameter left out, empty or not the call's, or work that
ended without saying how), `UBB_EXIT_VALUE_REFUSED` (65, a value that was passed and cannot be
used: a quantity, a cost, a response that does not hold what a declared path reads, a value that
would move a route), `UBB_EXIT_TOOL_UNAVAILABLE` (69), `UBB_EXIT_RESPONSE_UNREADABLE` (76) and
`UBB_EXIT_NOT_CONFIGURED` (78). The file gives none of them a second meaning. A request that
fails returns the status CURL gave it, with the body the API answered printed, and curl's own
statuses are curl's: one may be the same number as one of these. **What no failure can be is
20**: a request that failed with that very status is returned as 1.

### 5. There is no SDK, so the wire is the renderer's, and it is typed against the contract

What the Python target leaves to the SDK is this renderer's knowledge here:

- **The route of each operation a Blueprint names**, in `src/shell/plan.ts`. Each is typed against
  the committed contract: a route the contract no longer publishes for that operation stops
  compiling.
- **Which token is not a key of the body.** A one-segment token named for a place in the route —
  `task_id` in `/api/v1/tasks/{task_id}/close` — fills that place. It must be a value that needs
  no encoding there and is not a dot segment, which curl would resolve into another route, or the
  call is refused.
- **The two fields a close may carry beside its outcome**, `outcome_reason` and `reason_detail`.
  They are parameters a call may leave out, and are sent only where given.
- **The credential's header.** The key is handed to curl on standard input and is never a word of
  its command line, where another process could list it.

**Only keys the operation's request publishes are sent.** The server drops an unpublished key and
answers 200, and there is no SDK here to refuse one first. So the suite runs every complete
branch the way its own call-site blocks say to and checks every key of every body that arrived
against `openapi/v1.json`. That is the test G23 arms.

### 6. A supplier's cost is converted on its digits, and is never a number in jq or in shell

jq holds a number as a double: 9223372036854775807 handed to jq 1.6 as `--argjson` comes back as
9223372036854776000. Shell arithmetic is a machine integer that wraps. So neither does the
conversion.

**The amount is text, and stays text.** Its sign, digits, point and exponent are read off it;
the point is moved by the declared representation's power of ten; an amount that would leave a
digit behind the point is refused; the result is compared with the largest a money column holds
digit group by digit group. The only arithmetic is on the exponent and on a count of places. The
result is written into the body by the shell, as its digits: it never becomes a jq number.

**That is the one value that reaches a body other than as an argument of jq**, and it is a
deliberate departure from #184 §10's "runtime values always go through `--arg`, `--argjson` or a
file". What is written is not the caller's text but the converter's output, which is digits and
an optional sign and nothing else.

The conversion answers what the platform's does, which is more than the request admits: the
contract bounds `provider_cost_micros` at zero and at twelve digits, and a negative cost or a
larger one is converted here and refused by the API.

Every multiplier is a power of ten, which is what makes moving the point enough. A currency that
broke that is refused at render.

**It is held to the platform's own table, case for case**, as the Python target's is — with one
difference that is the platform's to state and not this renderer's. A shell argument has no type:
a decimal, an integer and a float of the same digits are one argument. So each case of the table
carries a second answer, written by the platform, for the amount handed over AS ITS TEXT. The two
answers differ for a binary float and for nothing else: the float is refused, and its text is the
decimal it spells. **A shell caller's float is its text.** The danger a float carries in Python is
here upstream of the file, in whatever produced the text, and the file's comment says so: pass the
amount as the supplier wrote it, since a number another tool has parsed may already be rounded.

Two known differences from the platform's reader, both outside the table and both refusals: it
accepts the decimal digits of every script and the shell reads ASCII digits only, and it strips
every character Unicode calls a space where the shell strips the ones POSIX does.

The currency-disagreement proof is the helper's, as ADR-0016 §4 records for Python and for the
same reason. #583 owes the case through the artifact.

### 7. A request preview is documentation

One `request_preview` file a call: the method, the URL, the headers and the body, written from the
same plan the runnable file is, in the same shapes — a literal as itself, a runtime value as
`$name`, the credential as `$UBB_API_KEY`, where the API is as `$UBB_BASE_URL`. It is not run,
defines nothing, and **carries no readiness verdict**: the header of the runnable file is where
the verdict is stated, and a preview says of itself that it is not that file. A value with nothing
configured to supply it is shown in the shape it has in the file, which is not a verdict on the
call.

One a call and not one file, because the page that shows them (#579) shows a call at a time.

### 8. What is refused

Everything ADR-0016 §7 lists that is not about an SDK, and:

- no close of the work, or more than one;
- a route with a place no token fills;
- a record that names no key its event is sent under;
- one parameter asked for as two kinds of value;
- a parameter name that is not an identifier.

**A shell Blueprint is not asked for an SDK major**, and the header states whatever the document
says, which is null.

### 9. Where the shell is run

The suite runs what it renders, with no skip (ADR-0016's rule). Every shell file is parsed by
`sh` and by `bash`, and the lifecycle, the stop and the conversion are run under both.

**In CI, by the runner's own tools.** The `codegen` job checks for `sh`, `bash`, `curl` and `jq`
by name before the tests, so a runner image that stopped carrying one fails there and says which.

**Neither of those is bash 3.2, which is where §3 was decided.** The whole shell suite was run
once, by hand, in four more images: Ubuntu 24.04 (the runner's own dash, bash 5.2, jq 1.7 and
curl 8.5), Alpine (busybox ash, jq 1.7.1), bash 3.2.57 with jq 1.8.2, and zsh 5.9 standing where
the suite asks for `bash`. All of it passes in each, but for the one case that IS the evidence:
under bash 3.2 the form decided against fails as §3 records. What holds the rule on every run is
structural, and needs no old shell: no heredoc is opened inside a substitution. A standing matrix
of shells is #582's.

**On a machine without them, in a container.** `UBB_CODEGEN_SHELL_IMAGE` names an image and the
same harness runs inside it, with the files mounted. This exists for Windows: a Git Bash with a
native `jq.exe` is not an environment a generated file is ever run in, and what it would prove is
about that pairing. The image the package builds is Debian stable (dash, bash 5.2, jq 1.6,
curl 7.88) and the runner is Ubuntu (jq 1.7, curl 8), so between them the suite sees two
generations of each tool.

### 10. What the owner ruled, and what this ADR does not decide

**The owner reviewed PR #598 on 2026-10-02 and ruled on what this ADR had left to them.** As
built, the boundary declared work that returned a failure `failed`, and the outer function was
`ubb_unit_of_work`. Both were changed before the merge, so neither ever shipped.

1. **No outcome is fabricated from a status.** A work function's non-zero status does not make a
   Task `failed`. The status is passed on unchanged, a Task with no outcome declared is left open
   and said to be, a signal's status is passed on the same way, and a stop is never turned into a
   failure. An explicit `ubb_close_task outcome=failed …` is how an integration declares one. The
   invariant kept is the stronger one: UBB writes a terminal business outcome only on
   unambiguous evidence (§4).
2. **The five statuses of §4 and their values are approved**, beside `UBB_EXIT_STOP_REQUESTED`,
   which stays 20. A caller, and everything this renderer writes, uses the names and not the
   numbers: the literal 20 is written once, as that constant's value.
3. **The three result variables are approved, with the lifecycle §2 states**: results the file
   sets and not settings, `UBB_RESPONSE` overwritten by the next call, `UBB_STOP_REQUESTED` the
   stop's metadata and not a flag, cleared before a stop-capable call does anything, and none of
   them exported.
4. **`ubb_start_task` and `ubb_close_task` are approved, and the outer function is
   `ubb_run_task`.** "Unit of work" is not a noun a tenant is given anywhere else; a Task is.
5. **The heredoc decision of §3 is approved, and is not to be simplified later** because a newer
   shell tolerates another form: programs in functions of their own, no heredoc inside a
   substitution, and both the losing form's reproduction and the structural test kept.
6. **Approved as built**: `name=value` arguments and refusal before any side effect, the cost
   converted on its text, a response as a file, one preview a call, no host, no curl timeout the
   renderer made up, and catalogue version 2 (version 3 since #582, which reworded the refusal of
   an old jq — see the amendment to §1).

**A path for work that has already happened is not rendered, and that is a stated limitation of
this target in v1** (ruling 6), not something a shell file is implied to do. The Python target has
`backfill_<name>`, which passes the SDK's `stop_behavior="return"`. The specification gives the
shell target no batch path and says nothing of a backfill, and one would need two things nobody
has ruled: the parameter that says when the work happened, and what a stop does to the status of
a call that must not interrupt a backlog. **A tenant with a backlog to record uses the Python
target.** A shell path can be added without breaking a file already generated.

The fields #569 will publish in a stop's metadata (#585). Execution against the real application,
and images that really lack a tool or carry an old one, are #582's and are in
`tests/code_builder_execution/`, with the standing matrix of shells. A cost read off a supplier's
response, a constant's value and a missing agreed price (#583, #584, #586): each arrives as tokens
and needs no new rule here.

## What proves it

| Rule | Test |
|---|---|
| §1 — never exits, sets no option, holds no variable of another spelling | `apps/codegen/tests/shell.artifact.test.ts` — "never exits the shell that sources it, and sets none of its options", "holds no variable of its own that is not spelled UBB_ or _ubb_" |
| §1 — the same under `sh` and `bash`, with `set -eu` or without | `apps/codegen/tests/shell.execution.test.ts` — "runs the same under %s, with set -eu or without" |
| §1 — preflight refuses before any request, holds nothing of the tenant's, and sourcing does nothing | same module — "refuses before any request where %s", "probes with nothing of the tenant's, and creates nothing", "does nothing when the file is sourced, and never ends the shell that sourced it" |
| §1 — the jq probe asks for exactly what the file's own programs ask of jq, and a program asking for what no probe knows refuses to render | same module — "probes for exactly what the file's own programs ask of jq, and no more", "refuses to render a program that asks jq for what no probe knows" |
| §1 — on machines that really lack jq or curl, or carry a jq or a curl too old, the file is refused before any request, unit of work or temporary file, against the real application | `tests/code_builder_execution/test_preflight_refuses_before_any_request.py::test_a_machine_without_a_tool_it_needs_is_refused_before_any_request` |
| §2 — every runtime value a `name=value` parameter at its own call; left out, empty or not the call's is refused | `apps/codegen/tests/shell.artifact.test.ts` — "asks for every runtime value as a name=value parameter, at the call it is declared for"; `apps/codegen/tests/shell.execution.test.ts` — "refuses, naming it, a runtime value left out, passed empty, or not the call's" |
| §2 — no declared name is a name the shell, jq or the file already has | `apps/codegen/tests/shell.artifact.test.ts` — "gives a parameter no name the shell or jq could already have a meaning for"; `apps/codegen/tests/shell.execution.test.ts` — "can never stand in front of a name the shell, jq or the file already has: %s" |
| §2 — a quantity is a whole number carried exactly, or refused, passed in or read off a response | `apps/codegen/tests/shell.execution.test.ts` — "refuses a quantity that is not a whole number it can carry exactly", "refuses to record from a response that does not hold what a declared path reads" |
| §3 — both forms carry every kind of name; the chosen one is the one rendered | `apps/codegen/tests/shell.execution.test.ts` — "%s, a program carries every kind of name unchanged, expands nothing and runs nothing (%s)", "differ in one thing: only the form decided against opens a heredoc inside a substitution", "is settled the way the rendered file is written" |
| §3 — every program in a quoted heredoc no line of which could end it; every value an argument; every key quoted | `apps/codegen/tests/shell.artifact.test.ts` — "holds every jq program in a quoted heredoc, no line of which could end it", "passes every runtime value to jq as an argument, and quotes every key" |
| §3 — a name cannot end a heredoc, a string or a line, or run anything | `apps/codegen/tests/shell.execution.test.ts` — "cannot end a heredoc, a string or a line, or run anything: %s", "reach the wire exactly as they were declared" |
| §4 — a stop returns the reserved status with its metadata; two scopes share it | `apps/codegen/tests/shell.execution.test.ts` — "returns the reserved status with its metadata set, the event recorded once (%s)", "shares one status between a task-scoped and a customer-scoped stop, told apart by metadata" |
| §4 — the boundary logs and returns it, never as success, whether or not the work returned it | same module — "is observed by the boundary, logged, and returned — never as success", "is still a stop where the work never looked at the status that carried it" |
| §4, §10 — no outcome is declared from a status: the status is passed on, the Task left open and said to be; a declared failure is still sent | same module — "declares nothing for work that returned %s: the status is passed on and the Task left open, said so", "does not take a work function's last test coming out false for a failed Task", "still sends the failure a tenant declares, as the tenant declared it", "leaves work that ended cleanly without an outcome open, and says so", "declares nothing more for work that declared its own outcome"; `apps/codegen/tests/shell.artifact.test.ts` — "declares no outcome of its own: the only close is the one a tenant calls"; `apps/codegen/tests/catalogue.test.ts` — "names every outcome a close may declare as the registry does, and holds none to declare itself" |
| §2, §10 — the result variables: a stop is never a stale one, the runner's is its Task's, the response is the last call's, none is exported | `apps/codegen/tests/shell.execution.test.ts` — "clears an earlier call's stop before a record does anything, so a stop is never a stale one", "clears an earlier stop before ubb_run_task does anything, a run that is refused among them", "answers ubb_run_task with the stop its Task met, whatever a later record left behind", "starts a new piece of work with no stop of an earlier one's", "overwrites the response with each call's own", "sets its results in the shell and exports none of them to a child process"; `apps/codegen/tests/shell.artifact.test.ts` — "exports none of what it sets: the result variables are the shell's, not the environment's" |
| §2, §10 — the three fixed functions are named for the Task | `apps/codegen/tests/catalogue.test.ts` — "name the three fixed functions for the Task, the domain's own noun, and no other" |
| §1, §4 — the block that acts on a stop is reached under `set -e` | same module — "is acted on by the stop block as rendered, under set -eu, and the script goes on (%s)" |
| §2 — a call is written by the Blueprint's parameter names, not its fields' | `apps/codegen/tests/shell.artifact.test.ts` — "writes a call by the names the Blueprint gives its parameters, not by its fields' names" |
| §5 — a value cannot move the route it is written into | `apps/codegen/tests/shell.execution.test.ts` — "refuses a value that would change the route it is written into" |
| §3, §4 — nothing in a subshell but a program function and curl, and no heredoc in one; the literal once | `apps/codegen/tests/shell.artifact.test.ts` — "runs nothing in a subshell but a jq program and curl, and opens no heredoc in one", "emits the reserved status through its one constant, and the literal once" |
| §4 — an ordinary failure keeps its own status and is never taken for a stop | `apps/codegen/tests/shell.execution.test.ts` — "keeps %s its own status, with the body it was answered", "never lets a failure be taken for a stop, whatever status it failed with", "refuses an acknowledgement that %s, as neither success nor a stop" |
| §4 — the statuses stand clear of each other and of 20 | `apps/codegen/tests/catalogue.test.ts` — "keep the stop's status clear of every other status a shell file returns" |
| §5 — each request is the operation the Blueprint names, at the contract's route | `apps/codegen/tests/shell.execution.test.ts` — "starts, records and closes through the operations the Blueprint names" |
| §5 — only published keys are sent, by every complete branch, run | same module — "sends only keys the operation's request publishes: %s, run as its own blocks say", "reads these branches' published keys off a contract that has some" |
| §5 — the credential is curl's standard input and is written nowhere | `apps/codegen/tests/shell.artifact.test.ts` — "reads the credential from the environment, hands it to curl on standard input, and writes it nowhere" |
| §6 — the conversion is the platform's, case for case, on text | `apps/codegen/tests/shell.execution.test.ts` — "is converted exactly as the platform converts its text, case for case, under sh and bash", "does no arithmetic on the amount: nothing in the file could round it", "goes on the wire as whole micros, every digit of it, with the declared currency"; `ubb-platform/api/v1/tests/test_the_renderers_fixtures_are_what_the_platform_answers.py` — `test_the_reported_cost_cases_carry_this_platforms_answers`, `test_an_amount_as_text_is_answered_differently_only_where_the_type_was_why` |
| §7 — a preview carries no verdict and the header does | `apps/codegen/tests/shell.artifact.test.ts` — "carries no readiness verdict, and the header of the runnable file does", "is not the runnable file: it defines nothing and runs nothing" |
| §8 — what is refused | `apps/codegen/tests/shell.artifact.test.ts` — "refuses %s rather than writing a file that is wrong", "does not ask a shell Blueprint for an SDK major, and states the one it is given" |
| §9 — the tools are checked for in CI before the tests, and no setting takes the tests off the runner | `tests/contracts/test_the_renderer_suite_is_enforced.py` — `test_ci_runs_the_renderers_suite_and_can_fail_on_it`, `test_the_shell_tests_have_no_way_to_pass_without_a_shell` |
| ADR-0016 §5, for this target — every shell Blueprint is what the route answers, one a branch | `ubb-platform/api/v1/tests/test_the_renderers_fixtures_are_what_the_platform_answers.py` — `test_a_committed_blueprint_is_what_the_route_answers`, `test_every_branch_is_committed_for_both_targets` |

## Consequences

- **The names and the statuses are a contract with code UBB never sees.** Renaming a function, a
  variable a call leaves its answer in, or a parameter, or moving a status, breaks a tenant's
  script. Each is a new renderer contract and is announced as one.
- **A tenant's script checks statuses by hand inside the work.** That is the price of a stop that
  cannot be swallowed by a subshell or lost to `set -e`, and the call-site block says it.
- **A Task whose work fails without declaring an outcome stays open**, where the Python target
  would have declared it `failed`. That is deliberate (§4): an open Task can still be closed
  correctly, and a wrongly failed one cannot be reopened. The file says so on standard error
  every time it happens.
- **A response is a file, and a cost is text.** Both are what a shell script already has after it
  called its supplier with curl.
- **The catalogue is one for both targets, and it is version 2.** A Python file's header says so
  too, though nothing a Python file says changed.
- **The suite needs a shell with curl and jq, or a container.** There is no skip.
- **A quantity above fifteen digits, and a figure in another script's digits, are refused** where
  the platform would take them. Both are refusals, not wrong answers.
- **A file generated today has no path for work that has already happened** (§10).
