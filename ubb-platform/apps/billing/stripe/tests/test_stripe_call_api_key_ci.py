"""CI guard (F4.4): every production ``stripe_call(`` invocation passes api_key=.

``stripe_call``'s api_key parameter is required keyword-only, so a missed call
site is a TypeError — but only when that code path actually runs. This AST scan
turns the omission into a commit-time failure instead: a forgotten api_key= is
exactly the bug class that silently routed sandbox traffic to live Stripe.
"""
import ast
from pathlib import Path

# apps/billing/stripe/tests/test_*.py -> ubb-platform/
PLATFORM_ROOT = Path(__file__).resolve().parents[4]

_EXCLUDED_DIR_NAMES = {"tests", "migrations", "__pycache__"}


def _iter_source_files():
    """Every production .py under apps/, api/, core/ (no tests, no migrations)."""
    for top in ("apps", "api", "core"):
        root = PLATFORM_ROOT / top
        for path in sorted(root.rglob("*.py")):
            rel = path.relative_to(PLATFORM_ROOT)
            if any(part in _EXCLUDED_DIR_NAMES for part in rel.parts):
                continue
            if path.name.startswith("test_") or path.name == "conftest.py":
                continue
            yield path, rel


def _is_stripe_call(node):
    f = node.func
    if isinstance(f, ast.Name):
        return f.id == "stripe_call"
    if isinstance(f, ast.Attribute):
        return f.attr == "stripe_call"
    return False


def _collect():
    violations, sites = [], 0
    for path, rel in _iter_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_stripe_call(node):
                sites += 1
                keywords = {kw.arg for kw in node.keywords}
                # None = a **splat, which may carry api_key — allowed.
                if "api_key" not in keywords and None not in keywords:
                    violations.append(f"{rel.as_posix()}:{node.lineno}")
    return violations, sites


def test_every_stripe_call_invocation_passes_api_key():
    violations, sites = _collect()
    # Guard against a vacuous pass from path-resolution breakage: the codebase
    # has 20+ production stripe_call sites today.
    assert sites >= 20, f"AST walker only found {sites} stripe_call invocations"
    assert not violations, (
        "stripe_call( without api_key= — every call site must pass "
        "api_key=api_key_for_tenant(<tenant in scope>) so sandbox flows can "
        "never silently use the live key:\n" + "\n".join(violations)
    )
