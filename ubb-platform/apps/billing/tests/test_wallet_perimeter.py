"""#109 — the Wallet module perimeter pin (ADR-001 walker style).

Every wallet mutation path routes through ``apps/billing/wallets/`` (the
operations module and its private implementation). This test walks EVERY
non-test, non-migration ``.py`` under ``apps/``, ``core/`` AND ``api/`` and
asserts, for every file OUTSIDE the perimeter:

1. no import of ``apps.billing.wallets.grants`` — ``GrantLedger`` is private
   implementation of the module (issue #109 decision 1);
2. no write to a ``balance_micros`` attribute (``x.balance_micros = ...`` /
   ``+=`` / ``-=``) — the wallet's spendable cache moves only inside the
   module. The one allowlisted file writes the postpaid ``CustomerLedger``'s
   field of the same name, a different model;
3. no write to a grant lot's money buckets (``remaining_micros``,
   ``granted_micros``, ``expired_micros``, ``voided_micros``);
4. no manager mutation (``create`` / ``bulk_create`` / ``update`` /
   ``update_or_create`` / ``get_or_create`` / ``delete``) rooted at
   ``WalletTransaction`` / ``CreditGrant`` / ``GrantAllocation`` — ledger rows
   and lots are born and mutated only behind the seam (reads stay free);
5. no ``LiveLedgerService.credit`` call — the Tier-2 credit mirror is derived
   from the op's balance delta INSIDE the module (decision 4; the five
   hand-wired sites died with #109). The one sanctioned non-ledger site is
   ``HoldService.settle`` (a hold release is not a ledger movement).

Instance-level ``.save()`` on a fetched model can't be attributed statically —
rules 2/3 cover the fields such a write would have to touch first, which is
what makes the pin bite in practice.
"""
import ast
from pathlib import Path

# apps/billing/tests/test_wallet_perimeter.py -> ubb-platform/
PLATFORM_ROOT = Path(__file__).resolve().parents[3]

ISSUE = "issue #109 (the Wallet module decision record)"

# The module: everything under apps/billing/wallets/ (operations.py + private
# implementation + the beat tasks that are part of the module's surface).
PERIMETER_PREFIX = "apps/billing/wallets/"

GRANTS_MODULE = "apps.billing.wallets.grants"

# Rule 2 allowlist: the postpaid receivable ledger has its own balance_micros
# column (apps/billing/invoicing/models.py:CustomerLedger) — a different
# model, deliberately outside the wallet seam.
BALANCE_WRITE_ALLOWLIST = frozenset({
    "apps/billing/invoicing/services/postpaid_service.py",
})

GRANT_MONEY_FIELDS = frozenset({
    "remaining_micros", "granted_micros", "expired_micros", "voided_micros",
})

LEDGER_MODELS = frozenset({"WalletTransaction", "CreditGrant", "GrantAllocation"})
MANAGER_MUTATORS = frozenset({
    "create", "bulk_create", "update", "update_or_create", "get_or_create",
    "delete",
})

# Rule 5 allowlist: the ONE sanctioned non-ledger LiveLedgerService.credit
# site (a hold release is not a ledger movement). Defining credit() is free —
# only `LiveLedgerService.credit(...)` call sites are pinned.
MIRROR_ALLOWLIST = frozenset({
    "apps/billing/gating/services/hold_service.py",
})

_EXCLUDED_DIR_NAMES = {"tests", "migrations", "__pycache__"}

RULE_GRANTS_IMPORT = "grants-import"
RULE_BALANCE_WRITE = "balance-write"
RULE_GRANT_FIELD_WRITE = "grant-field-write"
RULE_LEDGER_MUTATION = "ledger-manager-mutation"
RULE_MIRROR_CALL = "live-mirror-call"


def _iter_source_files():
    """Every production .py under apps/, core/ and api/ (no tests/migrations)."""
    for top in ("apps", "core", "api"):
        for path in sorted((PLATFORM_ROOT / top).rglob("*.py")):
            rel = path.relative_to(PLATFORM_ROOT)
            if any(part in _EXCLUDED_DIR_NAMES for part in rel.parts):
                continue
            if path.name == "conftest.py" or path.name.startswith("test_"):
                continue
            yield path, rel


