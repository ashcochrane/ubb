"""The SDK major a Blueprint names is the major of the SDK in this tree (#576).

An Integration Blueprint for the Python target says which SDK major the code
is generated against (`sdk_major_version`). That number is a constant in the
resolver, and the SDK's own version is a line in its `pyproject.toml` — two
surfaces stating one fact, with nothing between them but the owner's ruling
that the coordinated release is v3.

This holds them to each other, so the release that moves the SDK's major is
red here until the Blueprint names it. Read by AST rather than imported: this
suite runs without Django, and what is being compared is a value written in a
file.
"""

import ast
import re

from _helpers import REPO_ROOT

RESOLVER = REPO_ROOT / "ubb-platform" / "api" / "v1" / "integration_blueprint.py"
PYPROJECT = REPO_ROOT / "ubb-sdk" / "pyproject.toml"


def _majors_the_blueprint_names():
    """The values of `SDK_MAJOR_VERSION` in the resolver, as written."""
    tree = ast.parse(RESOLVER.read_text(encoding="utf-8"))
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and getattr(node.targets[0], "id", None) == "SDK_MAJOR_VERSION"):
            assert isinstance(node.value, ast.Dict), (
                "SDK_MAJOR_VERSION is no longer a literal mapping; this check "
                "reads the assignment and must be taught its new shape")
            return [ast.literal_eval(value) for value in node.value.values]
    raise AssertionError("the resolver no longer assigns SDK_MAJOR_VERSION")


def _the_major_that_ships():
    version = re.search(r'^version\s*=\s*"(\d+)\.\d+\.\d+"\s*$',
                        PYPROJECT.read_text(encoding="utf-8"), re.MULTILINE)
    assert version, "ubb-sdk/pyproject.toml states no version this can read"
    return int(version.group(1))


def test_the_python_target_names_the_major_of_the_sdk_in_this_tree():
    named = _majors_the_blueprint_names()

    # One target has an SDK and one has none, so the mapping holds exactly
    # one number and one absence.
    assert sorted(named, key=str) == sorted(
        [_the_major_that_ships(), None], key=str)
