"""G20 — migrations carry their data, from the cutover onward (ADR-0007 §1).

ADR-0007 §1 binds "from the cutover squash onward": a rename is `RenameField` /
`RenameModel`, never a drop and an add; a data move is an explicit `RunPython`
with a reverse where one is possible; a drop states its reason in the migration.
Before the squash the rule did not apply, and that exemption is spent (#190,
ADR-0026). This module is the check behind it.

**WHAT IT HOLDS.** Every migration AFTER the fresh initial set — the 26 files the
cutover left, named in :data:`FRESH_INITIAL_SET` — is read with `ast` (this suite
has no Django), and:

1. **A suspected rename is refused.** Within ONE app, a drop and an add on the
   same model — `RemoveField` + `AddField` — or a `DeleteModel` + `CreateModel`,
   found in the same migration OR in two ADJACENT migrations of that app (in
   either order), is a disguised rename whatever the names, types or options of
   the two sides: an "obvious rename with a type adjustment" is still a drop of
   the column's rows (§0.3 point 9). It passes only where one of the two
   migrations declares, in a module-level `NOT_A_RENAME = {"<model>.<field>":
   "<reason>"}` (or `{"<Model>": "<reason>"}` for a model) keyed by the DROPPED
   side, that it is not one, and why.
2. **A drop states its reason.** Every `RemoveField` / `DeleteModel` is named in
   a module-level `DROPS = {"<model>.<field>" | "<Model>": "<reason>"}` with a
   non-empty reason.
3. **A data step is reversible or says why not.** Every `RunPython` names a
   reverse, and so does every `RunSQL`; otherwise the module declares
   `IRREVERSIBLE = "<reason>"`.

**WHAT IT DOES NOT HOLD — ITS SCOPE, STATED (§0.3 point 9).** The detection is
static and deliberately narrow, and the claim above is exactly as wide as it:

- a drop and an add MORE than one migration apart in an app are not paired;
- a field dropped from one model and added to ANOTHER, or across apps, is not
  paired;
- operations inside `SeparateDatabaseAndState.state_operations` are not read (they
  move no rows); its `database_operations` are;
- raw SQL (`RunSQL`) is checked only for a reverse — a column dropped by hand-
  written SQL is not recognised as a drop;
- a `RunPython` reverse is accepted as written: whether it truly restores the
  data is a review question, not a static one.

So G20 makes the anti-pattern ADR-0007 §1 names impossible to write by
splitting it into two files; it is not a semantic migration engine, and its
manifest row says the same.
"""

import ast
import re
from pathlib import Path

from _helpers import REPO_ROOT

PLATFORM = REPO_ROOT / "ubb-platform"

#: THE FRESH INITIAL SET — the migrations the cutover left (#190, ADR-0026), and
#: the boundary G20 holds from. A generated `0001_initial` per app, and the six
#: hand-written rules migrations that carry the database's triggers. Every
#: migration NOT named here is held.
FRESH_INITIAL_SET = frozenset({
    "ubb-platform/apps/billing/gating/migrations/0001_initial.py",
    "ubb-platform/apps/billing/invoicing/migrations/0001_initial.py",
    "ubb-platform/apps/billing/stripe/migrations/0001_initial.py",
    "ubb-platform/apps/billing/tenant_billing/migrations/0001_initial.py",
    "ubb-platform/apps/billing/topups/migrations/0001_initial.py",
    "ubb-platform/apps/billing/wallets/migrations/0001_initial.py",
    "ubb-platform/apps/metering/pricing/migrations/0001_initial.py",
    "ubb-platform/apps/metering/pricing/migrations/0002_the_database_rules.py",
    "ubb-platform/apps/metering/usage/migrations/0001_initial.py",
    "ubb-platform/apps/metering/usage/migrations/0002_the_database_rules.py",
    "ubb-platform/apps/platform/audit/migrations/0001_initial.py",
    "ubb-platform/apps/platform/code_builder/migrations/0001_initial.py",
    "ubb-platform/apps/platform/code_builder/migrations/0002_the_database_rules.py",
    "ubb-platform/apps/platform/customers/migrations/0001_initial.py",
    "ubb-platform/apps/platform/event_types/migrations/0001_initial.py",
    "ubb-platform/apps/platform/event_types/migrations/0002_the_database_rules.py",
    "ubb-platform/apps/platform/events/migrations/0001_initial.py",
    "ubb-platform/apps/platform/grouping_fields/migrations/0001_initial.py",
    "ubb-platform/apps/platform/membership/migrations/0001_initial.py",
    "ubb-platform/apps/platform/plans/migrations/0001_initial.py",
    "ubb-platform/apps/platform/tenants/migrations/0001_initial.py",
    "ubb-platform/apps/platform/tenants/migrations/0002_the_database_rules.py",
    "ubb-platform/apps/platform/work/migrations/0001_initial.py",
    "ubb-platform/apps/platform/work/migrations/0002_the_database_rules.py",
    "ubb-platform/apps/referrals/migrations/0001_initial.py",
    "ubb-platform/apps/subscriptions/migrations/0001_initial.py",
})

