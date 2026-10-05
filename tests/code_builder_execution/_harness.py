"""The execution harness: what Seam C does between a resolved Blueprint and a
record in the database (#582; ADR-0008 §5, #158 §5.3–§5.5).

    render it  ->  write it to disk, unpatched  ->  run it as a customer runs it

**Rendering** is `ubb-codegen`'s own `render`, called through
`apps/codegen/scripts/render.ts`, which prints exactly what `render` returns.

**Writing** puts the files under `artifact/` in a directory of their own and
takes a sha256 of each as it is written. Before every run and after it, the
directory is held to that set: every file there, unchanged, and nothing else.
Nothing in this suite edits a rendered file; this is what would notice if
something did (ADR-0008 §5: CI may supply the code's runtime inputs, it may
not repair the code).

**Running** is a customer's script beside the files, under `customer/`. The
script is the glue a customer writes — it imports or sources the rendered
module and pastes the rendered call-site blocks into its own code
(`_customer.py`) — and it supplies only runtime values. The process is given
the two documented variables, `UBB_BASE_URL` and `UBB_API_KEY`, and no other
`UBB_` variable. Python runs on this machine against the SDK in this tree;
shell runs in a pinned image (`images/`), on a machine of its own.

**Only complete artifacts run as a lifecycle.** A scaffold or a blocked
artifact is run for one reason, to prove it fails fast: none of its calls
that are not ready may reach the application, and the harness checks that
itself by watching the server.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from django.core.signals import request_started

REPO_ROOT = Path(__file__).resolve().parents[2]
SUITE = Path(__file__).resolve().parent

#: `render` from outside the renderer, run by Node straight from TypeScript.
RENDER = REPO_ROOT / "apps" / "codegen" / "scripts" / "render.ts"
#: The SDK the generated Python is run against: the one in this tree.
SDK = REPO_ROOT / "ubb-sdk"
#: The pinned images a generated shell file is run in (`images/<name>`).
IMAGES = SUITE / "images"
#: The deterministic supplier responses a customer's code hands over.
RESPONSES = SUITE / "provider_responses"
#: The committed contract: where each operation a Blueprint names is served.
CONTRACT = REPO_ROOT / "openapi" / "v1.json"

#: Where the rendered files are written, and where the customer's own are.
ARTIFACT = "artifact"
CUSTOMER = "customer"

#: The one readiness that runs as a lifecycle (ADR-0008 §5, #158 §5.6).
COMPLETE = "complete"

#: What a container calls the machine the live server is listening on, where
#: the container cannot share that machine's network (Docker Desktop).
CONTAINER_HOST = "host.docker.internal"

#: The two variables a generated file reads, and the only ones a run is given.
BASE_URL = "UBB_BASE_URL"
API_KEY = "UBB_API_KEY"


class ArtifactEdited(AssertionError):
    """A rendered file on disk is not what was rendered, or the directory
    holds a file `render` did not return, or lacks one it did."""


class NotRunnable(AssertionError):
    """A run the harness refuses to make: a lifecycle over an artifact that
    is not complete, or a fail-fast proof over one that is."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def catalogue() -> dict:
    """The renderer's catalogue — every fixed thing a generated file says —
    as `ubb-codegen` pins it, whole, in the one file named for its version."""
    (pinned,) = (REPO_ROOT / "apps" / "codegen" / "tests"
                 / "__snapshots__").glob("catalogue.v*.json")
    return json.loads(pinned.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Rendering and writing
# ---------------------------------------------------------------------------

def render(blueprint: dict) -> list[dict]:
    """The files `ubb-codegen` renders from `blueprint`, as it returns them."""
    ran = subprocess.run(
        ["node", "--experimental-strip-types", str(RENDER)],
        input=json.dumps(blueprint).encode("utf-8"), capture_output=True)
    if ran.returncode != 0:
        raise AssertionError(
            f"ubb-codegen refused the Blueprint:\n"
            f"{ran.stderr.decode('utf-8', 'replace')}")
    return json.loads(ran.stdout.decode("utf-8"))


@dataclass
class Artifact:
    """A rendered artifact on disk, with the checksum of every file."""

    blueprint: dict
    root: Path
    #: `path -> contents`, exactly as `render` returned them.
    files: dict[str, str]
    #: `path -> sha256`, taken of what was written.
    digests: dict[str, str]

    @property
    def directory(self) -> Path:
        return self.root / ARTIFACT

    @property
    def readiness(self) -> str:
        return self.blueprint["readiness"]

    @property
    def target(self) -> str:
        return self.blueprint["target"]

    def block(self, path: str) -> str:
        """A rendered call-site block, by its path under `call_sites/`."""
        name = f"call_sites/{path}"
        if name not in self.files:
            raise AssertionError(
                f"the artifact has no {name}: {sorted(self.files)}")
        return self.files[name]

    def unchanged(self) -> None:
        """Every rendered file is on disk as it was written, and the
        directory holds nothing else. Raises `ArtifactEdited`."""
        on_disk = {path.relative_to(self.directory).as_posix(): path
                   for path in self.directory.rglob("*") if path.is_file()}
        added = sorted(set(on_disk) - set(self.digests))
        missing = sorted(set(self.digests) - set(on_disk))
        if added or missing:
            raise ArtifactEdited(
                f"the artifact directory no longer holds what was rendered: "
                f"added {added}, missing {missing}")
        edited = sorted(path for path, digest in self.digests.items()
                        if sha256(on_disk[path].read_bytes()) != digest)
        if edited:
            raise ArtifactEdited(
                f"rendered files changed on disk after they were written: "
                f"{edited}")


def write(blueprint: dict, root: Path) -> Artifact:
    """Render `blueprint` and write the files under `root/artifact`, as
    bytes, exactly as returned: no newline is translated on any machine."""
    files = {file["path"]: file["contents"] for file in render(blueprint)}
    if not files:
        raise AssertionError("ubb-codegen rendered no files")
    digests = {}
    for path, contents in files.items():
        data = contents.encode("utf-8")
        target = root / ARTIFACT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        digests[path] = sha256(data)
    (root / CUSTOMER).mkdir(parents=True, exist_ok=True)
    artifact = Artifact(blueprint=blueprint, root=root, files=files,
                        digests=digests)
    artifact.unchanged()
    return artifact


# ---------------------------------------------------------------------------
# The application, served
# ---------------------------------------------------------------------------

@dataclass
class Server:
    """The real application, served by pytest-django's `live_server`, and
    how each place a script runs reaches it."""

    url: str

    @property
    def port(self) -> int:
        return int(self.url.rsplit(":", 1)[1])

    @property
    def shares_the_network(self) -> bool:
        """On Linux a container can share this machine's network, so it
        reaches the server where this process does. Docker Desktop cannot,
        and names this machine `host.docker.internal` instead."""
        return sys.platform.startswith("linux")

    @property
    def url_from_a_container(self) -> str:
        return (self.url if self.shares_the_network
                else f"http://{CONTAINER_HOST}:{self.port}")

    @property
    def network(self) -> list[str]:
        return ["--network", "host"] if self.shares_the_network else []

    @contextmanager
    def watching(self):
        """Every request the application starts to handle while the block
        runs, as `(method, path)` — read off Django's own signal, so it sees
        a request whether or not anything answers it."""
        seen: list[tuple[str, str]] = []

        def heard(sender, environ=None, **kwargs):
            environ = environ or {}
            seen.append((environ.get("REQUEST_METHOD", ""),
                         environ.get("PATH_INFO", "")))

        request_started.connect(heard, weak=False)
        try:
            yield seen
        finally:
            request_started.disconnect(heard)


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------

@dataclass
class Ran:
    """What a run did: its status and output, and every request the
    application saw while it ran."""

    status: int
    stdout: str
    stderr: str
    requests: list[tuple[str, str]] = field(default_factory=list)

    @property
    def said(self) -> dict[str, str]:
        """What the customer's script printed as `name=value` lines."""
        return dict(line.split("=", 1) for line in self.stdout.splitlines()
                    if re.match(r"^[a-z_]+=", line))

    def __str__(self):
        return (f"status {self.status}\n--- stdout\n{self.stdout}"
                f"\n--- stderr\n{self.stderr}\n--- requests\n{self.requests}")


#: Why a run is made: a lifecycle, which only a complete artifact may be;
#: or a proof that a not-ready artifact fails fast, which must reach nothing.
LIFECYCLE = "lifecycle"
FAIL_FAST = "fail_fast"


def _permitted(artifact: Artifact, purpose: str) -> None:
    if purpose == LIFECYCLE and artifact.readiness != COMPLETE:
        raise NotRunnable(
            f"only a complete artifact runs as a lifecycle; this one is "
            f"{artifact.readiness}")
    if purpose == FAIL_FAST and artifact.readiness == COMPLETE:
        raise NotRunnable(
            "a complete artifact has nothing to fail fast on")
    if purpose not in (LIFECYCLE, FAIL_FAST):
        raise NotRunnable(f"no run is made for {purpose!r}")


def _environment(base_url: str, api_key: str) -> dict[str, str]:
    """This machine's environment with every `UBB_` variable removed, and
    the two documented ones set."""
    environment = {name: value for name, value in os.environ.items()
                   if not name.startswith("UBB_")}
    environment[BASE_URL] = base_url
    environment[API_KEY] = api_key
    return environment


def run_python(artifact: Artifact, script: str, *, server: Server,
               api_key: str, purpose: str = LIFECYCLE) -> Ran:
    """Run `script` — the customer's Python — with the rendered module
    importable and the SDK in this tree beside it."""
    _permitted(artifact, purpose)
    path = artifact.root / CUSTOMER / "main.py"
    path.write_bytes(script.encode("utf-8"))
    environment = _environment(server.url, api_key)
    # Where the customer put the module, and the SDK it is run against. No
    # bytecode is written, so the artifact directory gains no file.
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(artifact.directory), str(SDK)])
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    # A traceback in plain text, whatever the terminal this suite runs in.
    environment["PYTHON_COLORS"] = "0"
    return _run(artifact, [sys.executable, str(path)], environment,
                server=server, purpose=purpose)


