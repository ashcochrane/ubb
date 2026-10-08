"""The harness itself: it runs exactly what was rendered, only where it may,
and its own observations are not vacuous (#582; ADR-0008 §5).

These are the checks every scenario stands on, each shown failing where it
must. A rendered file changed, added to or taken away before a run stops the
run before anything starts; a file the run writes beside the rendered ones
is caught after it. A lifecycle is refused for an artifact that is not
complete, and a fail-fast proof for one that is. A fail-fast run that
reaches a call that is not ready fails, whatever the script exit says.

Blueprints that need no tenant are the renderer's committed fixtures, which
the platform's own suite holds equal to what its route answers.
"""
import json
import os

import pytest

from _harness import (
    API_KEY, ARTIFACT, BASE_URL, CUSTOMER, MACHINE, Purpose,
    PROVIDER_RESPONSES, ArtifactEdited, NotRunnable, REPO_ROOT, Server, render,
    run_python, run_shell, write)
from _scenarios import (
    BILLED, BILLED_AS_A_FLOAT, BILLED_IN_EUROS, COST_PATH, EURO_COST_PATH,
    GEMINI, INPUT_TOKENS,
    OPENAI, OUTPUT_TOKENS, held_at, held_in)

FIXTURES = REPO_ROOT / "apps" / "codegen" / "fixtures" / "blueprints"

#: Nothing listens here. A run that starts against it fails loudly, so a
#: check that is meant to stop a run first is seen to.
NOWHERE = Server(url="http://127.0.0.1:9")

#: A customer script that leaves a mark if it ever runs.
MARKER = "ran.txt"
LEAVES_A_MARK = f'open(r"{{root}}/{CUSTOMER}/{MARKER}", "w").write("ran")\n'


def _fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _a_script(artifact):
    return LEAVES_A_MARK.format(root=artifact.root)


def test_files_are_written_byte_for_byte_as_render_returned_them(tmp_path):
    blueprint = _fixture("shell-explicit-subtasks")
    artifact = write(blueprint, tmp_path)

    for file in render(blueprint):
        written = (tmp_path / ARTIFACT / file["path"]).read_bytes()
        assert written == file["contents"].encode("utf-8"), file["path"]
    assert len(artifact.digests) == len(render(blueprint))


@pytest.mark.parametrize("change", ["edited", "added", "removed"])
def test_a_changed_artifact_is_refused_before_the_run_starts(change,
                                                            tmp_path):
    artifact = write(_fixture("calculated-cost"), tmp_path)
    module = tmp_path / ARTIFACT / "ubb_integration.py"
    if change == "edited":
        # The repair ADR-0008 §5 names first: the host patched in.
        rendered = module.read_bytes()
        patched = rendered.replace(
            b'base_url = os.environ.get("UBB_BASE_URL")',
            b'base_url = "http://127.0.0.1:9"')
        assert patched != rendered
        module.write_bytes(patched)
    elif change == "added":
        (tmp_path / ARTIFACT / "sitecustomize.py").write_text("")
    else:
        (tmp_path / ARTIFACT / "call_sites" / "close.py").unlink()

    with pytest.raises(ArtifactEdited) as refused:
        run_python(artifact, _a_script(artifact), server=NOWHERE,
                   api_key="not-a-real-key")

    named = {"edited": "ubb_integration.py", "added": "sitecustomize.py",
             "removed": "call_sites/close.py"}[change]
    assert named in str(refused.value)
    assert not (tmp_path / CUSTOMER / MARKER).exists()


def test_a_file_the_run_writes_beside_the_rendered_ones_is_caught(tmp_path):
    artifact = write(_fixture("calculated-cost"), tmp_path)
    script = (f'open(r"{tmp_path / ARTIFACT}/left-behind.txt", "w")'
              f'.write("x")\n')

    with pytest.raises(ArtifactEdited) as caught:
        run_python(artifact, script, server=NOWHERE, api_key="x")

    assert "left-behind.txt" in str(caught.value)


def test_only_a_complete_artifact_runs_as_a_lifecycle(tmp_path):
    artifact = write(_fixture("scaffold"), tmp_path)

    with pytest.raises(NotRunnable) as refused:
        run_python(artifact, _a_script(artifact), server=NOWHERE,
                   api_key="x", purpose=Purpose.LIFECYCLE)

    assert "only a complete artifact runs as a lifecycle" in str(
        refused.value)
    assert "scaffold" in str(refused.value)
    assert not (tmp_path / CUSTOMER / MARKER).exists()


