"""AST-enforced product dependency matrix.

UBB is four products (metering, billing, subscriptions, referrals) on a shared
platform kernel (``apps/platform``) plus ``core/`` plumbing and the ``api/``
composition layer. This test walks EVERY non-test, non-migration ``.py`` under
``apps/`` and ``core/`` and asserts the dependency matrix recorded in
docs/architecture/2026-06-12-adr-001-product-boundaries.md:

1. No module under ``apps/`` or ``core/`` imports the ``api`` composition layer.
2. ``apps/platform/**`` imports no product (platform is the kernel) — the only
   exemption is the dev-only seed command allowlisted below.
3. ``core/**`` imports only ``apps.platform.*`` among apps.
4. Product <-> product imports happen ONLY through the sanctioned channels:
   - ``apps.metering.queries`` (read contract, importable by any product),
   - billing -> ``apps.subscriptions.ports``,
   - subscriptions -> the "Stripe connector kit" (ADR-001 decision 5),
   - ``apps.platform.*`` and ``core.*`` (always allowed, see rule 1 of the ADR),
   - ``apps/<product>/api/**`` modules are composition-layer (ADR-001
     decision 4): they may import any product, but still never ``api.*``.

The walker visits ALL AST nodes, so lazy function-body imports (the historical
erosion vector — see the ADR's Context) are caught exactly like module-scope
imports. Relative imports are resolved to absolute module paths first.
"""
import ast
from pathlib import Path

# apps/platform/tests/test_product_boundaries.py -> ubb-platform/
PLATFORM_ROOT = Path(__file__).resolve().parents[3]

ADR = "docs/architecture/2026-06-12-adr-001-product-boundaries.md"

PLATFORM_KERNEL = "apps.platform"
PRODUCTS = ("apps.billing", "apps.metering", "apps.subscriptions", "apps.referrals")

# Channel: per-product read contracts (plain-data queries). Importable by ANY product.
SHARED_READ_CONTRACTS = ("apps.metering.queries", "apps.billing.queries")

# Channels sanctioned per importing product (ADR-001 decision 3 + 5).
PAIR_CHANNELS = {
    # billing consumes the subscriptions port (invoice payment-failed fast path
    # + invoice repair) — the only per-pair ports.py module today.
    "apps.billing": ("apps.subscriptions.ports",),
    # The "Stripe connector kit" (ADR-001 decision 5): shared Stripe plumbing
    # that lives in billing but is deliberately importable by subscriptions —
    # the stripe_call wrapper + API-version pin, the ONE StripeWebhookEvent
    # dedup table shared across both webhook endpoints, and the AR
    # transition/URL helpers. Future home: apps/connectors/ if products split.
    "apps.subscriptions": (
        "apps.billing.stripe.services.stripe_service",
        "apps.billing.stripe.models",
        "apps.billing.connectors.stripe.invoice_routing",
    ),
}

# Dev-only management commands exempt from rule 2 (ADR-001 decision 6).
PLATFORM_FILE_ALLOWLIST = frozenset({
    "apps/platform/tenants/management/commands/seed_dev_data.py",
})

_EXCLUDED_DIR_NAMES = {"tests", "migrations", "__pycache__"}

# Rule identifiers (used to bucket violations per test below).
RULE_API = "imports-api-layer"
RULE_PLATFORM = "platform-imports-product"
RULE_CORE = "core-imports-product"
RULE_CROSS = "unsanctioned-cross-product"


def _iter_source_files():
    """Every production .py under apps/ and core/ (no tests, no migrations)."""
    for top in ("apps", "core"):
        for path in sorted((PLATFORM_ROOT / top).rglob("*.py")):
            rel = path.relative_to(PLATFORM_ROOT)
            if any(part in _EXCLUDED_DIR_NAMES for part in rel.parts):
                continue
            if path.name == "conftest.py" or path.name.startswith("test_"):
                continue
            yield path, rel