#: Images built in this session, by name.
_BUILT: dict[str, str] = {}


def image(name: str) -> str:
    """The pinned image `images/<name>`, built once per session."""
    if name not in _BUILT:
        tag = f"ubb-code-builder-execution/{name}"
        built = subprocess.run(
            ["docker", "build", "--quiet", "--tag", tag, str(IMAGES / name)],
            capture_output=True)
        if built.returncode != 0:
            raise AssertionError(
                f"the image {name} did not build:\n"
                f"{built.stderr.decode('utf-8', 'replace')}")
        _BUILT[name] = tag
    return _BUILT[name]


def run_shell(artifact: Artifact, script: str, *, server: Server,
              api_key: str, image_name: str = "shell", shell: str = "sh",
              purpose: str = LIFECYCLE, temporary: Path | None = None) -> Ran:
    """Run `script` — the customer's shell — under `shell` in the image
    `image_name`, with the work directory mounted as `/work`.

    `temporary`, when given, is mounted as the container's `/tmp`, so a test
    can see whether anything was left there."""
    _permitted(artifact, purpose)
    tag = image(image_name)
    (artifact.root / CUSTOMER / "main.sh").write_bytes(script.encode("utf-8"))
    argv = ["docker", "run", "--rm", *server.network,
            "--volume", f"{artifact.root}:/work", "--workdir", "/work",
            "--env", f"{BASE_URL}={server.url_from_a_container}",
            "--env", f"{API_KEY}={api_key}"]
    if temporary is not None:
        argv += ["--volume", f"{temporary}:/tmp"]
    argv += [*as_this_user(), tag, shell, f"{CUSTOMER}/main.sh"]
    return _run(artifact, argv, None, server=server, purpose=purpose)


