"""A machine without the tools a generated shell file needs is refused
before anything happens (#582; #180 §12; ADR-0017 §1).

The renderer's own suite proves the refusals with stand-ins on `PATH`. Here
they are real machines: four pinned images under `images/`, each the
`shell` image with one thing missing or too old —

* `without-jq`: no jq at all;
* `without-curl`: no curl at all;
* `jq-1.4`: a jq that cannot run the programs the file hands it (it has no
  `--argjson` and no `--slurpfile`);
* `curl-7.75`: a curl without `--fail-with-body`, which arrived in 7.76.

A complete artifact is run in each exactly as in the shell image the
lifecycle passes in, and each must refuse with the file's own words for that
defect and its own status, BEFORE ANY REQUEST, Task or temporary work: the
application is watched for a request while the script runs, the tenant's
work is counted, and the container's `/tmp` is a directory this test holds.
"""
import pytest

from apps.platform.work.models import Task

from _customer import shell_script
from _harness import catalogue, run_shell, write
from _scenarios import (
    SHELL, _declared_status, _refusal_configuration, _refusal_work)
from _tenant import ScenarioTenant

pytestmark = pytest.mark.django_db(transaction=True)

#: Each image, and the catalogue member naming what it lacks.
MACHINES = {
    "without-jq": "jqMissing",
    "without-curl": "curlMissing",
    "jq-1.4": "jqUnusable",
    "curl-7.75": "curlUnusable",
}


@pytest.mark.parametrize("image_name", sorted(MACHINES))
def test_a_machine_without_a_tool_it_needs_is_refused_before_any_request(
        image_name, server, tmp_path):
    tenant = ScenarioTenant(f"preflight on {image_name}")
    selection = _refusal_configuration(tenant, SHELL)
    artifact = write(tenant.blueprint(SHELL, **selection), tmp_path / "work")
    temporary = tmp_path / "tmp"
    temporary.mkdir()
    (work,) = _refusal_work(SHELL)

    ran = run_shell(artifact, shell_script(artifact, work, tenant.customers),
                    server=server, api_key=tenant.raw_key,
                    image_name=image_name, temporary=temporary)

    message = catalogue()["SHELL_MESSAGES"][MACHINES[image_name]]
    # Its own words, and nothing else said: a refusal for any other reason
    # would print something else.
    assert ran.stderr.splitlines() == [message], ran
    assert ran.status == _declared_status(
        artifact, "UBB_EXIT_TOOL_UNAVAILABLE"), ran
    assert ran.said["status"] == str(ran.status), ran
    # Before any request, unit of work or temporary file.
    assert ran.requests == [], ran
    assert not Task.objects.filter(tenant=tenant.tenant).exists()
    assert list(temporary.iterdir()) == [], ran