def test_a_complete_artifact_is_not_run_to_fail_fast(tmp_path):
    artifact = write(_fixture("calculated-cost"), tmp_path)

    with pytest.raises(NotRunnable) as refused:
        run_python(artifact, _a_script(artifact), server=NOWHERE,
                   api_key="x", purpose=Purpose.FAIL_FAST)

    assert "a complete artifact has nothing to fail fast on" in str(
        refused.value)
    assert not (tmp_path / CUSTOMER / MARKER).exists()


@pytest.mark.django_db(transaction=True)
def test_a_fail_fast_run_that_reaches_a_call_not_ready_fails(server,
                                                             tmp_path):
    """The check is the harness's, not the script's: a script that exits
    cleanly having reached the record operation of a scaffold still fails."""
    artifact = write(_fixture("scaffold"), tmp_path)
    script = ("import urllib.request\n"
              "try:\n"
              f"    urllib.request.urlopen(urllib.request.Request("
              f"{server.url + '/api/v1/metering/usage'!r}, data=b'{{}}', "
              f"method='POST'))\n"
              "except Exception:\n"
              "    pass\n")

    with pytest.raises(AssertionError) as caught:
        run_python(artifact, script, server=server, api_key="x",
                   purpose=Purpose.FAIL_FAST)

    assert "a call that is not ready reached the application" in str(
        caught.value)
    assert "/api/v1/metering/usage" in str(caught.value)


#: What this suite's own process holds that is nobody else's business: the
#: application's database, cache, secret and settings.
SUITES_OWN = ("DATABASE_URL", "REDIS_URL", "SECRET_KEY", "DEBUG",
              "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
              "DJANGO_SETTINGS_MODULE", "UBB_TEST_REDIS_DB")


def test_a_python_run_is_given_nothing_of_this_suites_own(tmp_path):
    """Of UBB's, only the two documented variables; of the suite's own,
    nothing. (An interpreter may set variables of its own in its own
    process, so what is held to the machine's few is the harness's list,
    `MACHINE`, not everything the child can see.)"""
    held = [name for name in SUITES_OWN if name in os.environ]
    assert "DATABASE_URL" in held  # the premise: there is one to leak
    artifact = write(_fixture("calculated-cost"), tmp_path)
    script = "import json, os\nprint('environment=' + json.dumps(sorted(os.environ)))\n"

    ran = run_python(artifact, script, server=NOWHERE, api_key="not-a-real-key")

    given = set(json.loads(ran.said["environment"]))
    assert {name for name in given if name.startswith("UBB_")} == {
        BASE_URL, API_KEY}
    assert set(held) & given == set(), given
    assert not set(held) & set(MACHINE)


def test_the_temporary_directory_a_shell_run_is_given_is_where_it_writes(
        tmp_path):
    """What makes "nothing was left in /tmp" an observation: a run that does
    write there leaves it in the directory the test reads."""
    artifact = write(_fixture("shell-direct-task-events"), tmp_path / "work")
    temporary = tmp_path / "tmp"
    temporary.mkdir()

    run_shell(artifact, "printf x >/tmp/made-by-the-run\n", server=NOWHERE,
              api_key="x", temporary=temporary)

    assert [path.name for path in temporary.iterdir()] == ["made-by-the-run"]


def test_the_provider_responses_carry_what_the_scenarios_expect():
    for supplier in (OPENAI, GEMINI):
        assert held_in(supplier) == (INPUT_TOKENS, OUTPUT_TOKENS), supplier
    # The billed responses are the web API's own, with what it cost beside
    # the counts: the counts the scenarios read are the same, and the cost is
    # money as JSON writes it — a decimal string and an integer, which every
    # target reads, and the one written as a float, which none does.
    billed = (BILLED, BILLED_IN_EUROS, BILLED_AS_A_FLOAT)
    for response in billed:
        assert tuple(held_at(response, path) for path in (
            GEMINI.input, GEMINI.output)) == (INPUT_TOKENS, OUTPUT_TOKENS)
    assert isinstance(held_at(BILLED, COST_PATH), str)
    assert type(held_at(BILLED_IN_EUROS, EURO_COST_PATH)) is int
    assert type(held_at(BILLED_AS_A_FLOAT, COST_PATH)) is float
    assert sorted(path.name for path in PROVIDER_RESPONSES.glob("*.json")) == sorted(
        [f"{supplier.shape}.json" for supplier in (OPENAI, GEMINI)]
        + [f"{response.fixture}.json" for response in billed])
