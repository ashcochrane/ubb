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
"""

# Order is not significant — grouped by namespace for readability. #81 lands the
# ledger and one real site (api-key mint); #82 sweeps the rest of the mutating
# surface in, appending here.
AUDIT_ACTIONS = (
    # api keys / credentials
    "api_key.created",
)

_AUDIT_ACTIONS_SET = frozenset(AUDIT_ACTIONS)


def is_registered_action(name):
    """True if ``name`` is a registered audit action."""
    return name in _AUDIT_ACTIONS_SET
