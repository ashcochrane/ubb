# @generated from domain-vocabulary/ — do not edit by hand.
# Regenerate with `python -m tools.vocabulary --write`.
"""Canonical vocabulary constants, generated from the registry.

`domain-vocabulary/` at the git root is the checked-in statement of what every
UBB-owned concept is called and what values it may take (ADR-0008 §2). This
module is that registry rendered as Python, so a model or a service holds a
canonical value by REFERENCE and the backend cannot keep a second copy of it
that drifts.

Two names per value set, and the difference between them is load-bearing:

    <CONCEPT>_VALUES        a `closed` concept — exactly these, no more.
    <CONCEPT>_KNOWN_VALUES  an `open` concept — what UBB knows today. A value
                            that is not in it is still legal, so this set never
                            decides a rejection (ADR-0003).

Three things are deliberately absent:

- **Retired terms.** Naming one would plant a forbidden word in a file nobody
  may hand-edit. The forbidden-term sweep reads `retired_aliases` from the
  registry itself, which is the copy that can actually be corrected.
- **Label keys and the English.** Console content: wording changes far more
  often than the token underneath it (ADR-0008 §4).
- **Imports.** Literals only, so this module is safe to import from a
  migration, a management command or a settings-free tool, and can never take
  part in an import cycle.
"""

# --- customer_billing_mode ---------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# What UBB does about money for a tenant's customers. `external` means the
# tenant bills their customers somewhere else and UBB only meters; `prepaid`
# and `postpaid` mean UBB drives the money, and neither may be activated before
# its payment rail has been (ADR-0008 §6).
#
# Declared in concepts/economics.yaml.

CUSTOMER_BILLING_MODE_EXTERNAL = 'external'
CUSTOMER_BILLING_MODE_PREPAID = 'prepaid'
CUSTOMER_BILLING_MODE_POSTPAID = 'postpaid'

CUSTOMER_BILLING_MODE_VALUES = frozenset({
    CUSTOMER_BILLING_MODE_EXTERNAL,
    CUSTOMER_BILLING_MODE_PREPAID,
    CUSTOMER_BILLING_MODE_POSTPAID,
})


# --- grouping_field_value ----------------------------------------------------
#
# tenant_defined — The tenant owns the values. UBB defines the field and its
# validation contract and never enumerates the set — map #137 constraint 5 as a
# schema rule, so the registry cannot become the vendor catalogue that
# constraint forbids UBB to ship.
#
# A value a tenant reports on one of its own declared grouping fields — a model
# name, a region, a customer tier. UBB bounds the keyspace (ADR-0005's
# cardinality cap) and never enumerates the values: doing so would make the
# registry a catalogue of the tenant's vendors and models, which map #137
# constraint 5 forbids UBB to ship.
#
# Declared in concepts/economics.yaml.
#
# No constants: this kind declares no values by construction. The section is
# here so that fact is visible, rather than looking like a concept the
# generator lost.


# --- plan_name ---------------------------------------------------------------
#
# free_text — Not vocabulary. Recorded here so that "is this a value set?" is
# answered once, in data, rather than re-litigated by whoever next wants to add
# an enum to it.
#
# The display name a tenant gives a plan. Prose a human typed, not a token — it
# is recorded here so that "should plan names be an enum?" is answered once, in
# data, and never re-opened. A `free_text` concept declares no values by
# construction; that absence IS its content.
#
# Declared in concepts/economics.yaml.
#
# No constants: this kind declares no values by construction. The section is
# here so that fact is visible, rather than looking like a concept the
# generator lost.


# --- reason_code -------------------------------------------------------------
#
# open — UBB records the values it knows; consumers accept future and external
# ones. Checking is asymmetric — a registry-known value missing from a
# UBB-owned consumer is a defect, a runtime value the registry has never seen
# is legal.
#
# Why work was stopped or a limit was reported. Open rather than closed because
# a stop can originate outside UBB — a provider refusal, a tenant's own control
# — and a value UBB has never seen must still travel rather than be rejected at
# the boundary. The asymmetry is the whole point: a value listed here and
# missing from a UBB-owned consumer is a defect; a value the registry has never
# seen is legal.
#
# Declared in concepts/spend-controls.yaml.

REASON_CODE_TASK_COGS_CEILING = 'task_cogs_ceiling'
REASON_CODE_CUSTOMER_SPEND_POOL = 'customer_spend_pool'
REASON_CODE_PARENT_KILLED = 'parent_killed'

REASON_CODE_KNOWN_VALUES = frozenset({
    REASON_CODE_TASK_COGS_CEILING,
    REASON_CODE_CUSTOMER_SPEND_POOL,
    REASON_CODE_PARENT_KILLED,
})
