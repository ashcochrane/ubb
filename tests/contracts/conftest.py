"""Shared paths for the contract suite.

The only setup this suite needs is the git root on ``sys.path``, so
``import tools.vocabulary`` works when pytest is run from anywhere. There is no
Django setup, no database fixture and no settings module — see
``test_contract_suite_is_enforced.py``, which makes that a checked rule rather
than a habit.
"""

import sys
from pathlib import Path

# tests/contracts/conftest.py -> the git root.
#
# `_helpers.py` computes this same path independently rather than importing it
# from here. That is deliberate, not an oversight: this assignment has to run
# BEFORE anything can import `tools`, so it cannot live in a module that itself
# imports `tools`.
REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
