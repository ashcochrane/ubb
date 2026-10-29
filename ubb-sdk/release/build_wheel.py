"""Build the SDK's release wheel from its annotated tag, reproducibly (R2; #190).

    python ubb-sdk/release/build_wheel.py --tag sdk-v4.0.0 --commit <full sha> --out <dir>

The SDK release is a TAG plus a reproducibly built WHEEL, and no publish
mechanism (R2, recorded in #190 spec part 3 §9 and part 4; ADR-0026). This is
the recipe, committed with the code it builds so the tag carries it. It builds
from a clean export of the tag — never from a working checkout — twice, in two
fresh directories, inside a fresh virtual environment holding exactly the tag's
lock (``build-requirements.txt``: every package, pinned and hashed) and nothing
else — not even an installer: the environment is created without pip, and the
release Python's own pip installs the lock into it from outside, so no package
in it is exempt from the check. No outside Python setting reaches the install
or the build (:func:`release_environment`). It REFUSES rather than warns when:

- the running Python is not :data:`RELEASE_PYTHON` (major.minor);
- the tag is not annotated, or does not dereference to ``--commit``;
- the tag's package version is not the version the tag names;
- the export is not byte-for-byte the tag's tree (a dirty source);
- the recipe running is not the tag's own recipe — the pins and the recipe the
  release is built with are the ones the TAG carries, never the invoking
  checkout's;
- a line of the lock is not an exact, hashed pin;
- the build backend ``pyproject.toml`` requires is not exactly a pin in the
  lock;
- the build environment is not exactly the lock — a package missing, extra
  (an installer included) or at another version;
- the two builds' SHA-256 differ.

``SOURCE_DATE_EPOCH`` is the tagged commit's committer time, so the wheel's
timestamps are the commit's. The export is taken with ``core.autocrlf`` off, so
the wheel holds the repository's bytes whatever the builder's git configuration.
It writes the wheel and ``<tag>.release.json`` (:func:`release_identity`) — the
tag and the commit it dereferences to, the release Python's major.minor and
exact version, the platform, the lock's path and SHA-256 with every package it
installed, the installer that ran outside the environment, this recipe's own
SHA-256, the wheel's filename and its SHA-256 — to ``--out``.
"""

import argparse
import hashlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path

#: The Python major.minor the release is built with. A different interpreter is
#: an incompatible release environment and is refused.
RELEASE_PYTHON = (3, 13)

HERE = Path(__file__).resolve().parent
SDK_DIR = "ubb-sdk"
#: Where the recipe and its pins sit inside an export of the tag.
TAG_RECIPE = f"{SDK_DIR}/release/build_wheel.py"
TAG_REQUIREMENTS = f"{SDK_DIR}/release/build-requirements.txt"
TAG_PATTERN = re.compile(r"^sdk-v(\d+\.\d+\.\d+)$")


class RefusedRelease(SystemExit):
    """The recipe's one way of stopping: a stated reason, a non-zero exit."""

    def __init__(self, reason):
        super().__init__(f"release refused: {reason}")
        self.reason = reason


# --- the refusals, each a pure function the release test plants against -----

def refuse_unless_the_release_python(version_info):
    if tuple(version_info[:2]) != RELEASE_PYTHON:
        raise RefusedRelease(
            f"the release is built with Python {RELEASE_PYTHON[0]}.{RELEASE_PYTHON[1]}, "
            f"not {version_info[0]}.{version_info[1]}")


def refuse_unless_an_annotated_tag_on(tag, object_type, dereferenced, expected):
    if not TAG_PATTERN.match(tag):
        raise RefusedRelease(f"{tag!r} is not an SDK release tag (sdk-vX.Y.Z)")
    if object_type != "tag":
        raise RefusedRelease(f"{tag} is a {object_type}, not an annotated tag")
    if not re.fullmatch(r"[0-9a-f]{40}", expected or ""):
        raise RefusedRelease("--commit must be the full 40-character commit")
    if dereferenced != expected:
        raise RefusedRelease(f"{tag} names {dereferenced}, not the expected "
                             f"commit {expected}")


def refuse_unless_the_version_is_the_tags(tag, pyproject_text):
    found = re.search(r'(?m)^version\s*=\s*"([^"]+)"', pyproject_text)
    wanted = TAG_PATTERN.match(tag).group(1)
    if not found or found.group(1) != wanted:
        raise RefusedRelease(f"{tag} builds version "
                             f"{found.group(1) if found else None}, not {wanted}")


def pinned(requirements_text, os_name):
    """`{name: version}` the requirements pin for this OS, refusing any line
    that is not an exact, hashed pin."""
    pins = {}
    logical = re.sub(r"\\\n", " ", requirements_text)
    for line in logical.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(
            r"([A-Za-z0-9_.-]+)==([^\s;]+)\s*(?:;\s*os_name\s*==\s*\"(\w+)\")?"
            r"\s+--hash=sha256:[0-9a-f]{64}", line)
        if not match:
            raise RefusedRelease(f"{line!r} is not an exact, hashed pin")
        name, version, only_on = match.groups()
        if only_on is None or only_on == os_name:
            pins[canonical(name)] = version
    return pins


