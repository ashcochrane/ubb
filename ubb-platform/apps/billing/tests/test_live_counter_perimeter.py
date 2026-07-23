"""#111 — the live-counter perimeter pins (ADR-001 walker style).

ONE module owns the Tier-2 Redis state: every key format, Lua script, TTL,
and the stop-flag cache live in ``apps/billing/gating/services/
live_counter.py``. This test walks EVERY non-test, non-migration ``.py``
under ``apps/``, ``core/`` AND ``api/`` and asserts, for every file OUTSIDE
the module:

1. no string literal spells a live-counter key family
   (``ubb:livebal`` / ``ubb:livespend`` / ``ubb:stop:`` / ``ubb:stopchan``
   / ``ubb:budget`` — the #111 DoD explicitly covers the new budget
   namespace). Together with rule 2 this also pins "never EVALs the
   module's Lua": the scripts are private constants and the keys they
   target are unspellable. Other ``ubb:*`` families (idem, cardver,
   markup…) belong to their own modules and are not this pin's concern.
2. no import of the module's private names (``_client``, key helpers, Lua
   sources) and no use of its test door (``Door`` — D4: TEST-ONLY; tests
   are outside this walk by construction).
3. no ``StopSignalState`` manager mutation (create/update/get_or_create/…)
   and no ``.episode_seq`` attribute write outside StopSignalService — the
   #111 D5 addition: every StopSignalState WRITE goes through the one
   emission choke point (reads stay free: patrol re-mints, queries report).
   Instance-level ``.save()`` can't be attributed statically — the manager
   rule plus the episode_seq field rule cover what such a write would have
   to touch first (the wallet-perimeter precedent).

Key formats themselves are frozen in the module's OWN pin test
(``apps/billing/gating/tests/test_live_counter_pins.py``) — the one
sanctioned home for the literals.
"""
import ast
from pathlib import Path

# apps/billing/tests/test_live_counter_perimeter.py -> ubb-platform/
PLATFORM_ROOT = Path(__file__).resolve().parents[3]

ISSUE = "issue #111 (one live counter)"

COUNTER_MODULE_LABEL = "apps/billing/gating/services/live_counter.py"

SIGNAL_MODULE_LABEL = "apps/billing/gating/services/stop_signal_service.py"

# The pinned key families. "ubb:stop:" keeps its colon so the idem/cardver
# style families can never collide; "ubb:stopchan" needs none (no shorter
# family shares the prefix).
KEY_FAMILIES = ("ubb:livebal", "ubb:livespend", "ubb:stop:", "ubb:stopchan",
                "ubb:budget")

MANAGER_MUTATORS = frozenset({
    "create", "bulk_create", "bulk_update", "update", "update_or_create",
    "get_or_create", "delete",
})

RULE_KEY_LITERAL = "key-family-literal"
RULE_PRIVATE_IMPORT = "private-import"
RULE_DOOR_USE = "test-door-use"
RULE_SIGNAL_MUTATION = "signal-manager-mutation"
RULE_EPISODE_WRITE = "episode-seq-write"

_EXCLUDED_DIR_NAMES = {"tests", "migrations", "__pycache__"}


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