def as_this_user() -> list[str]:
    """Where users are numbered, a container runs as this one, so what it
    writes into a mounted directory can be read, checked and removed."""
    if hasattr(os, "getuid"):
        return ["--user", f"{os.getuid()}:{os.getgid()}"]
    return []


def not_ready_routes(blueprint: dict) -> list[tuple[str, re.Pattern]]:
    """`(method, path pattern)` of every operation a not-ready call of
    `blueprint` names, read off the committed contract."""
    served = {}
    for path, methods in json.loads(
            CONTRACT.read_text(encoding="utf-8"))["paths"].items():
        for method, operation in methods.items():
            if isinstance(operation, dict) and "operationId" in operation:
                served[operation["operationId"]] = (
                    method.upper(),
                    re.compile("^" + re.sub(r"\{[^{}]+\}", "[^/]+", path)
                               + "$"))
    return [served[call["operation_id"]] for call in blueprint["calls"]
            if call["readiness"] != COMPLETE]


def _run(artifact, argv, environment, *, server, purpose) -> Ran:
    artifact.unchanged()
    with server.watching() as requests:
        ran = subprocess.run(argv, capture_output=True, env=environment,
                             cwd=artifact.root, timeout=600)
    artifact.unchanged()
    result = Ran(status=ran.returncode,
                 stdout=ran.stdout.decode("utf-8", "replace"),
                 stderr=ran.stderr.decode("utf-8", "replace"),
                 requests=list(requests))
    if purpose == FAIL_FAST:
        # A call that is not ready fails before it is sent: none of those
        # calls' operations may have been asked for, whatever else was.
        not_ready = not_ready_routes(artifact.blueprint)
        reached = [(method, path) for method, path in result.requests
                   if any(method == expected and pattern.match(path)
                          for expected, pattern in not_ready)]
        if reached:
            raise AssertionError(
                f"a call that is not ready reached the application at "
                f"{reached}:\n{result}")
    return result
