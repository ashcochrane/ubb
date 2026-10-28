"""The audit action registry — the contractual vocabulary of recordable actions.

Each recorded action is a stable, domain-shaped name (``noun.verb``) that is part
of the public compatibility contract (ADR-004 §2, under ADR-003's rules):
**additive-only, a rename is a breaking change**. Names are deliberately decoupled
from routes — the ADR-002 single-API restructure renames routes; it must never
rewrite history's vocabulary — and equally decoupled from the webhook catalog
(``apps/platform/events/catalog.py``): queue and ledger stay separate concepts, so
the audit action ``api_key.created`` and the webhook event ``tenant.api_key_created``
are independent names in independent contracts.

This is the audit twin of that catalog and the #63 error-code registry: one source
of truth, extended only by appending. ``record()`` refuses an unregistered name, so
the registry cannot silently drift from what the ledger actually writes — and the
#82 mutating-route CI pin checks new routes against exactly this set.

**THE SOURCE OF TRUTH IS THE VOCABULARY REGISTRY SINCE R10-W4 (slice 8).** This
module used to spell all sixty-nine names inline, with the reasoning for each
beside it, while ``domain-vocabulary/concepts/governance.yaml`` declared the same
catalogue again — two copies, and G2 measured this one as holding none of the
registry's values. It now holds them BY REFERENCE: the recordable set is the
registry's ``audit_action`` less what the registry WITHHOLDS, and the reasoning
lives beside each value in that file (the history of the inline copy is in git,
before this commit).

**THE ONE WITHHELD ACTION** is ``system.preproduction_model_cutover``. It was to
open the production ledger at the cutover; #190's ruling of 2026-10-23 decided no
opening row is ever written, and keeps the registration until W6 retires it with
the reset. Until then it is declared, never recordable and never advertised — and
both halves read ``AUDIT_ACTION_WITHHELD_VALUES``, so the backend and the
published contract learn the one exclusion from one place.

**The kind of record an action changed** is the registry's closed
``audit_resource_type`` (ruling 6). ``record()`` refuses any other, and every
writer names one by reference rather than spelling it.
"""

from core.vocabulary import (
    AUDIT_ACTION_VALUES,
    AUDIT_ACTION_WITHHELD_VALUES,
    AUDIT_RESOURCE_TYPE_VALUES,
)

#: Every action the ledger may record: the registry's catalogue, less the
#: actions it withholds. Order is not significant.
AUDIT_ACTIONS = AUDIT_ACTION_VALUES - AUDIT_ACTION_WITHHELD_VALUES

#: Every kind of record an audited action may name.
AUDIT_RESOURCE_TYPES = AUDIT_RESOURCE_TYPE_VALUES


def is_registered_action(name):
    """True if ``name`` is an audit action the ledger may record."""
    return name in AUDIT_ACTIONS


def is_withheld_action(name):
    """True if ``name`` is declared but may never be recorded."""
    return name in AUDIT_ACTION_WITHHELD_VALUES


def is_declared_resource_type(name):
    """True if ``name`` is a kind of record an audited action may name."""
    return name in AUDIT_RESOURCE_TYPES