def _string_constants(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node


def _manager_root(func):
    """For a Call func node, walk the attribute/call chain looking for
    ``StopSignalState.objects`` at its root (handles
    ``StopSignalState.objects.filter(...).update(...)`` chains)."""
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
            return node.id if saw_objects and node.id == "StopSignalState" else None
        else:
            return None


def _assign_targets(node):
    if isinstance(node, ast.Assign):
        return node.targets
    if isinstance(node, (ast.AugAssign, ast.AnnAssign)):
        return [node.target]
    return []


def check_source(tree, label):
    """Return (rule, message) violations for one parsed file."""
    violations = []
    outside_counter = label != COUNTER_MODULE_LABEL
    outside_signal = label != SIGNAL_MODULE_LABEL
    for node in ast.walk(tree):
        if outside_counter and isinstance(node, ast.Constant) \
                and isinstance(node.value, str):
            for family in KEY_FAMILIES:
                if family in node.value:
                    violations.append((RULE_KEY_LITERAL, (
                        f"{label}:{node.lineno} spells '{family}' — the live "
                        f"counter's keyspace is private to "
                        f"{COUNTER_MODULE_LABEL}; go through its ops (or the "
                        f"test door, tests only) — see {ISSUE}")))
                    break
        if outside_counter and isinstance(node, ast.ImportFrom) \
                and (node.module or "").split(".")[-1] == "live_counter":
            # Matches absolute AND relative spellings (`from .live_counter
            # import _client` resolves module="live_counter" at level 1).
            for alias in node.names:
                if alias.name.startswith("_"):
                    violations.append((RULE_PRIVATE_IMPORT, (
                        f"{label}:{node.lineno} imports {alias.name} from the "
                        f"live counter — privates stay private; use the "
                        f"public ops — see {ISSUE}")))
                elif alias.name == "Door":
                    violations.append((RULE_DOOR_USE, (
                        f"{label}:{node.lineno} imports the test door — Door "
                        f"is TEST-ONLY (D4) — see {ISSUE}")))
        if outside_counter and isinstance(node, ast.Attribute) \
                and node.attr == "Door":
            violations.append((RULE_DOOR_USE, (
                f"{label}:{node.lineno} touches .Door — the test door is "
                f"TEST-ONLY (D4) — see {ISSUE}")))
        if outside_signal:
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr in MANAGER_MUTATORS \
                    and _manager_root(node.func.value) is not None:
                violations.append((RULE_SIGNAL_MUTATION, (
                    f"{label}:{node.lineno} calls StopSignalState.objects…"
                    f".{node.func.attr}(...) — every StopSignalState write "
                    f"goes through StopSignalService (reads stay free) — "
                    f"see {ISSUE}")))
            for target in _assign_targets(node):
                if isinstance(target, ast.Attribute) and target.attr == "episode_seq":
                    violations.append((RULE_EPISODE_WRITE, (
                        f"{label}:{node.lineno} writes .episode_seq — the "
                        f"episode counter moves only inside StopSignalService "
                        f"— see {ISSUE}")))
    return violations


def _collect():
    violations = []
    scanned = set()
    for path, rel in _iter_source_files():
        label = rel.as_posix()
        scanned.add(label)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        violations.extend(check_source(tree, label))
    return violations, scanned


_VIOLATIONS, _SCANNED = _collect()


def _failures(rule):
    return "\n".join(msg for r, msg in _VIOLATIONS if r == rule)


def test_walker_actually_sees_the_codebase():
    """Guard against vacuous passes from path-resolution breakage."""
    assert len(_SCANNED) > 100, f"only scanned {len(_SCANNED)} files"
    for expected in (
        COUNTER_MODULE_LABEL,
        SIGNAL_MODULE_LABEL,
        "apps/billing/gating/repair.py",
        "apps/billing/queries.py",
        "api/v1/tenant_endpoints.py",
    ):
        assert expected in _SCANNED, f"walker did not visit {expected}"


def test_no_key_family_literal_outside_the_module():
    assert not _failures(RULE_KEY_LITERAL), "\n" + _failures(RULE_KEY_LITERAL)


def test_no_private_imports_from_the_module():
    assert not _failures(RULE_PRIVATE_IMPORT), (
        "\n" + _failures(RULE_PRIVATE_IMPORT))


def test_the_test_door_stays_out_of_production():
    assert not _failures(RULE_DOOR_USE), "\n" + _failures(RULE_DOOR_USE)


def test_no_signal_state_writes_outside_stop_signal_service():
    assert not _failures(RULE_SIGNAL_MUTATION), (
        "\n" + _failures(RULE_SIGNAL_MUTATION))


def test_no_episode_seq_writes_outside_stop_signal_service():
    assert not _failures(RULE_EPISODE_WRITE), (
        "\n" + _failures(RULE_EPISODE_WRITE))


# ---------------------------------------------------------------------------
# Negative controls: prove each rule actually fires on synthetic sources.
# ---------------------------------------------------------------------------


def _check_snippet(source, label="apps/billing/synthetic/module.py"):
    return check_source(ast.parse(source), label)


def test_negative_control_key_literal_is_flagged():
    for src in (
        'key = f"ubb:livebal:{owner_id}"\n',
        'key = "ubb:livespend:" + str(o) + ":" + label\n',
        'client.delete("ubb:stop:%s" % o)\n',
        'chan = f"ubb:stopchan:{o}"\n',
        'k = f"ubb:budget:{cid}:{label}"\n',
        '"""docstring spelling ubb:livebal:{owner} counts too"""\n',
    ):
        hits = _check_snippet(src)
        assert [r for r, _ in hits] == [RULE_KEY_LITERAL], src


def test_negative_control_private_import_is_flagged():
    for src in (
        "from apps.billing.gating.services.live_counter import _client\n",
        "from apps.billing.gating.services.live_counter import _livebal_key\n",
        "from .live_counter import _client\n",  # relative spelling
        "def lazy():\n"
        "    from apps.billing.gating.services.live_counter import _SEED_AND_DECR\n",
    ):
        hits = _check_snippet(src)
        assert [r for r, _ in hits] == [RULE_PRIVATE_IMPORT], src


def test_negative_control_door_use_is_flagged():
    hits = _check_snippet(
        "from apps.billing.gating.services.live_counter import Door\n")
    assert [r for r, _ in hits] == [RULE_DOOR_USE]
    hits = _check_snippet("live_counter.Door.set_balance(o, 5)\n")
    assert [r for r, _ in hits] == [RULE_DOOR_USE]


def test_negative_control_signal_mutation_is_flagged():
    for src in (
        "StopSignalState.objects.create(owner_id=o)\n",
        "StopSignalState.objects.filter(tenant_id=t).update(state='cleared')\n",
        "StopSignalState.objects.get_or_create(owner_id=o)\n",
    ):
        hits = _check_snippet(src)
        assert [r for r, _ in hits] == [RULE_SIGNAL_MUTATION], src


def test_negative_control_episode_write_is_flagged():
    hits = _check_snippet("row.episode_seq += 1\n")
    assert [r for r, _ in hits] == [RULE_EPISODE_WRITE]


def test_positive_control_sanctioned_shapes_stay_free():
    # Reads of the signal ledger stay free (patrol re-mints, queries report).
    assert not _check_snippet(
        "rows = StopSignalState.objects.filter(tenant_id=t)\n"
        "row = StopSignalState.objects.select_for_update().get(id=rid)\n"
        "n = row.episode_seq\n")
    # The module itself may spell its own keys and mutate nothing else.
    assert not _check_snippet('key = f"ubb:livebal:{owner_id}"\n',
                              label=COUNTER_MODULE_LABEL)
    # StopSignalService itself owns the writes.
    assert not _check_snippet(
        "StopSignalState.objects.filter(tenant_id=t).update(state='cleared')\n",
        label=SIGNAL_MODULE_LABEL)
    # Other ubb: families (idem, cardver, markup…) belong to their modules.
    assert not _check_snippet('k = f"ubb:idem:{tenant_id}:{key}"\n')
    # Public-op imports stay free.
    assert not _check_snippet(
        "from apps.billing.gating.services.live_counter import LiveCounter\n")
