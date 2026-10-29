"""Build the SDK's release wheel from its annotated tag, reproducibly (R2; #190).

    python ubb-sdk/release/build_wheel.py --tag sdk-v4.0.0 --commit <full sha> --out <dir>

The SDK release is a TAG plus a reproducibly built WHEEL, and no publish
mechanism (R2, recorded in #190 spec part 3 §9 and part 4; ADR-0026). This is
the recipe, committed with the code it builds so the tag carries it. It builds
from a clean export of the tag — never from a working checkout — twice, in two
fresh directories, inside a fresh virtual environment holding exactly the pinned
and hashed build environment, and it REFUSES rather than warns when:

- the running Python is not :data:`RELEASE_PYTHON` (major.minor);
- the tag is not annotated, or does not dereference to ``--commit``;
- the tag's package version is not the version the tag names;
- the export is not byte-for-byte the tag's tree (a dirty source);
- the recipe running is not the tag's own recipe — the pins and the recipe the
  release is built with are the ones the TAG carries, never the invoking
  checkout's;
- the build environment is not exactly the tag's ``build-requirements.txt``
  (unpinned or incompatible);
- the two builds' SHA-256 differ.

``SOURCE_DATE_EPOCH`` is the tagged commit's committer time, so the wheel's
timestamps are the commit's. The export is taken with ``core.autocrlf`` off, so
the wheel holds the repository's bytes whatever the builder's git configuration.
It writes the wheel and ``<tag>.release.json`` — the tag, the commit, the Python
version, the platform, the toolchain (every pinned package, the installer's pip,
this recipe's own SHA-256), the wheel's filename and its SHA-256 — to ``--out``.
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


def refuse_unless_exactly_pinned(installed, pins):
    """`installed` is `{name: version}` from the build environment, the
    installer itself (pip) aside. Anything missing, extra or different is an
    unpinned or incompatible environment."""
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


def build_environment(work, requirements):
    env_dir = work / "env"
    subprocess.run([sys.executable, "-m", "venv", str(env_dir)], check=True)
    python = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run([str(python), "-m", "pip", "install", "--quiet",
                    "--disable-pip-version-check", "--require-hashes", "--no-deps",
                    "--only-binary=:all:", "-r", str(requirements)], check=True)
    frozen = subprocess.run([str(python), "-m", "pip", "list", "--format=json",
                             "--disable-pip-version-check"],
                            capture_output=True, check=True, text=True).stdout
    installed = {canonical(p["name"]): p["version"] for p in json.loads(frozen)}
    pip_version = installed.pop("pip", None)
    refuse_unless_exactly_pinned(installed, pinned(requirements.read_text(encoding="utf-8"),
                                                   os.name))
    return python, installed, pip_version


def build_once(python, export_dir, out_dir, epoch):
    source = out_dir / "source"
    shutil.copytree(export_dir, source)
    environment = dict(os.environ, SOURCE_DATE_EPOCH=str(epoch), PYTHONHASHSEED="0")
    subprocess.run([str(python), "-m", "build", "--wheel", "--no-isolation",
                    "--outdir", str(out_dir / "dist"), str(source / SDK_DIR)],
                   check=True, env=environment, capture_output=True)
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

        python, toolchain, pip_version = build_environment(work, requirements)
        first, first_sha = build_once(python, work / "export", work / "one", epoch)
        second, second_sha = build_once(python, work / "export", work / "two", epoch)
        refuse_unless_reproduced(first_sha, second_sha)

        args.out.mkdir(parents=True, exist_ok=True)
        shutil.copy2(first, args.out / first.name)
        identity = {
            "tag": args.tag,
            "commit": args.commit,
            "source_date_epoch": epoch,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "toolchain": {"build_requirements": toolchain, "installer_pip": pip_version,
                          "recipe_sha256": hashlib.sha256(
                              Path(__file__).read_bytes()).hexdigest(),
                          "requirements_sha256": hashlib.sha256(
                              requirements.read_bytes()).hexdigest()},
            "wheel": first.name,
            "sha256": first_sha,
            "builds_compared": 2,
        }
        (args.out / f"{args.tag}.release.json").write_text(
            json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(identity, indent=2))
    return identity


if __name__ == "__main__":
    main()
