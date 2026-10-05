"""The standing matrix of shells, and the one case in it that must fail
(#582; ADR-0017 §3 left the matrix to this suite).

The generated shell file runs under every shell in `_scenarios.MATRIX` — dash,
bash 5.2, bash 3.2 (what macOS ships as `bash` and as `sh`) and dash with the
oldest jq the file runs with — and the lifecycle and the ceiling scenarios run
in each, against the real application (`test_every_scenario_runs_unmodified`).

What decided how the file hands jq its programs is kept as two scripts in the
renderer's harness: the form it writes (a heredoc on jq's standard input) and
the form it decided against (a heredoc inside a command substitution). Both
carry every kind of declared name on every shell but one: bash 3.2 reads a
heredoc inside `$( )` as shell, and one backtick in a name ends it. So across
the whole matrix exactly one of these runs fails, and it is that one.
"""
import json
import subprocess

import pytest

from _harness import REPO_ROOT, as_this_user, image
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


def _run(form, shell, directory):
    ran = subprocess.run(
        ["docker", "run", "--rm",
         "--volume", f"{EVIDENCE}:/evidence:ro",
         "--volume", f"{directory}:/work", "--workdir", "/work",
         *as_this_user(), image(shell.image), shell.command,
         f"/evidence/{form}.sh"],
        capture_output=True)
    said = dict(line.split("=", 1) for line
                in ran.stdout.decode("utf-8").splitlines() if "=" in line)
    return ran.returncode, said, ran.stderr.decode("utf-8", "replace")


@pytest.mark.parametrize("shell", MATRIX, ids=[shell.name for shell in MATRIX])
@pytest.mark.parametrize("form", [CHOSEN, DECIDED_AGAINST])
def test_only_bash_3_2_fails_and_only_the_form_decided_against(
        form, shell, tmp_path):
    status, said, stderr = _run(form, shell, tmp_path)

    if (form, shell.name) == (DECIDED_AGAINST, BASH_3_2):
        assert status != 0, said
        assert "bad substitution" in stderr, stderr
        assert "carried" not in said
    else:
        assert (status, stderr) == (0, ""), stderr
        assert json.loads(said["carried"]) == CARRIED
    # Whichever way it went, no declared name ran as a command.
    assert not (tmp_path / "made-by-a-name").exists()


def test_the_matrix_holds_the_shell_that_decided_it():
    """Vacuity guard: without bash 3.2 in the matrix the case above that
    must fail is never run."""
    assert BASH_3_2 in [shell.name for shell in MATRIX]