def canonical(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def refuse_unless_the_backend_is_locked(pyproject_text, pins):
    """Every requirement of ``[build-system]`` is ``name==version`` with that
    exact pin in the lock: the backend the wheel is built by is one the lock
    installs, never one resolved from outside it."""
    requires = tomllib.loads(pyproject_text).get("build-system", {}).get("requires")
    if not requires:
        raise RefusedRelease("pyproject.toml names no [build-system] requires")
    for requirement in requires:
        match = re.fullmatch(r"\s*([A-Za-z0-9_.-]+)\s*==\s*([^\s;,]+)\s*", requirement)
        if not match or pins.get(canonical(match.group(1))) != match.group(2):
            raise RefusedRelease(f"the build backend's {requirement!r} is not "
                                 f"exactly a pin in the lock")


def refuse_unless_exactly_pinned(installed, pins):
    """`installed` is `{name: version}` of EVERY distribution in the build
    environment — which holds no installer, so none is set aside. Anything
    missing, extra or different is an unpinned or incompatible environment."""
    extra = sorted(set(installed) - set(pins))
    missing = sorted(set(pins) - set(installed))
    different = sorted(name for name in set(pins) & set(installed)
                       if pins[name] != installed[name])
    if extra or missing or different:
        raise RefusedRelease(f"the build environment is not the pinned one: "
                             f"extra {extra}, missing {missing}, "
                             f"different {different}")


def git_blob_id(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def refuse_unless_the_tags_tree(listed, exported):
    """`listed` is `{path: blob id}` from `git ls-tree -r <tag>`; `exported` is
    `{path: bytes}` of the export. A path more or less, or one byte different,
    is a dirty source."""
    if set(listed) != set(exported):
        raise RefusedRelease(
            f"the export is not the tag's tree: "
            f"{sorted(set(listed) ^ set(exported))[:5]}")
    changed = sorted(path for path, data in exported.items()
                     if git_blob_id(data) != listed[path])
    if changed:
        raise RefusedRelease(f"the export differs from the tag's tree: {changed[:5]}")


def refuse_unless_the_tags_recipe(running, carried):
    """The recipe that runs must be the one the tag carries, byte for byte, so
    an edited local copy — or edited local pins beside it — never builds a
    release."""
    if carried is None:
        raise RefusedRelease(f"the tag carries no {TAG_RECIPE}")
    if running != carried:
        raise RefusedRelease("the recipe running is not the tag's own recipe; run "
                             "the one the tag carries")


def refuse_unless_reproduced(first, second):
    if first != second:
        raise RefusedRelease(f"two builds of one tag differ: {first} != {second}")


#: Settings the builder's own shell could carry into the install or the build:
#: an import path, a startup file, a package index or pip option, a backend or
#: distutils switch, a hook override, an active virtual environment.
OUTSIDE_SETTINGS = ("PYTHON", "PIP_", "SETUPTOOLS", "DISTUTILS", "_PYPROJECT_HOOKS",
                    "VIRTUAL_ENV", "CONDA_")


def release_environment(base):
    """The process environment the install and the builds run in: the
    builder's, less every setting in :data:`OUTSIDE_SETTINGS`, with the hash
    seed, the user site and the text encoding fixed."""
    kept = {name: value for name, value in base.items()
            if not name.upper().startswith(OUTSIDE_SETTINGS)}
    return {**kept, "PYTHONHASHSEED": "0", "PYTHONNOUSERSITE": "1", "PYTHONUTF8": "1"}


def release_identity(*, tag, commit, epoch, python_version, platform_name, lock_bytes,
                     installed, installer, recipe_bytes, wheel_name, wheel_sha256):
    """The release's evidence: everything a second builder needs to say they
    built the same thing, and the one number that says they did."""
    return {
        "tag": tag,
        "commit": commit,
        "source_date_epoch": epoch,
        "python": {"release": f"{RELEASE_PYTHON[0]}.{RELEASE_PYTHON[1]}",
                   "exact": python_version},
        "platform": platform_name,
        "lock": {"path": TAG_REQUIREMENTS,
                 "sha256": hashlib.sha256(lock_bytes).hexdigest(),
                 "installed": dict(sorted(installed.items()))},
        "installer": {"pip": installer, "in_the_build_environment": False},
        "recipe_sha256": hashlib.sha256(recipe_bytes).hexdigest(),
        "wheel": wheel_name,
        "sha256": wheel_sha256,
        "builds_compared": 2,
    }


# --- the recipe --------------------------------------------------------------

def git(repo, *args, data=False):
    ran = subprocess.run(["git", "-c", "core.autocrlf=false", *args], cwd=repo,
                         capture_output=True, check=True)
    return ran.stdout if data else ran.stdout.decode("utf-8").strip()


def export(repo, tag, into):
    archive = git(repo, "archive", "--format=tar", tag, SDK_DIR, data=True)
    exported = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            if member.isfile():
                exported[member.name] = tar.extractfile(member).read()
    for path, content in exported.items():
        target = into / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return exported


def listed_tree(repo, tag):
    listed = {}
    for line in git(repo, "ls-tree", "-r", "--full-tree", tag, "--", SDK_DIR).splitlines():
        meta, path = line.split("\t", 1)
        _mode, kind, blob = meta.split()
        if kind == "blob":
            listed[path] = blob
    return listed


#: What the build environment holds, read by its own interpreter in isolated
#: mode (no script directory, no user site, no ``PYTHON*`` setting).
INSTALLED = ("import importlib.metadata as m, json, re; print(json.dumps("
             "{re.sub(r'[-_.]+', '-', d.metadata['Name']).lower(): d.version "
             "for d in m.distributions()}))")


def build_environment(work, requirements, environment):
    """A virtual environment holding exactly the lock: created WITHOUT pip,
    and filled by the release Python's own pip from outside it (``--python``),
    isolated from every pip configuration file and setting."""
    env_dir = work / "env"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(env_dir)],
                   check=True, env=environment)
    python = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    installer = subprocess.run([sys.executable, "-m", "pip", "--version"], check=True,
                               capture_output=True, text=True, env=environment
                               ).stdout.split()[1]
    subprocess.run([sys.executable, "-m", "pip", "--isolated", "--python", str(python),
                    "install", "--quiet", "--disable-pip-version-check", "--no-input",
                    "--require-hashes", "--no-deps", "--only-binary=:all:",
                    "-r", str(requirements)], check=True, env=environment)
    listed = subprocess.run([str(python), "-I", "-c", INSTALLED], check=True,
                            capture_output=True, text=True, env=environment).stdout
    installed = json.loads(listed)
    refuse_unless_exactly_pinned(installed, pinned(requirements.read_text(encoding="utf-8"),
                                                   os.name))
    return python, installed, installer


