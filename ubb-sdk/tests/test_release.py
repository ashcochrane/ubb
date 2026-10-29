"""Release-identity pins for the SDK's first release, v4.0.0 (#190, ADR-0026).

The release is cut at the cutover: an annotated tag, `sdk-v4.0.0`, and a wheel
built reproducibly from it by the committed recipe (`release/build_wheel.py`,
R2). Nothing was ever released before it — 3.0.0 was this tree's pre-release
number (#85 folded the generated core and the problem+json error model into it),
never tagged and never published. It must be stamped so a consumer can verify,
from the installed package alone, *both* which SDK release they hold *and* which
committed spec revision it was cut against. These pins guard that identity:

  * the SDK is v4.0.0;
  * pyproject's build version and the importable ``ubb.__version__`` never
    drift (a release that stamps one version but installs as another is a
    silent lie to the integrating tenant);
  * the spec-revision stamp is exposed on the public surface
    (``ubb.__spec_revision__`` / ``ubb.__spec_version__``); and
  * the release recipe builds in a pinned, hashed environment with a pinned
    backend, and refuses — shown here on planted inputs — a wrong Python, a
    lightweight or misplaced tag, a dirty export, an unpinned environment and
    two builds that differ.

That the stamp *matches the committed spec byte-for-byte* is pinned once, in
``tests/test_generated_core.py::TestSpecRevisionStamp`` — not re-derived here.
This file pins only that the public release surface re-exports it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
from pathlib import Path

import pytest

import ubb
from ubb import _spec_revision

SDK_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = SDK_ROOT / "pyproject.toml"
RECIPE = SDK_ROOT / "release" / "build_wheel.py"
BUILD_REQUIREMENTS = SDK_ROOT / "release" / "build-requirements.txt"


def _recipe():
    """The release recipe, loaded by path: it is a script beside the package,
    deliberately not part of the wheel it builds."""
    spec = importlib.util.spec_from_file_location("build_wheel", RECIPE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pyproject_version() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    assert m, "no version line in pyproject.toml"
    return m.group(1)


class TestReleaseVersion:
    """The SDK is v4.0.0, stamped consistently across build metadata and runtime."""

    def test_sdk_is_v4(self):
        # The release cut at the cutover (#190): the first one ever tagged.
        assert ubb.__version__ == "4.0.0"

    def test_pyproject_and_module_version_agree(self):
        assert _pyproject_version() == ubb.__version__

    def test_version_is_on_public_surface(self):
        assert "__version__" in ubb.__all__


class TestReleaseSpecStamp:
    """The spec-revision stamp is exposed on the public release surface."""

    def test_public_surface_re_exports_the_generated_stamp(self):
        assert ubb.__spec_revision__ == _spec_revision.SPEC_SHA256
        assert ubb.__spec_version__ == _spec_revision.SPEC_VERSION

    def test_spec_revision_is_a_sha256(self):
        assert re.fullmatch(r"[0-9a-f]{64}", ubb.__spec_revision__)

    def test_stamp_is_on_public_surface(self):
        assert "__spec_revision__" in ubb.__all__
        assert "__spec_version__" in ubb.__all__


class TestTheReleaseRecipe:
    """The reproducible wheel's recipe (R2; #190 §0.3 point 16), committed with
    the code it builds so the tag carries it."""

    def test_every_build_requirement_is_an_exact_hashed_pin(self):
        recipe = _recipe()
        pins = recipe.pinned(BUILD_REQUIREMENTS.read_text(encoding="utf-8"), "posix")
        assert set(pins) == {"build", "packaging", "pyproject-hooks", "setuptools"}
        windows = recipe.pinned(BUILD_REQUIREMENTS.read_text(encoding="utf-8"), "nt")
        assert set(windows) - set(pins) == {"colorama"}

    def test_the_backend_pyproject_names_is_the_pinned_one(self):
        """The backend the wheel is built by is one the lock installs."""
        recipe = _recipe()
        for os_name in ("posix", "nt"):
            recipe.refuse_unless_the_backend_is_locked(
                PYPROJECT.read_text(encoding="utf-8"),
                recipe.pinned(BUILD_REQUIREMENTS.read_text(encoding="utf-8"), os_name))

    def test_planted_a_backend_requirement_the_lock_does_not_pin_is_refused(self):
        """Changing or ADDING a build dependency outside the lock is refused
        before anything is installed: a range, another version, an unpinned
        extra package, or no requirement at all."""
        recipe = _recipe()
        pins = recipe.pinned(BUILD_REQUIREMENTS.read_text(encoding="utf-8"), "posix")
        for requires in ('["setuptools>=80"]', '["setuptools==81.0.0"]',
                         '["setuptools==80.9.0", "wheel==0.45.1"]', "[]"):
            planted = f'[build-system]\nrequires = {requires}\n'
            with pytest.raises(recipe.RefusedRelease, match="build-system|lock"):
                recipe.refuse_unless_the_backend_is_locked(planted, pins)

    def test_the_release_python_is_stated(self):
        assert _recipe().RELEASE_PYTHON == (3, 13)

    def test_planted_an_unpinned_requirement_is_refused(self):
        recipe = _recipe()
        for line in ("build>=1.2\n", "build==1.2.2.post1\n",
                     "build==1.2.2.post1 --hash=sha256:abc\n"):
            with pytest.raises(recipe.RefusedRelease, match="exact, hashed pin"):
                recipe.pinned(line, "posix")

    def test_planted_another_python_is_refused(self):
        recipe = _recipe()
        recipe.refuse_unless_the_release_python((3, 13, 1))
        with pytest.raises(recipe.RefusedRelease, match="Python 3.13"):
            recipe.refuse_unless_the_release_python((3, 12, 9))

    def test_planted_a_lightweight_or_misplaced_tag_is_refused(self):
        recipe = _recipe()
        commit = "a" * 40
        recipe.refuse_unless_an_annotated_tag_on("sdk-v4.0.0", "tag", commit, commit)
        cases = (
            (("sdk-v4.0.0", "commit", commit, commit), "not an annotated tag"),
            (("sdk-v4.0.0", "tag", "b" * 40, commit), "not the expected commit"),
            (("v4.0.0", "tag", commit, commit), "not an SDK release tag"),
            (("sdk-v4.0.0", "tag", commit, "abc123"), "full 40-character"),
        )
        for arguments, reason in cases:
            with pytest.raises(recipe.RefusedRelease, match=reason):
                recipe.refuse_unless_an_annotated_tag_on(*arguments)

    def test_planted_a_version_that_is_not_the_tags_is_refused(self):
        recipe = _recipe()
        recipe.refuse_unless_the_version_is_the_tags("sdk-v4.0.0", 'version = "4.0.0"\n')
        with pytest.raises(recipe.RefusedRelease, match="not 4.0.0"):
            recipe.refuse_unless_the_version_is_the_tags("sdk-v4.0.0", 'version = "3.0.0"\n')

    def test_planted_a_dirty_export_is_refused(self):
        recipe = _recipe()
        clean = {"ubb-sdk/a.py": b"x = 1\n"}
        listed = {"ubb-sdk/a.py": recipe.git_blob_id(b"x = 1\n")}
        recipe.refuse_unless_the_tags_tree(listed, clean)
        with pytest.raises(recipe.RefusedRelease, match="differs from the tag"):
            recipe.refuse_unless_the_tags_tree(listed, {"ubb-sdk/a.py": b"x = 1\r\n"})
        with pytest.raises(recipe.RefusedRelease, match="not the tag's tree"):
            recipe.refuse_unless_the_tags_tree(listed, {**clean, "ubb-sdk/b.py": b""})

    def test_the_blob_id_is_gits(self):
        # `git hash-object` of "x = 1\n", so the dirty-export check compares
        # against what `git ls-tree` actually lists.
        assert _recipe().git_blob_id(b"x = 1\n") == (
            "7d4290a117a4ddcc11daae7ea675841033830c8f")

    def test_planted_an_unpinned_environment_is_refused(self):
        recipe = _recipe()
        pins = {"build": "1.2.2.post1", "setuptools": "80.9.0"}
        recipe.refuse_unless_exactly_pinned(dict(pins), pins)
        for installed, reason in (
                ({**pins, "wheel": "0.45.1"}, "extra \\['wheel'\\]"),
                ({"build": "1.2.2.post1"}, "missing \\['setuptools'\\]"),
                ({**pins, "setuptools": "81.0.0"}, "different \\['setuptools'\\]")):
            with pytest.raises(recipe.RefusedRelease, match=reason):
                recipe.refuse_unless_exactly_pinned(installed, pins)

    def test_planted_an_installer_in_the_environment_is_refused(self):
        """No package is set aside: the environment is created without pip, so
        a pip found in it is an extra like any other."""
        recipe = _recipe()
        pins = {"build": "1.2.2.post1", "setuptools": "80.9.0"}
        with pytest.raises(recipe.RefusedRelease, match="extra \\['pip'\\]"):
            recipe.refuse_unless_exactly_pinned({**pins, "pip": "26.1.2"}, pins)

    def test_no_outside_python_setting_reaches_the_build(self):
        recipe = _recipe()
        builder = {"PATH": "/usr/bin", "SystemRoot": "C:\\Windows", "HOME": "/home/x",
                   "PYTHONPATH": "/elsewhere", "PYTHONSTARTUP": "/x.py",
                   "PYTHONHASHSEED": "random", "PIP_INDEX_URL": "https://mirror",
                   "pip_extra_index_url": "https://other",
                   "SETUPTOOLS_SCM_PRETEND_VERSION": "9.9.9",
                   "SETUPTOOLS_USE_DISTUTILS": "stdlib", "DISTUTILS_DEBUG": "1",
                   "_PYPROJECT_HOOKS_BUILD_BACKEND": "other", "VIRTUAL_ENV": "/venv",
                   "CONDA_PREFIX": "/conda"}

        assert recipe.release_environment(builder) == {
            "PATH": "/usr/bin", "SystemRoot": "C:\\Windows", "HOME": "/home/x",
            "PYTHONHASHSEED": "0", "PYTHONNOUSERSITE": "1", "PYTHONUTF8": "1"}

    def test_the_evidence_names_the_tag_the_commit_the_python_the_lock_and_the_wheel(self):
        recipe = _recipe()
        lock = BUILD_REQUIREMENTS.read_bytes()
        identity = recipe.release_identity(
            tag="sdk-v4.0.0", commit="a" * 40, epoch=1, python_version="3.13.14",
            platform_name="any", lock_bytes=lock,
            installed={"setuptools": "80.9.0", "build": "1.2.2.post1"},
            installer="26.1.2", recipe_bytes=b"recipe",
            wheel_name="ubb_sdk-4.0.0-py3-none-any.whl", wheel_sha256="f" * 64)

        assert (identity["tag"], identity["commit"]) == ("sdk-v4.0.0", "a" * 40)
        assert identity["python"] == {"release": "3.13", "exact": "3.13.14"}
        assert identity["lock"]["path"] == "ubb-sdk/release/build-requirements.txt"
        assert identity["lock"]["sha256"] == hashlib.sha256(lock).hexdigest()
        assert list(identity["lock"]["installed"]) == ["build", "setuptools"]
        assert identity["installer"] == {"pip": "26.1.2",
                                         "in_the_build_environment": False}
        assert (identity["wheel"], identity["sha256"]) == (
            "ubb_sdk-4.0.0-py3-none-any.whl", "f" * 64)
        assert identity["builds_compared"] == 2

    def test_planted_two_different_builds_are_refused(self):
        recipe = _recipe()
        recipe.refuse_unless_reproduced("ab", "ab")
        with pytest.raises(recipe.RefusedRelease, match="two builds of one tag differ"):
            recipe.refuse_unless_reproduced("ab", "cd")

    def test_the_recipes_working_copy_is_lf_on_every_platform(self):
        """The recipe compares its own bytes with the tag's LF blob, so the
        repository keeps it LF in every working tree, whatever a checkout's
        core.autocrlf is — and the copy that runs here is LF."""
        attributes = (SDK_ROOT.parent / ".gitattributes").read_text(encoding="utf-8")
        assert re.search(r"(?m)^ubb-sdk/release/\*\* text eol=lf$", attributes)
        assert b"\r\n" not in (SDK_ROOT / "release" / "build_wheel.py").read_bytes()

    def test_planted_a_recipe_that_is_not_the_tags_is_refused(self):
        """The pins and the recipe are the TAG's: an edited local copy of either
        never builds a release (the recipe running is compared with the one the
        export carries, and installs the export's pins)."""
        recipe = _recipe()
        recipe.refuse_unless_the_tags_recipe(b"recipe", b"recipe")
        with pytest.raises(recipe.RefusedRelease, match="not the tag's own recipe"):
            recipe.refuse_unless_the_tags_recipe(b"edited recipe", b"recipe")
        with pytest.raises(recipe.RefusedRelease, match="carries no"):
            recipe.refuse_unless_the_tags_recipe(b"recipe", None)