def _module_name(rel_path):
    """Dotted module path for a file, and whether it is a package __init__."""
    parts = list(rel_path.with_suffix("").parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts = parts[:-1]
    return ".".join(parts), is_package


def iter_import_edges(tree, module, is_package=False):
    """Yield (lineno, base, full) for every import statement ANYWHERE in the tree.

    ``base`` is the imported-from module (relative imports resolved against
    ``module``); ``full`` is the most specific dotted name (``base.alias`` for
    ``from X import y`` — y may itself be a submodule). Uses ast.walk, so
    imports inside function bodies / methods / conditionals are all visited.
    """
    pkg_parts = module.split(".") if module else []
    if not is_package and pkg_parts:
        pkg_parts = pkg_parts[:-1]  # containing package of a plain module
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name, alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import: anchor it to the source package
                anchor = pkg_parts[: max(0, len(pkg_parts) - (node.level - 1))]
                suffix = node.module.split(".") if node.module else []
                base = ".".join(anchor + suffix)
            else:
                base = node.module or ""
            for alias in node.names:
                full = f"{base}.{alias.name}" if base else alias.name
                yield node.lineno, base, full


def _domain(mod):
    """Map a dotted name to its boundary domain (exact-segment prefix match, so
    apps.billing_extra is NOT apps.billing)."""
    if not mod:
        return None
    if mod == "api" or mod.startswith("api."):
        return "api"
    if mod == "core" or mod.startswith("core."):
        return "core"
    if mod == PLATFORM_KERNEL or mod.startswith(PLATFORM_KERNEL + "."):
        return PLATFORM_KERNEL
    for product in PRODUCTS:
        if mod == product or mod.startswith(product + "."):
            return product
    return None


def _matches_channel(channel, base, full):
    return (
        base == channel
        or base.startswith(channel + ".")
        or full == channel
        or full.startswith(channel + ".")
    )


def _is_composition_module(module):
    """apps/<product>/api/** — the composition layer (ADR-001 decision 4)."""
    return any(
        module == f"{product}.api" or module.startswith(f"{product}.api.")
        for product in PRODUCTS
    )


def classify_edge(source_module, source_label, allowlisted, lineno, base, full):
    """Return (rule, message) if this import edge violates the matrix, else None."""
    target_domain = _domain(base) or _domain(full)
    if target_domain is None or target_domain == "core":
        return None  # stdlib / third-party / core (always allowed)
    target = base if _domain(base) is not None else full
    source_domain = _domain(source_module)

    if target_domain == "api":
        return (
            RULE_API,
            f"{source_label}:{lineno} imports {target} — apps/ and core/ must "
            f"never import the api composition layer — see {ADR}",
        )
    if target_domain == PLATFORM_KERNEL:
        return None  # anything may use the platform kernel

    # target is a product
    if source_domain == "core":
        return (
            RULE_CORE,
            f"{source_label}:{lineno} imports {target} — core/ may import only "
            f"apps.platform among apps — see {ADR}",
        )
    if source_domain == PLATFORM_KERNEL:
        if allowlisted:
            return None
        return (
            RULE_PLATFORM,
            f"{source_label}:{lineno} imports {target} — the platform kernel "
            f"must never import a product (use customers/hooks.py or the "
            f"outbox) — see {ADR}",
        )
    if source_domain == target_domain:
        return None  # within one product
    if source_domain is not None and _is_composition_module(source_module):
        return None  # apps/<product>/api is composition layer
    channels = SHARED_READ_CONTRACTS + PAIR_CHANNELS.get(source_domain, ())
    if any(_matches_channel(channel, base, full) for channel in channels):
        return None
    return (
        RULE_CROSS,
        f"{source_label}:{lineno} imports {target} — unsanctioned "
        f"cross-product dependency ({source_domain or source_module} -> "
        f"{target_domain}); use the outbox, a queries.py read contract, a "
        f"ports.py module, or a platform hook — see {ADR}",
    )


def _collect():
    """Parse the whole tree once; return (violations, scanned_modules)."""
    violations = []
    scanned = set()
    for path, rel in _iter_source_files():
        label = rel.as_posix()
        module, is_package = _module_name(rel)
        scanned.add(module)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        allowlisted = label in PLATFORM_FILE_ALLOWLIST
        for lineno, base, full in iter_import_edges(tree, module, is_package):
            hit = classify_edge(module, label, allowlisted, lineno, base, full)
            if hit is not None:
                violations.append(hit)
    return violations, scanned


_VIOLATIONS, _SCANNED = _collect()


def _failures(rule):
    return "\n".join(msg for r, msg in _VIOLATIONS if r == rule)


def test_walker_actually_sees_the_codebase():
    """Guard against vacuous passes from path-resolution breakage."""
    assert len(_SCANNED) > 100, f"only scanned {len(_SCANNED)} modules"
    for expected in (
        "apps.billing.handlers",
        "apps.metering.queries",
        "apps.subscriptions.ports",
        "apps.platform.customers.hooks",
        "core.auth",
    ):
        assert expected in _SCANNED, f"walker did not visit {expected}"


def test_no_module_imports_the_api_layer():
    assert not _failures(RULE_API), "\n" + _failures(RULE_API)


def test_platform_kernel_imports_no_product():
    assert not _failures(RULE_PLATFORM), "\n" + _failures(RULE_PLATFORM)


def test_core_imports_only_platform_among_apps():
    assert not _failures(RULE_CORE), "\n" + _failures(RULE_CORE)


def test_cross_product_imports_only_via_sanctioned_channels():
    assert not _failures(RULE_CROSS), "\n" + _failures(RULE_CROSS)


# ---------------------------------------------------------------------------
# Negative controls: prove the classifier actually flags violations (run on
# parsed snippets with synthetic module paths, not real files).
# ---------------------------------------------------------------------------

def _classify_snippet(source, module):
    tree = ast.parse(source)
    label = module.replace(".", "/") + ".py"
    return [
        hit
        for lineno, base, full in iter_import_edges(tree, module, is_package=False)
        for hit in [classify_edge(module, label, False, lineno, base, full)]
        if hit is not None
    ]


def test_negative_control_module_scope_violation_is_flagged():
    hits = _classify_snippet(
        "from apps.subscriptions.models import SubscriptionInvoice\n",
        "apps.billing.synthetic.module",
    )
    assert len(hits) == 1
    rule, message = hits[0]
    assert rule == RULE_CROSS
    assert "apps.subscriptions.models" in message
    assert ":1 " in message


def test_negative_control_lazy_function_body_import_is_flagged():
    hits = _classify_snippet(
        "def sneaky():\n"
        "    from apps.subscriptions.models import SubscriptionInvoice\n",
        "apps.billing.synthetic.module",
    )
    assert len(hits) == 1
    rule, message = hits[0]
    assert rule == RULE_CROSS
    assert ":2 " in message


def test_negative_control_relative_import_is_resolved_and_flagged():
    # In apps/billing/x/y.py, "from ...subscriptions import models" resolves
    # to apps.subscriptions(.models) and must be flagged.
    hits = _classify_snippet(
        "from ...subscriptions import models\n",
        "apps.billing.x.y",
    )
    assert len(hits) == 1
    assert hits[0][0] == RULE_CROSS


def test_negative_control_apps_to_api_inversion_is_flagged():
    hits = _classify_snippet(
        "def lazy():\n    from api.v1.webhooks import something\n",
        "apps.metering.synthetic.module",
    )
    assert len(hits) == 1
    assert hits[0][0] == RULE_API


def test_positive_control_sanctioned_channels_are_not_flagged():
    assert not _classify_snippet(
        "from apps.metering.queries import get_customer_cost_totals\n",
        "apps.billing.synthetic.module",
    )
    assert not _classify_snippet(
        "from apps.subscriptions.ports import repair_subscription_invoice\n",
        "apps.billing.synthetic.module",
    )
    assert not _classify_snippet(
        "from apps.billing.stripe.models import StripeWebhookEvent\n",
        "apps.subscriptions.synthetic.module",
    )
    assert not _classify_snippet(
        "from apps.platform.events.outbox import write_event\n",
        "apps.referrals.synthetic.module",
    )


def test_prefix_matching_does_not_confuse_sibling_names():
    # apps.billing_extra is NOT apps.billing: it is no product at all, so it
    # must be ignored, not allowed-or-flagged as billing.
    assert _domain("apps.billing_extra.models") is None
    # apps.metering.queries_extra is NOT the queries read contract.
    hits = _classify_snippet(
        "from apps.metering.queries_extra import leak\n",
        "apps.billing.synthetic.module",
    )
    assert len(hits) == 1
    assert hits[0][0] == RULE_CROSS
