"""The pool's stop line is compared by the shared predicate and by nothing
else (#459, slice 6 §4; the ceiling's one-place rule, #452, applied to the
pool).

Two modules hold the pool's lanes — the pool service (the start gate, the
durable drawdown compare, the seat-level reconcile) and the live counter (the
recording lane, the owner-level reconcile). Neither may spell an at-or-over
compare of its own: the AC's own instruction is to grep both for the operator
against the pool amount and find only the import, and this module is that
grep made a gate. Alert LEVELS are compared in the pool service on purpose —
they are `emit_threshold_alerts`' level rule, not the stop line — with the
strict operators, which is why the rule here is the at-or-over operator and
the import rather than "no compare at all".

The pool service's docstring is also held to the one input this ticket owes a
later one: a compensating Charge must decrement its period's pool (#472).
"""
import ast
from pathlib import Path

from apps.billing.gating.services import customer_spend_pool_service, live_counter

MODULES = (customer_spend_pool_service, live_counter)
THE_PREDICATE = "past_spend_pool_stop"
THE_LINE = "spend_pool_stop_threshold"


def _source(module):
    return Path(module.__file__).read_text(encoding="utf-8")


def _imports_from_core_crossing(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "core.crossing":
            names.update(alias.name for alias in node.names)
    return names


def test_neither_pool_module_spells_an_at_or_over_compare():
    for module in MODULES:
        tree = ast.parse(_source(module))
        spelled = [node.lineno for node in ast.walk(tree)
                   if isinstance(node, ast.Compare)
                   and any(isinstance(op, ast.GtE) for op in node.ops)]
        assert spelled == [], (
            f"{module.__name__} spells an at-or-over compare at line(s) "
            f"{spelled}; the pool's stop line is `core.crossing.{THE_PREDICATE}` "
            f"over `{THE_LINE}` and nothing else")


def test_both_pool_modules_reach_the_stop_line_only_through_the_import():
    for module in MODULES:
        imported = _imports_from_core_crossing(ast.parse(_source(module)))
        assert {THE_PREDICATE, THE_LINE} <= imported, (
            f"{module.__name__} imports {sorted(imported)} from core.crossing; "
            f"the pool's compare and its line must both come from there")


def test_the_walk_sees_the_operator_it_refuses():
    """Positive control: the shape the gate exists to refuse is visible to it."""
    tree = ast.parse("def past(spend, cfg):\n    return spend >= cfg.cap_micros\n")
    assert any(isinstance(node, ast.Compare)
               and any(isinstance(op, ast.GtE) for op in node.ops)
               for node in ast.walk(tree))


def test_the_pool_service_states_the_compensating_record_input():
    """A compensating Charge must decrement its period's pool — stated as an
    input where the pool is counted, built by #472 and not here."""
    doc = customer_spend_pool_service.__doc__ or ""
    assert "compensating" in doc.lower() and "decrement" in doc.lower(), doc
    assert "#472" in doc
