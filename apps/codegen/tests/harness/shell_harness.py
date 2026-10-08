"""What the renderer's tests ask a shell about the files it returned.

The renderer is TypeScript and what it writes for this target is a POSIX shell
file that calls curl and jq, so "the file parses", "a stop returns 20" and
"the declared name reaches the wire unchanged" are questions only a shell with
those two tools can answer. Each command below answers one, over a directory
of files exactly as `render` returned them, and prints its answer as one JSON
document.

Nothing here repairs what it runs. The files are parsed, sourced and called as
a tenant would; the only things supplied from outside are the two documented
environment variables. Every path is relative to the directory the harness is
started in, which is the directory the files were written to — so the same
commands run on the machine itself and in a container that directory is
mounted into.

    python shell_harness.py syntax
    python shell_harness.py run           <plan.json>
    python shell_harness.py reported-cost <cases.json> <messages.json>
    python shell_harness.py response-cost <cases.json> <function> <representation> <currency> <messages.json>
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from harness import HARNESS_CREDENTIAL, Server, read_off_a_response

#: The shells a generated file is run under. `sh` is whatever the machine's
#: POSIX shell is — dash on the CI runner and in the test image — and `bash`
#: is the one most people type into.
SHELLS = ("sh", "bash")

MODULE = "ubb_integration.sh"


def _ran(arguments, environment, cwd="."):
    ran = subprocess.run(arguments, capture_output=True, env=environment,
                         cwd=cwd)
    return {"status": ran.returncode,
            "stdout": ran.stdout.decode("utf-8", "replace"),
            "stderr": ran.stderr.decode("utf-8", "replace")}


def syntax():
    """Each shell file, and the first reason a shell refuses to parse it."""
    answers = {}
    for path in sorted(Path(".").rglob("*.sh")):
        refusal = None
        for shell in SHELLS:
            parsed = _ran([shell, "-n", str(path)], dict(os.environ))
            if parsed["status"] != 0 and refusal is None:
                refusal = f"{shell}: {parsed['stderr'].strip()}"
        answers[path.as_posix()] = refusal
    return answers


def _environment(server, changes):
    """The environment a generated file is run in: the machine's own, the two
    documented variables, and whatever a test changes. `None` unsets one."""
    environment = dict(os.environ)
    environment["UBB_BASE_URL"] = server.url
    environment["UBB_API_KEY"] = HARNESS_CREDENTIAL
    for name, value in (changes or {}).items():
        if value is None:
            environment.pop(name, None)
        else:
            environment[name] = value
    return environment


def run(plan_path):
    """Run a test's script under one shell, against a local server standing
    where UBB would. The script sources the files itself, as a tenant does."""
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    server = Server()
    for answer in plan.get("answers", []):
        server.queue(answer["path"], **answer.get("answer", {}))
    script = Path("__script__.sh")
    script.write_bytes(plan["script"].encode("utf-8"))
    ran = _ran([plan.get("shell", "sh"), str(script)],
               _environment(server, plan.get("environment")))
    return {**ran, "requests": server.requests}


def reported_cost(cases_path, messages_path):
    """The generated conversion and the generated currency rule, run over
    every case the platform answered for an amount handed over as text.
    Returns the cases that disagree.

    A refusal is told apart from a conversion by its status, and a refusal
    about the currency from one about the amount by what it printed."""
    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    said = json.loads(Path(messages_path).read_text(encoding="utf-8"))
    environment = dict(os.environ)
    Path("__amount__.sh").write_bytes(
        b'. ./' + MODULE.encode() + b'\n'
        b'_ubb_to_micros "$1" "$2" "$3"\n'
        b'printf "%s %s\\n" "$?" "${_ubb_micros-}"\n')
    Path("__currency__.sh").write_bytes(
        b'. ./' + MODULE.encode() + b'\n'
        b'_ubb_pin_currency "$1" "$2"\n'
        b'printf "%s %s\\n" "$?" "${_ubb_currency-}"\n')

    def answered(script, shell, *arguments):
        ran = _ran([shell, script, *arguments], environment)
        status, _, value = ran["stdout"].strip().partition(" ")
        if status == "0":
            return value
        if status != str(said["refused_status"]):
            return {"unexpected": ran}
        about = any(message in ran["stderr"] for message in said["currency"])
        return {"refused": "currency" if about else "amount"}

    disagreements = []
    for shell in SHELLS:
        for case in cases["amounts"]:
            got = answered("__amount__.sh", shell, case["amount"]["text"],
                           case["representation"], case["currency"])
            if isinstance(got, str):
                # As text: a whole number of nineteen digits is not one every
                # reader of this answer could hold.
                expected = case["expected_as_text"].get("answer")
                agreed = expected is not None and got == str(expected)
            else:
                agreed = got == case["expected_as_text"]
            if not agreed:
                disagreements.append({"shell": shell, "case": case, "got": got})
        for case in cases["currencies"]:
            got = answered("__currency__.sh", shell, case["declared"],
                           case["reported"] or "")
            expected = case["expected"]
            agreed = (got == expected.get("answer") if isinstance(got, str)
                      else got == expected)
            if not agreed:
                disagreements.append({"shell": shell, "case": case, "got": got})
    return {"amounts": len(cases["amounts"]),
            "currencies": len(cases["currencies"]),
            "shells": list(SHELLS),
            "disagreements": disagreements}


def response_cost(cases_path, function, representation, currency,
                  messages_path):
    """A supplier's cost READ OFF A RESPONSE, run through the generated record
    function over every row the platform answered for `representation` in
    `currency` (#583), under every shell the harness has: each row's text is
    written to a file exactly as it is, the function is called with that
    file, a stand-in server answers, and what was sent — or why it refused,
    having sent nothing — is held to the platform's answer. Returns the rows
    that disagree."""
    rows = read_off_a_response(cases_path, representation, currency)
    said = json.loads(Path(messages_path).read_text(encoding="utf-8"))
    Path("__record__.sh").write_bytes(
        b'. ./' + MODULE.encode() + b'\n' + function.encode() +
        b' customer_id=c idempotency_key="$1" task_id=t'
        b' response=__response__.json\n')
    server = Server()
    environment = _environment(server, None)
    disagreements = []
    for shell in SHELLS:
        for index, row in enumerate(rows):
            Path("__response__.json").write_bytes(row["document"].encode("utf-8"))
            before = len(server.requests)
            ran = _ran([shell, "__record__.sh", f"e{index}"], environment)
            sent = server.requests[before:]
            if ran["status"] == 0 and len(sent) == 1:
                got = {"answer": sent[0]["body"].get("provider_response_cost_micros")}
                if "provider_cost_micros" in sent[0]["body"]:
                    got["on_the_callers_field"] = True
            elif ran["status"] == said["refused_status"]:
                about = ("response" if any(message in ran["stderr"]
                                           for message in said["response"])
                         else "currency" if any(message in ran["stderr"]
                                                for message in said["currency"])
                         else "amount")
                got = {"refused": about}
                if sent:
                    got["sent"] = True
            else:
                got = {"unexpected": ran}
            if got != row["expected"]:
                disagreements.append({"shell": shell, "row": row, "got": got})
    return {"rows": len(rows), "shells": list(SHELLS),
            "disagreements": disagreements}


COMMANDS = {"syntax": syntax, "run": run, "reported-cost": reported_cost,
            "response-cost": response_cost}

if __name__ == "__main__":
    answer = COMMANDS[sys.argv[1]](*sys.argv[2:])
    sys.stdout.buffer.write(json.dumps(answer, ensure_ascii=True).encode())