#: HOW MANY MIGRATIONS G20 HOLDS. Zero on the cutover's own commit, stated
#: rather than left to an empty walk passing quietly (§0.3 point 9): the planted
#: cases below carry the red until a real migration arrives. The commit that
#: adds the first migration after the cutover moves this to 1 — the visible,
#: reviewed admission of a migration into the history G20 holds.
MIGRATIONS_SINCE_THE_CUTOVER = 0

NUMBERED = re.compile(r"^\d{4}_\w+\.py$")
DROP_OPS = {"RemoveField", "DeleteModel"}
ADD_OPS = {"AddField", "CreateModel"}


# ---------------------------------------------------------------------------
# The reader: one migration file -> what it does to data
# ---------------------------------------------------------------------------

def _name_of(call):
    func = call.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)


def _argument(call, position, keyword):
    for kw in call.keywords:
        if kw.arg == keyword:
            return kw.value
    return call.args[position] if len(call.args) > position else None


def _text(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _operations(nodes):
    """Every operation call in an `operations` list, reading into a
    `SeparateDatabaseAndState`'s DATABASE operations (its state operations
    move no rows)."""
    for node in nodes:
        if not isinstance(node, ast.Call):
            continue
        if _name_of(node) == "SeparateDatabaseAndState":
            database = _argument(node, 0, "database_operations")
            if isinstance(database, (ast.List, ast.Tuple)):
                yield from _operations(database.elts)
            continue
        yield node


def _module_literal(tree, name):
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in statement.targets):
            return ast.literal_eval(statement.value)
    return None