def _resolve_import(node, module_parts):
    """Absolute dotted bases for an Import/ImportFrom (relative resolved)."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if node.level:  # relative import: anchor to the source package
        anchor = module_parts[: max(0, len(module_parts) - (node.level - 1))]
        suffix = node.module.split(".") if node.module else []
        base = ".".join(anchor + suffix)
    else:
        base = node.module or ""
    out = []
    for alias in node.names:
        out.append(f"{base}.{alias.name}" if base else alias.name)
        out.append(base)
    return out


def _assign_targets(node):
    if isinstance(node, ast.Assign):
        return node.targets
    if isinstance(node, (ast.AugAssign, ast.AnnAssign)):
        return [node.target]
    return []


def _manager_root(func):
    """For a Call func node, walk the attribute/call chain looking for
    ``<Name in LEDGER_MODELS>.objects`` at its root. Handles chains like
    ``CreditGrant.objects.filter(...).update(...)``."""
    node = func
    saw_objects = False
    while True:
        if isinstance(node, ast.Attribute):
            if node.attr == "objects":
                saw_objects = True
            node = node.value
        elif isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.Name):
            return node.id if saw_objects and node.id in LEDGER_MODELS else None
        else:
            return None


def check_source(tree, label, module_parts):
    """Return (rule, message) violations for one parsed file."""
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for dotted in _resolve_import(node, module_parts):
                if dotted == GRANTS_MODULE or dotted.startswith(GRANTS_MODULE + "."):
                    violations.append((RULE_GRANTS_IMPORT, (
                        f"{label}:{node.lineno} imports {GRANTS_MODULE} — "
                        f"GrantLedger is private to the wallet module; call "
                        f"apps.billing.wallets.operations — see {ISSUE}")))
                    break
        for target in _assign_targets(node):
            if isinstance(target, ast.Attribute):
                if target.attr == "balance_micros":
                    violations.append((RULE_BALANCE_WRITE, (
                        f"{label}:{node.lineno} writes .balance_micros — "
                        f"wallet balances move only through "
                        f"apps.billing.wallets.operations — see {ISSUE}")))
                elif target.attr in GRANT_MONEY_FIELDS:
                    violations.append((RULE_GRANT_FIELD_WRITE, (
                        f"{label}:{node.lineno} writes .{target.attr} — grant "
                        f"lot buckets move only inside the wallet module — "
                        f"see {ISSUE}")))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in MANAGER_MUTATORS:
                root = _manager_root(node.func.value)
                if root is not None:
                    violations.append((RULE_LEDGER_MUTATION, (
                        f"{label}:{node.lineno} calls {root}.objects…"
                        f".{node.func.attr}(...) — ledger rows and lots are "
                        f"created/mutated only behind the wallet seam — "
                        f"see {ISSUE}")))
            if (node.func.attr == "credit"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "LiveLedgerService"):
                violations.append((RULE_MIRROR_CALL, (
                    f"{label}:{node.lineno} calls LiveLedgerService.credit — "
                    f"the credit mirror is derived inside the wallet module "
                    f"(HoldService.settle is the one sanctioned non-ledger "
                    f"site) — see {ISSUE}")))
    return violations


def _collect():
    violations = []
    scanned = set()
    for path, rel in _iter_source_files():
        label = rel.as_posix()
        if label.startswith(PERIMETER_PREFIX):
            continue  # inside the module
        module_parts = list(rel.with_suffix("").parts)
        if module_parts[-1] == "__init__":
            module_parts = module_parts[:-1]
        else:
            module_parts = module_parts[:-1]  # containing package
        scanned.add(label)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for rule, msg in check_source(tree, label, module_parts):
            if rule == RULE_BALANCE_WRITE and label in BALANCE_WRITE_ALLOWLIST:
                continue
            if rule == RULE_MIRROR_CALL and label in MIRROR_ALLOWLIST:
                continue
            violations.append((rule, msg))
    return violations, scanned


_VIOLATIONS, _SCANNED = _collect()


def _failures(rule):
    return "\n".join(msg for r, msg in _VIOLATIONS if r == rule)


def test_walker_actually_sees_the_codebase():
    """Guard against vacuous passes from path-resolution breakage."""
    assert len(_SCANNED) > 100, f"only scanned {len(_SCANNED)} files"
    for expected in (
        "apps/billing/handlers.py",
        "apps/billing/topups/services.py",
        "apps/billing/connectors/stripe/webhooks.py",
        "api/v1/billing_endpoints.py",
    ):
        assert expected in _SCANNED, f"walker did not visit {expected}"
    # The perimeter itself is excluded, not scanned.
    assert not any(f.startswith(PERIMETER_PREFIX) for f in _SCANNED)


def test_grantledger_is_private_to_the_module():
    assert not _failures(RULE_GRANTS_IMPORT), "\n" + _failures(RULE_GRANTS_IMPORT)


def test_no_balance_writes_outside_the_module():
    assert not _failures(RULE_BALANCE_WRITE), "\n" + _failures(RULE_BALANCE_WRITE)


def test_no_grant_bucket_writes_outside_the_module():
    assert not _failures(RULE_GRANT_FIELD_WRITE), (
        "\n" + _failures(RULE_GRANT_FIELD_WRITE))


def test_no_ledger_manager_mutations_outside_the_module():
    assert not _failures(RULE_LEDGER_MUTATION), (
        "\n" + _failures(RULE_LEDGER_MUTATION))


def test_no_live_mirror_calls_outside_the_module():
    assert not _failures(RULE_MIRROR_CALL), "\n" + _failures(RULE_MIRROR_CALL)


def test_allowlists_are_still_real_files():
    """No stale allowlist entry: every exemption maps to a live source file."""
    for label in BALANCE_WRITE_ALLOWLIST | MIRROR_ALLOWLIST:
        assert (PLATFORM_ROOT / label).is_file(), f"stale allowlist entry {label}"


# ---------------------------------------------------------------------------
# Negative controls: prove each rule actually fires on synthetic sources.
# ---------------------------------------------------------------------------


def _check_snippet(source, module="apps.billing.synthetic.module"):
    tree = ast.parse(source)
    label = module.replace(".", "/") + ".py"
    return check_source(tree, label, module.split(".")[:-1])


def test_negative_control_grants_import_is_flagged():
    for src in (
        "from apps.billing.wallets.grants import GrantLedger\n",
        "import apps.billing.wallets.grants\n",
        "def lazy():\n    from apps.billing.wallets.grants import GrantLedger\n",
    ):
        hits = _check_snippet(src)
        assert [r for r, _ in hits] == [RULE_GRANTS_IMPORT], src


def test_negative_control_relative_grants_import_is_flagged():
    # In apps/billing/topups/services.py: from ..wallets import grants ->
    # apps.billing.wallets.grants.
    hits = _check_snippet("from ..wallets import grants\n",
                          module="apps.billing.topups.services")
    assert [r for r, _ in hits] == [RULE_GRANTS_IMPORT]


def test_negative_control_balance_write_is_flagged():
    for src in (
        "wallet.balance_micros = 0\n",
        "wallet.balance_micros -= amount\n",
        "wallet.balance_micros += amount\n",
    ):
        hits = _check_snippet(src)
        assert [r for r, _ in hits] == [RULE_BALANCE_WRITE], src


def test_negative_control_grant_bucket_write_is_flagged():
    hits = _check_snippet("grant.remaining_micros = 0\n")
    assert [r for r, _ in hits] == [RULE_GRANT_FIELD_WRITE]


def test_negative_control_manager_mutation_is_flagged():
    for src in (
        "WalletTransaction.objects.create(wallet=w)\n",
        "CreditGrant.objects.filter(id=1).update(status='voided')\n",
        "GrantAllocation.objects.bulk_create(rows)\n",
    ):
        hits = _check_snippet(src)
        assert [r for r, _ in hits] == [RULE_LEDGER_MUTATION], src


def test_negative_control_mirror_call_is_flagged():
    hits = _check_snippet("LiveLedgerService.credit(oid, tenant, amt)\n")
    assert [r for r, _ in hits] == [RULE_MIRROR_CALL]


def test_positive_control_reads_are_not_flagged():
    assert not _check_snippet(
        "from apps.billing.wallets.models import Wallet, WalletTransaction\n"
        "w = Wallet.objects.get(customer=c)\n"
        "rows = WalletTransaction.objects.filter(wallet=w).first()\n"
        "n = CreditGrant.objects.filter(wallet=w).count()\n"
        "b = w.balance_micros\n")
    # Other models' managers stay free.
    assert not _check_snippet("TopUpAttempt.objects.create(customer=c)\n")
    # Reading LiveLedgerService's other surface stays free.
    assert not _check_snippet("LiveLedgerService.read_stop(oid, tenant)\n")
