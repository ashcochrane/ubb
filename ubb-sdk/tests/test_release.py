"""Release-identity pins for the coordinated v3.0 cut (issue #85).

The v3.0 release carries the generated core (#84) and the new problem+json
error model (#78) together, in one coordinated breaking release. It must be
stamped so a consumer can verify, from the installed package alone, *both*
which SDK release they hold *and* which committed spec revision it was cut
against. These pins guard that release identity:

  * the SDK is v3.0 — the clean pre-launch cut (#65);
  * pyproject's build version and the importable ``ubb.__version__`` never
    drift (a release that stamps 3.0.0 but installs as 2.x is a silent lie to
    the one integrating tenant); and
  * the spec-revision stamp is exposed on the public surface
    (``ubb.__spec_revision__`` / ``ubb.__spec_version__``).

That the stamp *matches the committed spec byte-for-byte* is pinned once, in
``tests/test_generated_core.py::TestSpecRevisionStamp`` — not re-derived here.
This file pins only that the public release surface re-exports it.
"""

from __future__ import annotations

import re
from pathlib import Path

import ubb
from ubb import _spec_revision

SDK_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = SDK_ROOT / "pyproject.toml"


def _pyproject_version() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    assert m, "no version line in pyproject.toml"
    return m.group(1)


class TestReleaseVersion:
    """The SDK is v3.0, stamped consistently across build metadata and runtime."""

    def test_sdk_is_v3(self):
        # This ticket IS the v3.0 cut — the single coordinated breaking release.
        assert ubb.__version__ == "3.0.0"

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
