"""Which tables carry an amount UBB may not have, and what says so (#348).

An **amount/status pair** is a nullable money column plus the status column
beside it that says why an amount is missing — the shape `core.cost_totals`
totals, and the reason a total over it has to declare what it left out. The
rules live there, and so does the type — :class:`core.cost_totals.AmountStatusPair`,
which is a parameter of those rules before it is anything else. **What lives
here is the list of pairs**, one line per table, because the rules are generic
and the tables are not.

Two consequences worth stating, since they are why this is a module of its own
rather than four lines at the top of the seam:

* **The seam names no table.** A rule that holds a column name is a rule with
  one table's answer baked in, and the day a second table needs the same rule
  the honest options are a parameter or a second copy. `core.cost_totals` chose
  the parameter (#348); this file is where the argument comes from.
* **Everything that applies the rules can read it.** ADR-001 lets any product
  import ``core.*``, and forbids the kernel from importing a product at all —
  so a pair named beside metering's own model would be out of reach of
  `apps/platform`, which applies the unresolved rule to a running unit of work.
  That is not a hypothetical: `counts_as_unresolved` has five call sites in
  four modules today — two products, the kernel and the composition layer.

A pair is a claim about a table's schema, and nothing here checks it. The check
is the gate — `apps/platform/tests/test_no_bare_supplier_cost_aggregate.py`
sweeps for totals taken over the amount column without its count, and asks this
module which column that is rather than holding a copy of the name.
"""
from core.cost_totals import AmountStatusPair
from core.vocabulary import COSTING_STATUS_UNRESOLVED

#: The posting's supplier cost. `NULL` means UBB has not resolved this cost
#: (#317, ADR-0007 §2); `costing_status` is what separates that from a cost the
#: Event Type declares does not exist, which is also `NULL` and is not missing.
SUPPLIER_COST = AmountStatusPair(
    amount_column="provider_cost_micros",
    status_column="costing_status",
    unresolved_status=COSTING_STATUS_UNRESOLVED,
)