def build_once(python, export_dir, out_dir, epoch, environment):
    source = out_dir / "source"
    shutil.copytree(export_dir, source)
    subprocess.run([str(python), "-m", "build", "--wheel", "--no-isolation",
                    "--outdir", str(out_dir / "dist"), str(source / SDK_DIR)],
                   check=True, env={**environment, "SOURCE_DATE_EPOCH": str(epoch)},
                   capture_output=True)
    (wheel,) = sorted((out_dir / "dist").glob("*.whl"))
    return wheel, hashlib.sha256(wheel.read_bytes()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--repo", type=Path, default=HERE.parents[1])
    args = parser.parse_args(argv)

    refuse_unless_the_release_python(sys.version_info)
    repo = args.repo.resolve()
    refuse_unless_an_annotated_tag_on(
        args.tag, git(repo, "cat-file", "-t", args.tag),
        git(repo, "rev-parse", f"{args.tag}^{{commit}}"), args.commit)
    epoch = int(git(repo, "log", "-1", "--format=%ct", args.commit))

    with tempfile.TemporaryDirectory(prefix="ubb-sdk-release-") as scratch:
        work = Path(scratch)
        exported = export(repo, args.tag, work / "export")
        refuse_unless_the_tags_tree(listed_tree(repo, args.tag), exported)
        refuse_unless_the_version_is_the_tags(
            args.tag, exported[f"{SDK_DIR}/pyproject.toml"].decode("utf-8"))
        refuse_unless_the_tags_recipe(Path(__file__).read_bytes(), exported.get(TAG_RECIPE))
        requirements = work / "export" / TAG_REQUIREMENTS
        refuse_unless_the_backend_is_locked(
            exported[f"{SDK_DIR}/pyproject.toml"].decode("utf-8"),
            pinned(requirements.read_text(encoding="utf-8"), os.name))

        environment = release_environment(os.environ)
        python, installed, installer = build_environment(work, requirements, environment)
        first, first_sha = build_once(python, work / "export", work / "one", epoch,
                                      environment)
        second, second_sha = build_once(python, work / "export", work / "two", epoch,
                                        environment)
        refuse_unless_reproduced(first_sha, second_sha)

        args.out.mkdir(parents=True, exist_ok=True)
        shutil.copy2(first, args.out / first.name)
        identity = release_identity(
            tag=args.tag, commit=args.commit, epoch=epoch,
            python_version=platform.python_version(), platform_name=platform.platform(),
            lock_bytes=requirements.read_bytes(), installed=installed,
            installer=installer, recipe_bytes=Path(__file__).read_bytes(),
            wheel_name=first.name, wheel_sha256=first_sha)
        (args.out / f"{args.tag}.release.json").write_text(
            json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(identity, indent=2))
    return identity


if __name__ == "__main__":
    main()
