"""Every declared scenario, on every target it names, run unmodified against
the real application (#582; ADR-0008 §5, #158 §5.3).

For each one, the seven steps, in order:

1. a tenant of its own is seeded and its configuration declared through its
   routes (`_tenant.py`);
2. the Blueprint is resolved through its route, and must be what the
   scenario says it is before anything else happens;
3. `ubb-codegen` renders it;
4. the files are written to disk unpatched, each checksummed as written;
5. the run is given `UBB_BASE_URL` and `UBB_API_KEY` and nothing else of
   UBB's;
6. the customer's own script runs it — Python on this machine, shell in a
   pinned image — and the checksums are held before and after;
7. the scenario asserts what the runs did and what the application holds.

A scenario whose Blueprint is not complete is run only to prove it fails
fast; the harness itself refuses a lifecycle over it, and fails the run if
any of its not-ready calls reached the application.
"""
import shutil

import pytest

from _customer import python_script, shell_script
from _harness import (
    COMPLETE, CUSTOMER, FAIL_FAST, LIFECYCLE, RESPONSES, run_python,
    run_shell, write)
from _scenarios import PYTHON, SCENARIOS, Outcome
from _tenant import ScenarioTenant

pytestmark = pytest.mark.django_db(transaction=True)


def _cases():
    for scenario in SCENARIOS:
        for target in scenario.targets:
            if target == PYTHON:
                yield pytest.param(scenario, target, None,
                                   id=f"{scenario.name}-{target}")
                continue
            for shell in scenario.shells:
                yield pytest.param(scenario, target, shell,
                                   id=f"{scenario.name}-{target}-{shell.name}")


@pytest.mark.parametrize("scenario,target,shell", list(_cases()))
def test_a_scenario_runs_unmodified(scenario, target, shell, server,
                                    tmp_path):
    tenant = ScenarioTenant(f"{scenario.name} on {target}",
                            **scenario.posture)
    selection = scenario.configure(tenant, target)
    blueprint = tenant.blueprint(target, **selection)
    assert blueprint["readiness"] == scenario.readiness, (
        blueprint["diagnostics"])

    artifact = write(blueprint, tmp_path)
    shutil.copytree(RESPONSES, tmp_path / CUSTOMER / "responses")
    purpose = LIFECYCLE if scenario.readiness == COMPLETE else FAIL_FAST

    runs = []
    for work in scenario.works(target):
        if target == PYTHON:
            runs.append(run_python(
                artifact, python_script(artifact, work, tenant.customers),
                server=server, api_key=tenant.raw_key, purpose=purpose))
        else:
            runs.append(run_shell(
                artifact, shell_script(artifact, work, tenant.customers),
                server=server, api_key=tenant.raw_key,
                image_name=shell.image, shell=shell.command,
                purpose=purpose))

    scenario.expect(Outcome(target=target, tenant=tenant, artifact=artifact,
                            runs=runs))