def read_migration(path, root):
    """`{site, app_dir, number, drops, adds, steps, DROPS, NOT_A_RENAME,
    IRREVERSIBLE}` for one migration file."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    listed = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Migration":
            for statement in node.body:
                if isinstance(statement, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == "operations"
                        for t in statement.targets):
                    listed = statement.value.elts
    drops, adds, steps = [], [], []
    for call in _operations(listed):
        kind = _name_of(call)
        if kind in ("RemoveField", "AddField"):
            model = (_text(_argument(call, 0, "model_name")) or "").lower()
            field = _text(_argument(call, 1, "name")) or ""
            (drops if kind == "RemoveField" else adds).append(
                (kind, model, f"{model}.{field}"))
        elif kind in ("DeleteModel", "CreateModel"):
            model = _text(_argument(call, 0, "name")) or ""
            (drops if kind == "DeleteModel" else adds).append(
                (kind, None, model))
        elif kind in ("RunPython", "RunSQL"):
            reverse = _argument(call, 1, "reverse_code" if kind == "RunPython"
                                else "reverse_sql")
            absent = reverse is None or (isinstance(reverse, ast.Constant)
                                         and reverse.value is None)
            steps.append((kind, not absent))
    file = Path(path)
    return {
        "site": file.relative_to(root).as_posix(),
        "app_dir": file.parent.relative_to(root).as_posix(),
        "number": int(file.name[:4]),
        "drops": drops, "adds": adds, "steps": steps,
        "DROPS": _module_literal(tree, "DROPS") or {},
        "NOT_A_RENAME": _module_literal(tree, "NOT_A_RENAME") or {},
        "IRREVERSIBLE": _module_literal(tree, "IRREVERSIBLE"),
    }


def held_migrations(root, fresh=FRESH_INITIAL_SET):
    """Every numbered migration under `root` that the fresh initial set does not
    name, read."""
    held = []
    for path in sorted(Path(root).rglob("migrations/*.py")):
        if ".venv" in path.parts or not NUMBERED.match(path.name):
            continue
        if path.relative_to(root).as_posix() not in fresh:
            held.append(read_migration(path, root))
    return held


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------

def _stated(declaration, key):
    reason = declaration.get(key)
    return isinstance(reason, str) and reason.strip() != ""


def _pairs(migration, other):
    """Every (dropped, added) pair a drop in `migration` and an add in `other`
    make on one model — fields on the same model, or any model for a model."""
    for drop_kind, drop_model, dropped in migration["drops"]:
        for add_kind, add_model, added in other["adds"]:
            if drop_kind == "RemoveField" and add_kind == "AddField" \
                    and drop_model == add_model:
                yield dropped, added
            elif drop_kind == "DeleteModel" and add_kind == "CreateModel":
                yield dropped, added


def faults_in(held):
    """Every way the held migrations break ADR-0007 §1, as plain sentences."""
    faults = []
    by_app = {}
    for migration in held:
        by_app.setdefault(migration["app_dir"], []).append(migration)
        for _kind, _model, site in migration["drops"]:
            if not _stated(migration["DROPS"], site):
                faults.append(f"{migration['site']}: drops {site} without a "
                              f"stated reason in DROPS")
        for kind, reversible in migration["steps"]:
            if not reversible and not (isinstance(migration["IRREVERSIBLE"], str)
                                       and migration["IRREVERSIBLE"].strip()):
                faults.append(f"{migration['site']}: a {kind} with no reverse "
                              f"and no IRREVERSIBLE reason")
    for app_dir, migrations in by_app.items():
        migrations.sort(key=lambda m: m["number"])
        for index, migration in enumerate(migrations):
            neighbours = [migration] + migrations[index + 1:index + 2]
            for first in neighbours:
                for second in neighbours:
                    if first is second and first is not migration:
                        continue
                    for dropped, added in _pairs(first, second):
                        declared = {**first["NOT_A_RENAME"], **second["NOT_A_RENAME"]}
                        if _stated(declared, dropped):
                            continue
                        where = (first["site"] if first is second else
                                 f"{first['site']} -> {second['site']}")
                        faults.append(f"{where}: drops {dropped} and adds "
                                      f"{added} — a disguised rename; use "
                                      f"RenameField/RenameModel, or declare "
                                      f"NOT_A_RENAME with a reason")
    return sorted(set(faults))


# ---------------------------------------------------------------------------
# The real tree
# ---------------------------------------------------------------------------

def test_the_fresh_initial_set_is_what_the_cutover_left():
    """Vacuity guard: the boundary names real files — every generated initial
    migration and every rules migration — so the walk below reads the tree it
    claims to, and the held set is the rest."""
    on_disk = {path.relative_to(REPO_ROOT).as_posix()
               for path in PLATFORM.rglob("migrations/*.py")
               if ".venv" not in path.parts and NUMBERED.match(path.name)}
    assert FRESH_INITIAL_SET <= on_disk, sorted(FRESH_INITIAL_SET - on_disk)
    assert len([s for s in FRESH_INITIAL_SET if s.endswith("0001_initial.py")]) == 20
    assert len([s for s in FRESH_INITIAL_SET
                if s.endswith("0002_the_database_rules.py")]) == 6


def test_the_held_set_is_every_migration_after_the_fresh_set():
    """The count is stated (:data:`MIGRATIONS_SINCE_THE_CUTOVER`), so an empty
    held set is a declared fact rather than a walk that found nothing."""
    held = held_migrations(REPO_ROOT)
    assert len(held) == MIGRATIONS_SINCE_THE_CUTOVER, (
        f"G20 holds {len(held)} migrations after the fresh initial set "
        f"({[m['site'] for m in held]}); state the new count in "
        f"MIGRATIONS_SINCE_THE_CUTOVER in the commit that adds one")


def test_every_migration_after_the_fresh_set_carries_its_data():
    """G20 — ADR-0007 §1, over every held migration."""
    faults = faults_in(held_migrations(REPO_ROOT))
    assert not faults, "\n".join(faults)


# ---------------------------------------------------------------------------
# Planted violations: each core category, red (§0.3 point 9)
# ---------------------------------------------------------------------------

HEADER = "from django.db import migrations, models\n\n"


def _plant(tmp_path, app, files):
    folder = tmp_path / "ubb-platform" / "apps" / app / "migrations"
    folder.mkdir(parents=True)
    (folder / "0001_initial.py").write_text(
        HEADER + "class Migration(migrations.Migration):\n    operations = []\n",
        encoding="utf-8")
    for name, body in files.items():
        (folder / name).write_text(HEADER + body, encoding="utf-8")
    fresh = {f"ubb-platform/apps/{app}/migrations/0001_initial.py"}
    return faults_in(held_migrations(tmp_path, fresh))


def _migration(*operations, preamble=""):
    listed = "".join(f"        {op},\n" for op in operations)
    return (preamble + "class Migration(migrations.Migration):\n"
            "    operations = [\n" + listed + "    ]\n")


REMOVE_A = 'migrations.RemoveField(model_name="widget", name="colour")'
ADD_B = ('migrations.AddField(model_name="widget", name="color", '
         'field=models.CharField(max_length=20, default=""))')
DROPS_A = 'DROPS = {"widget.colour": "replaced by color"}\n'


def test_planted_a_drop_and_an_add_in_one_migration_is_a_disguised_rename(tmp_path):
    faults = _plant(tmp_path, "shop", {
        "0002_rename.py": _migration(REMOVE_A, ADD_B, preamble=DROPS_A)})
    assert faults == [
        "ubb-platform/apps/shop/migrations/0002_rename.py: drops widget.colour "
        "and adds widget.color — a disguised rename; use RenameField/RenameModel, "
        "or declare NOT_A_RENAME with a reason"]


def test_planted_a_drop_then_an_add_in_the_next_migration_is_a_disguised_rename(tmp_path):
    """The split the ruling names: the same anti-pattern across two files."""
    faults = _plant(tmp_path, "shop", {
        "0002_drop.py": _migration(REMOVE_A, preamble=DROPS_A),
        "0003_add.py": _migration(ADD_B)})
    assert faults == [
        "ubb-platform/apps/shop/migrations/0002_drop.py -> "
        "ubb-platform/apps/shop/migrations/0003_add.py: drops widget.colour and "
        "adds widget.color — a disguised rename; use RenameField/RenameModel, "
        "or declare NOT_A_RENAME with a reason"]


def test_planted_an_add_then_a_drop_in_the_next_migration_is_a_disguised_rename(tmp_path):
    faults = _plant(tmp_path, "shop", {
        "0002_add.py": _migration(ADD_B),
        "0003_drop.py": _migration(REMOVE_A, preamble=DROPS_A)})
    assert len(faults) == 1 and "disguised rename" in faults[0]
    assert "0003_drop.py -> " in faults[0] and faults[0].endswith(
        "or declare NOT_A_RENAME with a reason")


def test_planted_a_model_deleted_then_created_next_door_is_a_disguised_rename(tmp_path):
    faults = _plant(tmp_path, "shop", {
        "0002_delete.py": _migration('migrations.DeleteModel(name="Gadget")',
                                     preamble='DROPS = {"Gadget": "superseded"}\n'),
        "0003_create.py": _migration(
            'migrations.CreateModel(name="Gizmo", fields=[("id", models.AutoField(primary_key=True))])')})
    assert faults == [
        "ubb-platform/apps/shop/migrations/0002_delete.py -> "
        "ubb-platform/apps/shop/migrations/0003_create.py: drops Gadget and adds "
        "Gizmo — a disguised rename; use RenameField/RenameModel, or declare "
        "NOT_A_RENAME with a reason"]


def test_planted_a_rename_with_a_type_adjustment_is_still_a_rename(tmp_path):
    """Not only an identical-type pair: a CharField dropped and a TextField with
    other options added under a new name is the same loss of rows."""
    faults = _plant(tmp_path, "shop", {
        "0002_retype.py": _migration(
            REMOVE_A,
            'migrations.AddField(model_name="widget", name="shade", '
            'field=models.TextField(null=True, blank=True))', preamble=DROPS_A)})
    assert len(faults) == 1 and "drops widget.colour and adds widget.shade" in faults[0]


def test_planted_a_drop_with_no_reason_is_refused(tmp_path):
    faults = _plant(tmp_path, "shop", {"0002_drop.py": _migration(REMOVE_A)})
    assert faults == ["ubb-platform/apps/shop/migrations/0002_drop.py: drops "
                      "widget.colour without a stated reason in DROPS"]


def test_planted_a_blank_reason_is_no_reason(tmp_path):
    faults = _plant(tmp_path, "shop", {"0002_drop.py": _migration(
        REMOVE_A, preamble='DROPS = {"widget.colour": "  "}\n')})
    assert faults == ["ubb-platform/apps/shop/migrations/0002_drop.py: drops "
                      "widget.colour without a stated reason in DROPS"]


def test_planted_a_runpython_with_no_reverse_is_refused(tmp_path):
    faults = _plant(tmp_path, "shop", {"0002_move.py": _migration(
        "migrations.RunPython(move)", preamble="def move(apps, schema_editor):\n    pass\n\n")})
    assert faults == ["ubb-platform/apps/shop/migrations/0002_move.py: a RunPython "
                      "with no reverse and no IRREVERSIBLE reason"]


def test_planted_a_runsql_with_no_reverse_is_refused(tmp_path):
    faults = _plant(tmp_path, "shop", {"0002_sql.py": _migration(
        'migrations.RunSQL("UPDATE x SET y = 1")')})
    assert faults == ["ubb-platform/apps/shop/migrations/0002_sql.py: a RunSQL "
                      "with no reverse and no IRREVERSIBLE reason"]


def test_planted_a_drop_inside_the_database_half_is_read(tmp_path):
    faults = _plant(tmp_path, "shop", {"0002_split.py": _migration(
        "migrations.SeparateDatabaseAndState(database_operations=["
        f"{REMOVE_A}], state_operations=[])")})
    assert faults == ["ubb-platform/apps/shop/migrations/0002_split.py: drops "
                      "widget.colour without a stated reason in DROPS"]


# ---------------------------------------------------------------------------
# Positive controls: what ADR-0007 §1 asks for passes
# ---------------------------------------------------------------------------

def test_a_rename_operation_passes(tmp_path):
    assert _plant(tmp_path, "shop", {"0002_rename.py": _migration(
        'migrations.RenameField(model_name="widget", old_name="colour", new_name="color")',
        'migrations.RenameModel(old_name="Gadget", new_name="Gizmo")')}) == []


def test_a_reasoned_drop_and_a_reversible_move_pass(tmp_path):
    assert _plant(tmp_path, "shop", {"0002_ok.py": _migration(
        REMOVE_A, "migrations.RunPython(move, back)",
        'migrations.RunSQL("UPDATE x SET y = 1", "UPDATE x SET y = 0")',
        preamble=DROPS_A + "def move(apps, schema_editor):\n    pass\n\n"
                 "def back(apps, schema_editor):\n    pass\n\n")}) == []


def test_a_stated_irreversible_step_passes(tmp_path):
    assert _plant(tmp_path, "shop", {"0002_once.py": _migration(
        "migrations.RunPython(move)",
        preamble='IRREVERSIBLE = "the old values cannot be recomputed"\n'
                 "def move(apps, schema_editor):\n    pass\n\n")}) == []


def test_a_pair_declared_not_a_rename_passes(tmp_path):
    assert _plant(tmp_path, "shop", {
        "0002_drop.py": _migration(REMOVE_A, preamble=DROPS_A + (
            'NOT_A_RENAME = {"widget.colour": "color is a new fact, not the '
            'old one renamed"}\n')),
        "0003_add.py": _migration(ADD_B)}) == []


def test_the_scope_is_adjacent_migrations_and_says_so(tmp_path):
    """The stated limit, pinned so the docstring cannot overclaim: a drop and
    an add TWO migrations apart are not paired by this detector."""
    assert _plant(tmp_path, "shop", {
        "0002_drop.py": _migration(REMOVE_A, preamble=DROPS_A),
        "0003_other.py": _migration(
            'migrations.AlterField(model_name="widget", name="size", '
            'field=models.IntegerField(default=0))'),
        "0004_add.py": _migration(ADD_B)}) == []


def test_two_apps_are_not_paired(tmp_path):
    folder = tmp_path / "ubb-platform" / "apps"
    for app, body in (("one", _migration(REMOVE_A, preamble=DROPS_A)),
                      ("two", _migration(ADD_B))):
        (folder / app / "migrations").mkdir(parents=True)
        (folder / app / "migrations" / "0002_x.py").write_text(HEADER + body,
                                                                 encoding="utf-8")
    assert faults_in(held_migrations(tmp_path, frozenset())) == []


def test_a_migration_outside_the_fresh_set_is_held(tmp_path):
    """The boundary is the constant: a file it does not name is read."""
    _plant(tmp_path, "shop", {"0002_x.py": _migration()})
    held = held_migrations(tmp_path, {"ubb-platform/apps/shop/migrations/0001_initial.py"})
    assert [m["site"] for m in held] == ["ubb-platform/apps/shop/migrations/0002_x.py"]
