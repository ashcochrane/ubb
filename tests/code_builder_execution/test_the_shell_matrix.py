"""The standing matrix of shells, and the one case in it that must fail
(#582; ADR-0017 §3 left the matrix to this suite).

The generated shell file runs under every shell in `_scenarios.MATRIX` — dash,
bash 5.2, bash 3.2 (what macOS ships as `bash` and as `sh`) and dash with the
oldest jq the file runs with — and the lifecycle and both stop scenarios run
in each, against the real application (`test_every_scenario_runs_unmodified`);
every other shell scenario runs under dash and bash.

What decided how the file hands jq its programs is kept as two scripts in the
renderer's harness: the form it writes (a heredoc on jq's standard input) and
the form it decided against (a heredoc inside a command substitution). Both
carry every kind of declared name on every shell but one: bash 3.2 reads a
heredoc inside `$( )` as shell, and one backtick in a name ends it. So across
the whole matrix exactly one of these runs fails, and it is that one.
"""
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from _harness import REPO_ROOT, Ran, Server, in_image, render
from _scenarios import MATRIX

EVIDENCE = REPO_ROOT / "apps" / "codegen" / "tests" / "harness"
CHOSEN = "heredoc_from_standard_input"
DECIDED_AGAINST = "heredoc_as_an_argument"

#: The one shell that reads a heredoc inside a substitution as shell.
BASH_3_2 = "bash@bash-3.2"

#: Every name the two scripts carry, as each declares it.
CARRIED = {
    "it's": "it's",
    "$HOME": "$HOME",
    "$(touch made-by-a-name)": "$(touch made-by-a-name)",
    "back`tick": "back`tick",
    "back\\slash\\n": "back\\slash\\n",
    "naïve–日本語": "naïve–日本語",
    "cache-read": "cache-read",
    "cache read tokens": "cache read tokens",
    "unbalanced)": "unbalanced)",
    "UBB_JQ": "UBB_JQ",
}


def _run(form, shell, directory) -> Ran:
    ran = subprocess.run(
        in_image(shell.image, shell.command, f"/evidence/{form}.sh",
                 work=directory, volumes={EVIDENCE: "/evidence:ro"}),
        capture_output=True)
    return Ran(status=ran.returncode,
               stdout=ran.stdout.decode("utf-8"),
               stderr=ran.stderr.decode("utf-8", "replace"))


@pytest.mark.parametrize("shell", MATRIX, ids=[shell.name for shell in MATRIX])
@pytest.mark.parametrize("form", [CHOSEN, DECIDED_AGAINST])
def test_only_bash_3_2_fails_and_only_the_form_decided_against(
        form, shell, tmp_path):
    ran = _run(form, shell, tmp_path)

    if (form, shell.name) == (DECIDED_AGAINST, BASH_3_2):
        assert ran.status != 0, ran
        assert "bad substitution" in ran.stderr, ran
        assert "carried" not in ran.said, ran
    else:
        assert (ran.status, ran.stderr) == (0, ""), ran
        assert json.loads(ran.said["carried"]) == CARRIED
        assert ran.said["ran_anything"] == "no", ran
    # Whichever way it went, no declared name ran as a command.
    assert not (tmp_path / "made-by-a-name").exists()


def test_the_matrix_holds_the_shell_that_decided_it():
    """Vacuity guard: without bash 3.2 in the matrix the case above that
    must fail is never run."""
    assert BASH_3_2 in [shell.name for shell in MATRIX]


# ---------------------------------------------------------------------------
# A stop's figures, on every jq the matrix carries (#585; ADR-0017 §6)
# ---------------------------------------------------------------------------
#
# The bound and the amount measured against it are signed 64-bit amounts of
# micros, and jq 1.5 and 1.6 hold a number as a double, so the file carries
# each one as the digits UBB wrote. The real application never writes figures
# at these extremes, so here a stand-in answers the record with them, as
# text: a hard floor at the most negative amounts a money column holds, and a
# grouping value that spells a stop field inside a string, which must never
# be read for one. The record is the file's own public call, as rendered from
# a committed Blueprint, and the stop is what it leaves in UBB_STOP_REQUESTED.

#: The committed shell Blueprint whose record call is run.
BLUEPRINT = (REPO_ROOT / "apps" / "codegen" / "fixtures" / "blueprints"
             / "shell-direct-task-events.json")
ACKNOWLEDGEMENT = (
    '{"event_id": "e9", "stop": true, "stop_scope": "customer", '
    '"stop_reason": "hard_floor", "trigger_source": "usage_ingest", '
    '"stop_bound_micros": -9223372036854775807, '
    '"stop_measured_micros": -9223372036854775808, '
    '"grouping_fields": {"note": "\\"stop_bound_micros\\": 1, \\\\\\" ,"}}')
#: The metadata, byte for byte: the figures as written, never rounded.
CARRIED_STOP = (
    '{"event_id":"e9","idempotency_key":"call-1","stop_scope":"customer",'
    '"stop_reason":"hard_floor","trigger_source":"usage_ingest",'
    '"stop_bound_micros":-9223372036854775807,'
    '"stop_measured_micros":-9223372036854775808}')


@pytest.fixture
def stand_in():
    """A local server standing where UBB would, answering every POST with
    `ACKNOWLEDGEMENT` exactly as written."""

    class Answers(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            body = ACKNOWLEDGEMENT.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *arguments):
            pass

    http = HTTPServer(("127.0.0.1", 0), Answers)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    try:
        yield Server(url=f"http://127.0.0.1:{http.server_port}")
    finally:
        http.shutdown()


@pytest.mark.parametrize("shell", MATRIX, ids=[shell.name for shell in MATRIX])
def test_a_stop_figure_is_carried_as_written_on_every_jq(
        shell, stand_in, tmp_path):
    for file in render(json.loads(BLUEPRINT.read_text(encoding="utf-8"))):
        target = tmp_path / "artifact" / file["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(file["contents"].encode("utf-8"))
    (tmp_path / "main.sh").write_bytes(
        b". ./artifact/ubb_integration.sh\n"
        b"ubb_record_search_run customer_id=c idempotency_key=call-1"
        b" task_id=t searches=1 && status=0 || status=$?\n"
        b"printf 'status=%s\\n' \"$status\"\n"
        b"printf 'stop_requested=%s\\n' \"$UBB_STOP_REQUESTED\"\n")
    ran = subprocess.run(
        in_image(shell.image, shell.command, "main.sh", work=tmp_path,
                 environment={"UBB_BASE_URL": stand_in.url_from_a_container,
                              "UBB_API_KEY": "not-a-key"},
                 network=stand_in.network),
        capture_output=True)
    ran = Ran(status=ran.returncode, stdout=ran.stdout.decode("utf-8"),
              stderr=ran.stderr.decode("utf-8", "replace"))

    assert ran.said == {"status": "20", "stop_requested": CARRIED_STOP}, ran


def test_the_matrix_holds_the_oldest_jq():
    """Vacuity guard: the figure above is only at risk on a jq that holds a
    number as a double, which the matrix carries as its oldest jq."""
    assert "oldest-jq" in [shell.image for shell in MATRIX]
