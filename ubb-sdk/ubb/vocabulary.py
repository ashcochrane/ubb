# @generated from domain-vocabulary/ — do not edit by hand.
# Regenerate with `python -m tools.vocabulary --write`.
"""Canonical vocabulary constants, generated from the registry.

`domain-vocabulary/` in the UBB repository is the checked-in statement of what
every UBB-owned concept is called and what values it may take (ADR-0008 §2).
This module is that registry rendered as Python, so **a value the API can
return is a value this SDK can name**: an integrator branches on a constant
rather than on a string they typed from memory into their own code.

Two names per value set, and the difference between them is load-bearing:

    <CONCEPT>_VALUES        a `closed` concept — exactly these, no more.
    <CONCEPT>_KNOWN_VALUES  an `open` concept — what UBB knows today. A value
                            that is not in it is still legal (ADR-0003), so
                            this set never decides a rejection. An SDK that
                            refused an unrecognised value would break its
                            callers on the day UBB adds one.

Three things are deliberately absent:

- **Retired terms.** Naming one would plant a forbidden word in a file nobody
  may hand-edit. The forbidden-term sweep reads `retired_aliases` from the
  registry itself, which is the copy that can actually be corrected.
- **Label keys and the English.** Console content: wording changes far more
  often than the token underneath it (ADR-0008 §4), and an SDK has no user to
  render one to.
- **Imports, and a re-export.** Literals only, so importing this module can
  neither fail nor join an import cycle. It is deliberately NOT star-exported
  from `ubb/__init__.py`: that would put every concept's constants in the
  package's top-level namespace, and a hand-written re-export list would be the
  second copy of every name this artifact exists to abolish. Reach it by
  module::

      from ubb import vocabulary

      if response.status == vocabulary.TASK_STATUS_COMPLETED:
          ...
"""

# --- affordability_reason ----------------------------------------------------
#
# open — UBB records the values it knows; consumers accept future and external
# ones. Checking is asymmetric — a registry-known value missing from a
# UBB-owned consumer is a defect, a runtime value the registry has never seen
# is legal.
#
# Why an affordability question was answered no. The question names what is
# being asked rather than the object inspected, so it stays true if a credit
# line or a grant later becomes an input. Open for the same reason as the stop
# vocabulary beside it: a refusal can arise from a control UBB gains later, and
# a caller must render one it has not seen rather than fail.
#
# Declared in concepts/spend-controls.yaml.

AFFORDABILITY_REASON_INSUFFICIENT_FUNDS = 'insufficient_funds'
AFFORDABILITY_REASON_ACCOUNT_CLOSED = 'account_closed'
AFFORDABILITY_REASON_CUSTOMER_STOPPED = 'customer_stopped'
AFFORDABILITY_REASON_SOFT_FLOOR_REACHED = 'soft_floor_reached'
AFFORDABILITY_REASON_RATE_LIMIT_EXCEEDED = 'rate_limit_exceeded'
AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED = 'customer_spend_pool_exceeded'
AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_UNAVAILABLE = 'customer_spend_pool_unavailable'
AFFORDABILITY_REASON_PARENT_TASK_NOT_ACTIVE = 'parent_task_not_active'
AFFORDABILITY_REASON_SUBTASK_DEPTH_EXCEEDED = 'subtask_depth_exceeded'

AFFORDABILITY_REASON_KNOWN_VALUES = frozenset({
    AFFORDABILITY_REASON_INSUFFICIENT_FUNDS,
    AFFORDABILITY_REASON_ACCOUNT_CLOSED,
    AFFORDABILITY_REASON_CUSTOMER_STOPPED,
    AFFORDABILITY_REASON_SOFT_FLOOR_REACHED,
    AFFORDABILITY_REASON_RATE_LIMIT_EXCEEDED,
    AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED,
    AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_UNAVAILABLE,
    AFFORDABILITY_REASON_PARENT_TASK_NOT_ACTIVE,
    AFFORDABILITY_REASON_SUBTASK_DEPTH_EXCEEDED,
})


# --- amount_representation ---------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# What an extracted supplier-cost number actually represents, so the conversion
# to currency micros is generated once and exactly rather than written by hand
# in a repository UBB never sees. Declaring it is what keeps "no float enters
# money arithmetic" true across the boundary (#179 §3.4).
#
# Declared in concepts/economics.yaml.

AMOUNT_REPRESENTATION_MICROS = 'micros'
AMOUNT_REPRESENTATION_MINOR_UNITS = 'minor_units'
AMOUNT_REPRESENTATION_MAJOR_UNITS_DECIMAL = 'major_units_decimal'

AMOUNT_REPRESENTATION_VALUES = frozenset({
    AMOUNT_REPRESENTATION_MICROS,
    AMOUNT_REPRESENTATION_MINOR_UNITS,
    AMOUNT_REPRESENTATION_MAJOR_UNITS_DECIMAL,
})


# --- analytics_grouping_kind -------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# Whether a grouping axis is a column on the event or a join to a declared
# rollup. The namespace is deliberate: a field and a rollup have materially
# different cardinality and query cost, and hiding that behind identical
# looking strings is how a chart times out in production (#153 §5.3).
#
# Declared in concepts/economics.yaml.

ANALYTICS_GROUPING_KIND_FIELD = 'field'
ANALYTICS_GROUPING_KIND_ROLLUP = 'rollup'

ANALYTICS_GROUPING_KIND_VALUES = frozenset({
    ANALYTICS_GROUPING_KIND_FIELD,
    ANALYTICS_GROUPING_KIND_ROLLUP,
})


# --- analytics_measure -------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# The four things the economic query can measure. Each name says which side of
# the trade it sits on, and `recorded_events` says plainly that it counts
# records at the tenant's declared granularity rather than units of work.
#
# Declared in concepts/economics.yaml.

ANALYTICS_MEASURE_SUPPLIER_COGS = 'supplier_cogs'
ANALYTICS_MEASURE_CUSTOMER_REVENUE = 'customer_revenue'
ANALYTICS_MEASURE_GROSS_MARGIN = 'gross_margin'
ANALYTICS_MEASURE_RECORDED_EVENTS = 'recorded_events'

ANALYTICS_MEASURE_VALUES = frozenset({
    ANALYTICS_MEASURE_SUPPLIER_COGS,
    ANALYTICS_MEASURE_CUSTOMER_REVENUE,
    ANALYTICS_MEASURE_GROSS_MARGIN,
    ANALYTICS_MEASURE_RECORDED_EVENTS,
})


# --- analytics_rollup --------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# The aggregation axes UBB itself owns, one level above what the tenant
# declares. The tenant assigns members to them; the axes themselves are UBB's.
# Rollup membership is analytical taxonomy and may reclassify history, which is
# safe precisely because it touches no money (#153 §5.5).
#
# Declared in concepts/economics.yaml.

ANALYTICS_ROLLUP_EVENT_CATEGORY = 'event_category'
ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT = 'measurement_concept'

ANALYTICS_ROLLUP_VALUES = frozenset({
    ANALYTICS_ROLLUP_EVENT_CATEGORY,
    ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT,
})


# --- audit_action ------------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# Every action the tenant governance ledger may record, as `noun.verb`. The
# ledger refuses an unregistered name, which is what stops the registered set
# from drifting from what is actually written. Closed for the same reason: UBB
# authors every one of them, and a name nothing may write is not an action.
#
# Declared in concepts/governance.yaml.

AUDIT_ACTION_API_KEY_CREATED = 'api_key.created'
AUDIT_ACTION_API_KEY_ROTATED = 'api_key.rotated'
AUDIT_ACTION_API_KEY_REVOKED = 'api_key.revoked'
AUDIT_ACTION_INVITATION_CREATED = 'invitation.created'
AUDIT_ACTION_INVITATION_REVOKED = 'invitation.revoked'
AUDIT_ACTION_MEMBER_ROLE_CHANGED = 'member.role_changed'
AUDIT_ACTION_MEMBER_REMOVED = 'member.removed'
AUDIT_ACTION_TENANT_CONFIG_CHANGED = 'tenant.config_changed'
AUDIT_ACTION_SANDBOX_CREATED = 'sandbox.created'
AUDIT_ACTION_SANDBOX_RESET = 'sandbox.reset'
AUDIT_ACTION_CONNECT_STARTED = 'connect.started'
AUDIT_ACTION_BILLING_PROFILE_SET = 'billing_profile.set'
AUDIT_ACTION_AUTO_TOP_UP_CONFIGURED = 'auto_top_up.configured'
AUDIT_ACTION_POSTPAID_CONFIG_SET = 'postpaid_config.set'
AUDIT_ACTION_CUSTOMER_SPEND_POOL_SET = 'customer_spend_pool.set'
AUDIT_ACTION_MARGIN_THRESHOLD_SET = 'margin_threshold.set'
AUDIT_ACTION_WALLET_CREDITED = 'wallet.credited'
AUDIT_ACTION_WALLET_DEBITED = 'wallet.debited'
AUDIT_ACTION_WALLET_WITHDRAWN = 'wallet.withdrawn'
AUDIT_ACTION_TOP_UP_REQUESTED = 'top_up.requested'
AUDIT_ACTION_USAGE_REFUNDED = 'usage.refunded'
AUDIT_ACTION_GRANT_CREATED = 'grant.created'
AUDIT_ACTION_GRANT_VOIDED = 'grant.voided'
AUDIT_ACTION_PRICING_BOOK_CREATED = 'pricing_book.created'
AUDIT_ACTION_PRICING_BOOK_ASSIGNED = 'pricing_book.assigned'
AUDIT_ACTION_PRICING_BOOK_PUBLISHED = 'pricing_book.published'
AUDIT_ACTION_COST_RATE_ADDED = 'cost_rate.added'
AUDIT_ACTION_COST_RATE_DELETED = 'cost_rate.deleted'
AUDIT_ACTION_PRICING_RULE_ADDED = 'pricing_rule.added'
AUDIT_ACTION_PRICING_RULE_DELETED = 'pricing_rule.deleted'
AUDIT_ACTION_CUSTOMER_PRICING_OVERRIDE_SET = 'customer_pricing_override.set'
AUDIT_ACTION_EVENT_TYPE_DECLARED = 'event_type.declared'
AUDIT_ACTION_MEASUREMENT_DECLARED = 'measurement.declared'
AUDIT_ACTION_GROUPING_FIELD_DECLARED = 'grouping_field.declared'
AUDIT_ACTION_TASK_TYPE_DECLARED = 'task_type.declared'
AUDIT_ACTION_TENANT_SUPPLIED_REVENUE_RECORDED = 'tenant_supplied_revenue.recorded'
AUDIT_ACTION_CUSTOMER_CREATED = 'customer.created'
AUDIT_ACTION_PLAN_CREATED = 'plan.created'
AUDIT_ACTION_PLAN_UPDATED = 'plan.updated'
AUDIT_ACTION_PLAN_ARCHIVED = 'plan.archived'
AUDIT_ACTION_PLAN_ASSIGNED = 'plan.assigned'
AUDIT_ACTION_SUBSCRIPTION_CREATED = 'subscription.created'
AUDIT_ACTION_SUBSCRIPTION_CANCELED = 'subscription.canceled'
AUDIT_ACTION_SUBSCRIPTION_PAUSED = 'subscription.paused'
AUDIT_ACTION_SUBSCRIPTION_RESUMED = 'subscription.resumed'
AUDIT_ACTION_SUBSCRIPTION_SEATS_CHANGED = 'subscription.seats_changed'
AUDIT_ACTION_REFERRAL_PROGRAM_CREATED = 'referral_program.created'
AUDIT_ACTION_REFERRAL_PROGRAM_UPDATED = 'referral_program.updated'
AUDIT_ACTION_REFERRAL_PROGRAM_DEACTIVATED = 'referral_program.deactivated'
AUDIT_ACTION_REFERRAL_PROGRAM_REACTIVATED = 'referral_program.reactivated'
AUDIT_ACTION_REFERRER_REGISTERED = 'referrer.registered'
AUDIT_ACTION_REFERRAL_ATTRIBUTED = 'referral.attributed'
AUDIT_ACTION_REFERRAL_REVOKED = 'referral.revoked'
AUDIT_ACTION_WEBHOOK_CONFIG_CREATED = 'webhook_config.created'
AUDIT_ACTION_WEBHOOK_CONFIG_UPDATED = 'webhook_config.updated'
AUDIT_ACTION_WEBHOOK_CONFIG_DELETED = 'webhook_config.deleted'
AUDIT_ACTION_WEBHOOK_CONFIG_SECRET_ROTATED = 'webhook_config.secret_rotated'
AUDIT_ACTION_SYSTEM_PREPRODUCTION_MODEL_CUTOVER = 'system.preproduction_model_cutover'

AUDIT_ACTION_VALUES = frozenset({
    AUDIT_ACTION_API_KEY_CREATED,
    AUDIT_ACTION_API_KEY_ROTATED,
    AUDIT_ACTION_API_KEY_REVOKED,
    AUDIT_ACTION_INVITATION_CREATED,
    AUDIT_ACTION_INVITATION_REVOKED,
    AUDIT_ACTION_MEMBER_ROLE_CHANGED,
    AUDIT_ACTION_MEMBER_REMOVED,
    AUDIT_ACTION_TENANT_CONFIG_CHANGED,
    AUDIT_ACTION_SANDBOX_CREATED,
    AUDIT_ACTION_SANDBOX_RESET,
    AUDIT_ACTION_CONNECT_STARTED,
    AUDIT_ACTION_BILLING_PROFILE_SET,
    AUDIT_ACTION_AUTO_TOP_UP_CONFIGURED,
    AUDIT_ACTION_POSTPAID_CONFIG_SET,
    AUDIT_ACTION_CUSTOMER_SPEND_POOL_SET,
    AUDIT_ACTION_MARGIN_THRESHOLD_SET,
    AUDIT_ACTION_WALLET_CREDITED,
    AUDIT_ACTION_WALLET_DEBITED,
    AUDIT_ACTION_WALLET_WITHDRAWN,
    AUDIT_ACTION_TOP_UP_REQUESTED,
    AUDIT_ACTION_USAGE_REFUNDED,
    AUDIT_ACTION_GRANT_CREATED,
    AUDIT_ACTION_GRANT_VOIDED,
    AUDIT_ACTION_PRICING_BOOK_CREATED,
    AUDIT_ACTION_PRICING_BOOK_ASSIGNED,
    AUDIT_ACTION_PRICING_BOOK_PUBLISHED,
    AUDIT_ACTION_COST_RATE_ADDED,
    AUDIT_ACTION_COST_RATE_DELETED,
    AUDIT_ACTION_PRICING_RULE_ADDED,
    AUDIT_ACTION_PRICING_RULE_DELETED,
    AUDIT_ACTION_CUSTOMER_PRICING_OVERRIDE_SET,
    AUDIT_ACTION_EVENT_TYPE_DECLARED,
    AUDIT_ACTION_MEASUREMENT_DECLARED,
    AUDIT_ACTION_GROUPING_FIELD_DECLARED,
    AUDIT_ACTION_TASK_TYPE_DECLARED,
    AUDIT_ACTION_TENANT_SUPPLIED_REVENUE_RECORDED,
    AUDIT_ACTION_CUSTOMER_CREATED,
    AUDIT_ACTION_PLAN_CREATED,
    AUDIT_ACTION_PLAN_UPDATED,
    AUDIT_ACTION_PLAN_ARCHIVED,
    AUDIT_ACTION_PLAN_ASSIGNED,
    AUDIT_ACTION_SUBSCRIPTION_CREATED,
    AUDIT_ACTION_SUBSCRIPTION_CANCELED,
    AUDIT_ACTION_SUBSCRIPTION_PAUSED,
    AUDIT_ACTION_SUBSCRIPTION_RESUMED,
    AUDIT_ACTION_SUBSCRIPTION_SEATS_CHANGED,
    AUDIT_ACTION_REFERRAL_PROGRAM_CREATED,
    AUDIT_ACTION_REFERRAL_PROGRAM_UPDATED,
    AUDIT_ACTION_REFERRAL_PROGRAM_DEACTIVATED,
    AUDIT_ACTION_REFERRAL_PROGRAM_REACTIVATED,
    AUDIT_ACTION_REFERRER_REGISTERED,
    AUDIT_ACTION_REFERRAL_ATTRIBUTED,
    AUDIT_ACTION_REFERRAL_REVOKED,
    AUDIT_ACTION_WEBHOOK_CONFIG_CREATED,
    AUDIT_ACTION_WEBHOOK_CONFIG_UPDATED,
    AUDIT_ACTION_WEBHOOK_CONFIG_DELETED,
    AUDIT_ACTION_WEBHOOK_CONFIG_SECRET_ROTATED,
    AUDIT_ACTION_SYSTEM_PREPRODUCTION_MODEL_CUTOVER,
})


# --- ceiling_basis -----------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# What a Ceiling bounds. Cost and time genuinely are different columns in
# different units, so each ceiling field states its own basis and unit rather
# than one field switching unit, storage and comparison at once (#150 §2.3).
#
# Declared in concepts/spend-controls.yaml.

CEILING_BASIS_COST = 'cost'
CEILING_BASIS_TIME = 'time'

CEILING_BASIS_VALUES = frozenset({
    CEILING_BASIS_COST,
    CEILING_BASIS_TIME,
})


# --- ceiling_status ----------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# What a ceiling assessment concluded for one Task. `indeterminate` is kept
# distinct from an unresolved cost on purpose: an unresolved cost is a missing
# value, and `indeterminate` is the resulting inability to evaluate the ceiling
# (#158 §12.2).
#
# Declared in concepts/spend-controls.yaml.
#
# Decision rule, declared as registry data and proved total and unambiguous by
# the compiler:
#
#   The lower-bound rule (#158 §12.3). Once the KNOWN portion of accumulated
#   COGS has reached the ceiling, costs still unresolved cannot argue the Task
#   back under it — this is a spend-control safety invariant rather than a
#   naming detail, which is why it is carried beside the values as data. `>=`
#   is the comparison, so a ceiling is reached rather than exceeded.
#
#   a_ceiling_applies=false, known_cogs_at_or_above_ceiling=any,
#   unresolved_costs_remain=any
#     -> not_applicable
#        Nothing was evaluated, so nothing was concluded. `indeterminate` means
#        UBB tried and could not tell, never that there was nothing to try
#        (#158 §12.4).
#
#   a_ceiling_applies=true, known_cogs_at_or_above_ceiling=true,
#   unresolved_costs_remain=any
#     -> ceiling_reached
#        The known accumulated COGS is already at or above the ceiling. Costs
#        that are still unresolved can only add to it, so no later resolution
#        can reverse this answer — reporting anything softer here would let an
#        unresolved cost buy a Task more spending.
#
#   a_ceiling_applies=true, known_cogs_at_or_above_ceiling=false,
#   unresolved_costs_remain=true
#     -> indeterminate
#        The known lower bound is still below the ceiling and at least one
#        applicable cost is unresolved, so UBB cannot prove the Task is inside
#        it. This is the only case the word covers.
#
#   a_ceiling_applies=true, known_cogs_at_or_above_ceiling=false,
#   unresolved_costs_remain=false
#     -> within_ceiling
#        Every applicable cost is resolved and the total is below the ceiling,
#        which is the only state in which UBB can say so positively.

CEILING_STATUS_WITHIN_CEILING = 'within_ceiling'
CEILING_STATUS_CEILING_REACHED = 'ceiling_reached'
CEILING_STATUS_INDETERMINATE = 'indeterminate'
CEILING_STATUS_NOT_APPLICABLE = 'not_applicable'

CEILING_STATUS_VALUES = frozenset({
    CEILING_STATUS_WITHIN_CEILING,
    CEILING_STATUS_CEILING_REACHED,
    CEILING_STATUS_INDETERMINATE,
    CEILING_STATUS_NOT_APPLICABLE,
})


# --- control_family ----------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# Which of the four spend controls a signal came from. The same four words are
# the webhook namespace, the analytics family and this field, because one
# public concept gets one public name (ADR-0006 §2). A Ceiling bounds one unit
# of work, a customer spend pool bounds one customer's charges over a period, a
# wallet policy holds the floors, and admission control bounds the rate of new
# work and says nothing about supplier cost at all.
#
# Declared in concepts/spend-controls.yaml.

CONTROL_FAMILY_CEILING = 'ceiling'
CONTROL_FAMILY_CUSTOMER_SPEND_POOL = 'customer_spend_pool'
CONTROL_FAMILY_WALLET_POLICY = 'wallet_policy'
CONTROL_FAMILY_ADMISSION_CONTROL = 'admission_control'

CONTROL_FAMILY_VALUES = frozenset({
    CONTROL_FAMILY_CEILING,
    CONTROL_FAMILY_CUSTOMER_SPEND_POOL,
    CONTROL_FAMILY_WALLET_POLICY,
    CONTROL_FAMILY_ADMISSION_CONTROL,
})


# --- costing_method ----------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# How an Event Type's supplier COGS is derived — `calculated` from declared
# Measurements against CostRates, or `reported` from a value the provider or
# the caller supplies. "Method" means how an amount is derived, and never which
# operating regime applies (ADR-0006 §3).
#
# Declared in concepts/economics.yaml.

COSTING_METHOD_CALCULATED = 'calculated'
COSTING_METHOD_REPORTED = 'reported'

COSTING_METHOD_VALUES = frozenset({
    COSTING_METHOD_CALCULATED,
    COSTING_METHOD_REPORTED,
})


# --- costing_status ----------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# Whether supplier COGS for a subject is settled. `unresolved` and a NULL
# amount are one fact and travel together; zero is a resolved amount and means
# something else entirely (ADR-0007 §2).
#
# Declared in concepts/economics.yaml.

COSTING_STATUS_KNOWN = 'known'
COSTING_STATUS_UNRESOLVED = 'unresolved'
COSTING_STATUS_NOT_APPLICABLE = 'not_applicable'

COSTING_STATUS_VALUES = frozenset({
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_UNRESOLVED,
    COSTING_STATUS_NOT_APPLICABLE,
})


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


# --- event_type_key ----------------------------------------------------------
#
# tenant_defined — The tenant owns the values. UBB defines the field and its
# validation contract and never enumerates the set — map #137 constraint 5 as a
# schema rule, so the registry cannot become the vendor catalogue that
# constraint forbids UBB to ship.
#
# The key a tenant gives one of its own registered Event Types. UBB owns the
# entity, its costing declaration and its validation contract, and never
# enumerates the keys: doing so would make the registry a catalogue of the
# tenant's providers and calls, which map #137 constraint 5 forbids UBB to
# ship.
#
# Declared in concepts/economics.yaml.
#
# No constants: this kind declares no values by construction. The section is
# here so that fact is visible, rather than looking like a concept the
# generator lost.


# --- external_task_id --------------------------------------------------------
#
# free_text — Not vocabulary. Recorded here so that "is this a value set?" is
# answered once, in data, rather than re-litigated by whoever next wants to add
# an enum to it.
#
# The caller's own identifier for a Task, carried so an engineer can find their
# side of the record from UBB's. Opaque to UBB, which neither parses it nor
# groups on it.
#
# Declared in concepts/tasks.yaml.
#
# No constants: this kind declares no values by construction. The section is
# here so that fact is visible, rather than looking like a concept the
# generator lost.


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
# registry a catalogue of the tenant's suppliers and models, which map #137
# constraint 5 forbids UBB to ship.
#
# Declared in concepts/economics.yaml.
#
# No constants: this kind declares no values by construction. The section is
# here so that fact is visible, rather than looking like a concept the
# generator lost.


# --- idempotency_key ---------------------------------------------------------
#
# free_text — Not vocabulary. Recorded here so that "is this a value set?" is
# answered once, in data, rather than re-litigated by whoever next wants to add
# an enum to it.
#
# The caller's key for making a retried write safe. Opaque to UBB beyond its
# length bound, and the only caller-supplied correlation value on the recording
# path — which is what made the second one removable: it had no uniqueness
# constraint, no lookup, no filter and no read that changed any behaviour,
# while carrying an index write on the hottest path in the system (#179 §4).
#
# Declared in concepts/retired.yaml.
#
# No constants: this kind declares no values by construction. The section is
# here so that fact is visible, rather than looking like a concept the
# generator lost.


# --- live_counter_maintenance_enabled ----------------------------------------
#
# free_text — Not vocabulary. Recorded here so that "is this a value set?" is
# answered once, in data, rather than re-litigated by whoever next wants to add
# an enum to it.
#
# The per-tenant switch selecting WHEN the live spend counters are maintained:
# ON debits them synchronously on the recording path and checks the crossing
# there, so the ack itself carries the stop verdict; OFF does no counter work
# at record time and the durable drawdown detects instead, at its own latency.
# It was named for the arrival-time ingest lane. Slice 1 (#192) deleted that
# lane and kept the switch, because it never was the lane's switch — it also
# gates both reconciles' counter legs and the upward repair, none of which is
# arrival-shaped, and the conflation cost a whole ticket (#233) to unpick when
# `repair.py` was read under the wrong meaning. Renamed by #246 while the
# pre-live contract window was still open (ADR-0007 §5), because after platform
# admission the same word costs a 90-day deprecation cycle.
#
# Declared in concepts/retired.yaml.
#
# No constants: this kind declares no values by construction. The section is
# here so that fact is visible, rather than looking like a concept the
# generator lost.


# --- measure_status ----------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# What one requested measure's amount is worth in a response. Four facts that
# used to be one integer: `incomplete` says some input is still unresolved,
# `unavailable_at_requested_grain` says the number exists but cannot be
# attributed this finely, and `not_applicable` says the measure does not apply
# here. No query may coerce any of them to zero (#153 §8.5).
#
# Declared in concepts/economics.yaml.

MEASURE_STATUS_KNOWN = 'known'
MEASURE_STATUS_INCOMPLETE = 'incomplete'
MEASURE_STATUS_UNAVAILABLE_AT_REQUESTED_GRAIN = 'unavailable_at_requested_grain'
MEASURE_STATUS_NOT_APPLICABLE = 'not_applicable'

MEASURE_STATUS_VALUES = frozenset({
    MEASURE_STATUS_KNOWN,
    MEASURE_STATUS_INCOMPLETE,
    MEASURE_STATUS_UNAVAILABLE_AT_REQUESTED_GRAIN,
    MEASURE_STATUS_NOT_APPLICABLE,
})


# --- measurement_key ---------------------------------------------------------
#
# tenant_defined — The tenant owns the values. UBB defines the field and its
# validation contract and never enumerates the set — map #137 constraint 5 as a
# schema rule, so the registry cannot become the vendor catalogue that
# constraint forbids UBB to ship.
#
# The key a tenant gives one of its own declared measurable quantities. UBB
# owns the entity, its unit and its value type, and never enumerates the keys.
# The industry uses the retired word for the metered ENTITY rather than for the
# quantity inside it, so keeping it here would have guaranteed mis-translation
# at every integration boundary (#145 §10).
#
# Declared in concepts/retired.yaml.
#
# No constants: this kind declares no values by construction. The section is
# here so that fact is visible, rather than looking like a concept the
# generator lost.


# --- metadata_key ------------------------------------------------------------
#
# tenant_defined — The tenant owns the values. UBB defines the field and its
# validation contract and never enumerates the set — map #137 constraint 5 as a
# schema rule, so the registry cannot become the vendor catalogue that
# constraint forbids UBB to ship.
#
# A key in the one open bag a tenant may attach to a record. Filterable, never
# groupable — grouping is what declared Grouping Fields are for, and the bag
# exists precisely because not everything a caller wants to keep should become
# an analytics axis with a cardinality bound.
#
# Declared in concepts/retired.yaml.
#
# No constants: this kind declares no values by construction. The section is
# here so that fact is visible, rather than looking like a concept the
# generator lost.


# --- payment_rail ------------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# A mechanism through which UBB collects a tenant's customer money. Named for
# the mechanism rather than after any one provider, because activation is
# scoped per rail: one successful transaction on one rail is never read as
# proof that another is ready. Each rail carries its own readiness evidence and
# its own named approver.
#
# Declared in concepts/payment-rails.yaml.

PAYMENT_RAIL_STRIPE = 'stripe'

PAYMENT_RAIL_VALUES = frozenset({
    PAYMENT_RAIL_STRIPE,
})


# --- payment_rail_environment ------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# Which environment a rail activation was evidenced in. The distinction is the
# whole point of recording it: an automated round trip in one proves the
# integration works, and only a controlled transaction in the other proves
# money moved, was received, and reconciled exactly once.
#
# Declared in concepts/payment-rails.yaml.

PAYMENT_RAIL_ENVIRONMENT_TEST = 'test'
PAYMENT_RAIL_ENVIRONMENT_LIVE = 'live'

PAYMENT_RAIL_ENVIRONMENT_VALUES = frozenset({
    PAYMENT_RAIL_ENVIRONMENT_TEST,
    PAYMENT_RAIL_ENVIRONMENT_LIVE,
})


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


# --- pricing_book_name -------------------------------------------------------
#
# free_text — Not vocabulary. Recorded here so that "is this a value set?" is
# answered once, in data, rather than re-litigated by whoever next wants to add
# an enum to it.
#
# The display name a tenant gives a book of pricing rules. Prose a human typed.
# The record it names replaced an entity that carried supplier cost and
# customer price in one table discriminated by a column, which is the
# conflation the cost/price split exists to end (#138, #148 §5.4).
#
# Declared in concepts/retired.yaml.
#
# No constants: this kind declares no values by construction. The section is
# here so that fact is visible, rather than looking like a concept the
# generator lost.


# --- pricing_method ----------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# How a resolved pricing rule derives customer price — as a margin applied over
# supplier cost, or as a price attached directly to the event. One method per
# rule; a rule that wanted both would be two rules.
#
# Declared in concepts/economics.yaml.

PRICING_METHOD_MARGIN_OVER_COST = 'margin_over_cost'
PRICING_METHOD_DIRECT_EVENT_PRICE = 'direct_event_price'

PRICING_METHOD_VALUES = frozenset({
    PRICING_METHOD_MARGIN_OVER_COST,
    PRICING_METHOD_DIRECT_EVENT_PRICE,
})


# --- pricing_mode ------------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# Which pricing regime governs a whole Task — every event priced as it arrives,
# or one agreed price for the delivered Task. Declared on the Task kind and
# snapshotted onto the Task; both carry the same word deliberately, because
# they are one concept at two scopes and the model name already supplies the
# scope.
#
# Declared in concepts/economics.yaml.

PRICING_MODE_EVENT_PRICED = 'event_priced'
PRICING_MODE_FIXED = 'fixed'

PRICING_MODE_VALUES = frozenset({
    PRICING_MODE_EVENT_PRICED,
    PRICING_MODE_FIXED,
})


# --- pricing_receipt_subject_type --------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# What a Pricing Receipt explains — one usage row, or one canonical Charge. The
# receipt is the authoritative record of ECONOMIC RESOLUTION, not a guarantee
# that customer revenue exists: a metering-only tenant has receipts (ADR-0006).
# Its `provenance` section survives as a section name.
#
# Declared in concepts/economics.yaml.

PRICING_RECEIPT_SUBJECT_TYPE_USAGE_EVENT = 'usage_event'
PRICING_RECEIPT_SUBJECT_TYPE_CHARGE = 'charge'

PRICING_RECEIPT_SUBJECT_TYPE_VALUES = frozenset({
    PRICING_RECEIPT_SUBJECT_TYPE_USAGE_EVENT,
    PRICING_RECEIPT_SUBJECT_TYPE_CHARGE,
})


# --- pricing_status ----------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# Whether customer price for a subject is settled, and if not, why not.
# `waived` is a decision somebody made; `unknown` is information UBB does not
# have; `not_applicable` is a subject that generates no customer revenue at
# this level, such as an event inside a Task sold for one agreed price.
#
# Declared in concepts/economics.yaml.

PRICING_STATUS_KNOWN = 'known'
PRICING_STATUS_WAIVED = 'waived'
PRICING_STATUS_UNKNOWN = 'unknown'
PRICING_STATUS_NOT_APPLICABLE = 'not_applicable'

PRICING_STATUS_VALUES = frozenset({
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_WAIVED,
    PRICING_STATUS_UNKNOWN,
    PRICING_STATUS_NOT_APPLICABLE,
})


# --- rate_structure ----------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# The arithmetic shape of a rate — an amount per unit of quantity, or a
# component that applies once regardless of quantity. "Structure" means the
# mathematical shape and nothing else (ADR-0006 §3).
#
# Declared in concepts/economics.yaml.

RATE_STRUCTURE_PER_UNIT = 'per_unit'
RATE_STRUCTURE_FIXED_COMPONENT = 'fixed_component'

RATE_STRUCTURE_VALUES = frozenset({
    RATE_STRUCTURE_PER_UNIT,
    RATE_STRUCTURE_FIXED_COMPONENT,
})


# --- reason_code -------------------------------------------------------------
#
# open — UBB records the values it knows; consumers accept future and external
# ones. Checking is asymmetric — a registry-known value missing from a
# UBB-owned consumer is a defect, a runtime value the registry has never seen
# is legal.
#
# Why work was stopped, or why a bound was reported as reached. Open rather
# than closed because a stop can originate outside UBB — a provider refusal, a
# tenant's own control — and a value UBB has never seen must still travel
# rather than be rejected at the boundary. The asymmetry is the whole point: a
# value listed here and missing from a UBB-owned consumer is a defect; a value
# the registry has never seen is legal.
#
# Declared in concepts/spend-controls.yaml.

REASON_CODE_TASK_COGS_CEILING = 'task_cogs_ceiling'
REASON_CODE_CUSTOMER_SPEND_POOL = 'customer_spend_pool'
REASON_CODE_PARENT_KILLED = 'parent_killed'
REASON_CODE_SILENCE_WINDOW = 'silence_window'
REASON_CODE_HARD_FLOOR = 'hard_floor'

REASON_CODE_KNOWN_VALUES = frozenset({
    REASON_CODE_TASK_COGS_CEILING,
    REASON_CODE_CUSTOMER_SPEND_POOL,
    REASON_CODE_PARENT_KILLED,
    REASON_CODE_SILENCE_WINDOW,
    REASON_CODE_HARD_FLOOR,
})


# --- reason_detail -----------------------------------------------------------
#
# free_text — Not vocabulary. Recorded here so that "is this a value set?" is
# answered once, in data, rather than re-litigated by whoever next wants to add
# an enum to it.
#
# The sentence a caller may attach beside a reason code when a Task did not
# deliver. Display only, and never grouped on — it is the cardinality guard
# that lets the code beside it stay a small closed vocabulary (#140 §3.3).
#
# Declared in concepts/tasks.yaml.
#
# No constants: this kind declares no values by construction. The section is
# here so that fact is visible, rather than looking like a concept the
# generator lost.


# --- source_kind -------------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# Where a declared quantity comes from, and how the Code Builder is to obtain
# it. An Event Type's reported-cost mapping shares this source vocabulary but
# NARROWS it: a fixed per-call supplier cost is a configured cost rule, not a
# number that arrives per event, so `constant` is refused there (#156 §4, #179
# §3.3). Sharing the source declaration is the reuse worth having; sharing the
# whole set would let one costing method mean two things.
#
# Declared in concepts/economics.yaml.

SOURCE_KIND_PROVIDER_RESPONSE = 'provider_response'
SOURCE_KIND_CALLER_SUPPLIED = 'caller_supplied'
SOURCE_KIND_DERIVED = 'derived'
SOURCE_KIND_CONSTANT = 'constant'

SOURCE_KIND_VALUES = frozenset({
    SOURCE_KIND_PROVIDER_RESPONSE,
    SOURCE_KIND_CALLER_SUPPLIED,
    SOURCE_KIND_DERIVED,
    SOURCE_KIND_CONSTANT,
})


# --- spend_pool_enforce_mode -------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# Whether a customer spend pool only announces a crossing or also stops work. A
# blocking pool enforces identically for `prepaid` and `postpaid` — mode
# decides who invoices, not whether the bound bites (#150 §7.1).
#
# Declared in concepts/spend-controls.yaml.

SPEND_POOL_ENFORCE_MODE_ALERT_ONLY = 'alert_only'
SPEND_POOL_ENFORCE_MODE_BLOCKING = 'blocking'

SPEND_POOL_ENFORCE_MODE_VALUES = frozenset({
    SPEND_POOL_ENFORCE_MODE_ALERT_ONLY,
    SPEND_POOL_ENFORCE_MODE_BLOCKING,
})


# --- stop_behavior -----------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# What the generated integration wrapper does when UBB signals a spend stop.
# The default raises, and the signal derives from `BaseException` so a tenant's
# own broad handler cannot swallow it; `return` is available for callers who
# deliberately want to inspect the signal in line, and the generated code says
# which one it selected (#179 §1).
#
# Declared in concepts/tasks.yaml.

STOP_BEHAVIOR_RAISE = 'raise'
STOP_BEHAVIOR_RETURN = 'return'

STOP_BEHAVIOR_VALUES = frozenset({
    STOP_BEHAVIOR_RAISE,
    STOP_BEHAVIOR_RETURN,
})


# --- task_outcome ------------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# What the tenant declares when it closes a Task, and the only thing that
# decides whether a Charge fires. It is a separate concept from the resulting
# status because the caller declares an outcome and UBB records a state: a Task
# UBB already stopped does not become `delivered` because a worker said so
# late.
#
# Declared in concepts/tasks.yaml.

TASK_OUTCOME_DELIVERED = 'delivered'
TASK_OUTCOME_FAILED = 'failed'
TASK_OUTCOME_CANCELLED = 'cancelled'

TASK_OUTCOME_VALUES = frozenset({
    TASK_OUTCOME_DELIVERED,
    TASK_OUTCOME_FAILED,
    TASK_OUTCOME_CANCELLED,
})


# --- task_status -------------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# The durable state a Task or Subtask is in. `active` is the only non-terminal
# one. The three the tenant declares are reachable only by an explicit close;
# the two UBB writes are reachable only by UBB — `killed` means UBB stopped it
# on a spend signal and nothing else, and `expired` means nobody ever told UBB
# how it ended.
#
# Declared in concepts/tasks.yaml.

TASK_STATUS_ACTIVE = 'active'
TASK_STATUS_COMPLETED = 'completed'
TASK_STATUS_FAILED = 'failed'
TASK_STATUS_CANCELLED = 'cancelled'
TASK_STATUS_KILLED = 'killed'
TASK_STATUS_EXPIRED = 'expired'

TASK_STATUS_VALUES = frozenset({
    TASK_STATUS_ACTIVE,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_CANCELLED,
    TASK_STATUS_KILLED,
    TASK_STATUS_EXPIRED,
})


# --- task_type_key -----------------------------------------------------------
#
# tenant_defined — The tenant owns the values. UBB defines the field and its
# validation contract and never enumerates the set — map #137 constraint 5 as a
# schema rule, so the registry cannot become the vendor catalogue that
# constraint forbids UBB to ship.
#
# The key a tenant gives one of its own declared Task kinds. UBB owns the
# entity and its declaration rules and never enumerates the keys — map #137
# constraint 5, which is why the registry cannot become a catalogue of what the
# tenant sells.
#
# Declared in concepts/tasks.yaml.
#
# No constants: this kind declares no values by construction. The section is
# here so that fact is visible, rather than looking like a concept the
# generator lost.


# --- task_type_kind ----------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# Which level a declared Task kind may be used at. It survives the collapse of
# the two type columns into one because it is what lets a declaration be
# refused at declaration time rather than at use — a kind meant for contained
# work cannot be declared with a whole-Task pricing regime.
#
# Declared in concepts/tasks.yaml.

TASK_TYPE_KIND_TASK = 'task'
TASK_TYPE_KIND_SUBTASK = 'subtask'

TASK_TYPE_KIND_VALUES = frozenset({
    TASK_TYPE_KIND_TASK,
    TASK_TYPE_KIND_SUBTASK,
})


# --- tenant_posture ----------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# Whether UBB creates this tenant's customer charges at all. DERIVED from
# `customer_billing_mode` and never stored (ADR-0006 §4) — a second writable
# copy could disagree with the first, and the wrong one is always the one
# nobody is looking at. It is served read-only so callers need not reconstruct
# the mapping.
#
# Declared in concepts/economics.yaml.

TENANT_POSTURE_METERING_ONLY = 'metering_only'
TENANT_POSTURE_FULL_BILLING = 'full_billing'

TENANT_POSTURE_VALUES = frozenset({
    TENANT_POSTURE_METERING_ONLY,
    TENANT_POSTURE_FULL_BILLING,
})


# --- tenant_product ----------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# The products a tenant has enabled. Three, not four: the second recording lane
# was deleted along with the flag that switched it on, because there is one
# recording core and a tenant should not be choosing between two of them (#149
# §6). Subscription lifecycle gates on `billing` rather than on a flag of its
# own.
#
# Declared in concepts/economics.yaml.

TENANT_PRODUCT_METERING = 'metering'
TENANT_PRODUCT_BILLING = 'billing'
TENANT_PRODUCT_REFERRALS = 'referrals'

TENANT_PRODUCT_VALUES = frozenset({
    TENANT_PRODUCT_METERING,
    TENANT_PRODUCT_BILLING,
    TENANT_PRODUCT_REFERRALS,
})


# --- trigger_source ----------------------------------------------------------
#
# open — UBB records the values it knows; consumers accept future and external
# ones. Checking is asymmetric — a registry-known value missing from a
# UBB-owned consumer is a defect, a runtime value the registry has never seen
# is legal.
#
# The mechanism that applied a transition — which is a different question from
# the business cause, and both travel as structured fields so a webhook never
# has to carry either in its name (ADR-0006 §5). Open because the set grows
# whenever UBB adds an enforcement path, and a consumer must accept one it has
# not seen rather than reject the event carrying it.
#
# Declared in concepts/tasks.yaml.

TRIGGER_SOURCE_USAGE_INGEST = 'usage_ingest'
TRIGGER_SOURCE_ENFORCEMENT_PATROL = 'enforcement_patrol'
TRIGGER_SOURCE_PARENT_CASCADE = 'parent_cascade'
TRIGGER_SOURCE_POOL_CROSSING = 'pool_crossing'
TRIGGER_SOURCE_STALE_REAPER = 'stale_reaper'

TRIGGER_SOURCE_KNOWN_VALUES = frozenset({
    TRIGGER_SOURCE_USAGE_INGEST,
    TRIGGER_SOURCE_ENFORCEMENT_PATROL,
    TRIGGER_SOURCE_PARENT_CASCADE,
    TRIGGER_SOURCE_POOL_CROSSING,
    TRIGGER_SOURCE_STALE_REAPER,
})


# --- usage_event_kind --------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# The nature of one usage row, and NOTHING else — not the tenant, not how COGS
# was derived, not how customer price was calculated (ADR-0006 §3.8).
# `metered_usage` is a real event for work that occurred; `task_charge` is the
# synthetic posting projected from the canonical Charge when a Task sold for
# one agreed price is delivered.
#
# Declared in concepts/economics.yaml.

USAGE_EVENT_KIND_METERED_USAGE = 'metered_usage'
USAGE_EVENT_KIND_TASK_CHARGE = 'task_charge'

USAGE_EVENT_KIND_VALUES = frozenset({
    USAGE_EVENT_KIND_METERED_USAGE,
    USAGE_EVENT_KIND_TASK_CHARGE,
})


# --- webhook_event_type ------------------------------------------------------
#
# closed — UBB owns the whole value set — exactly these values, no more.
#
# Every event UBB publishes, named `<domain owner>.<past-tense state entered>`.
# A resource lifecycle transition is owned by the resource; a control's own
# state change is owned by the declared control family. Cause and mechanism
# never appear in the name — they travel as structured payload fields, so a
# subscriber classifies by subscribing rather than by parsing. Closed because
# UBB authors every one of them and a subscriber may only subscribe to a name
# UBB publishes.
#
# Declared in concepts/webhooks.yaml.

WEBHOOK_EVENT_TYPE_USAGE_RECORDED = 'usage.recorded'
WEBHOOK_EVENT_TYPE_USAGE_REFUNDED = 'usage.refunded'
WEBHOOK_EVENT_TYPE_REFUND_REQUESTED = 'refund.requested'
WEBHOOK_EVENT_TYPE_TASK_KILLED = 'task.killed'
WEBHOOK_EVENT_TYPE_TASK_EXPIRED = 'task.expired'
WEBHOOK_EVENT_TYPE_SUBTASK_KILLED = 'subtask.killed'
WEBHOOK_EVENT_TYPE_SUBTASK_EXPIRED = 'subtask.expired'
WEBHOOK_EVENT_TYPE_CUSTOMER_SPEND_POOL_THRESHOLD_REACHED = 'customer_spend_pool.threshold_reached'
WEBHOOK_EVENT_TYPE_WALLET_POLICY_SOFT_FLOOR_CROSSED = 'wallet_policy.soft_floor_crossed'
WEBHOOK_EVENT_TYPE_WALLET_POLICY_SOFT_FLOOR_CLEARED = 'wallet_policy.soft_floor_cleared'
WEBHOOK_EVENT_TYPE_CUSTOMER_STOPPED = 'customer.stopped'
WEBHOOK_EVENT_TYPE_CUSTOMER_STOP_CLEARED = 'customer.stop_cleared'
WEBHOOK_EVENT_TYPE_CUSTOMER_SUSPENDED = 'customer.suspended'
WEBHOOK_EVENT_TYPE_CUSTOMER_DELETED = 'customer.deleted'
WEBHOOK_EVENT_TYPE_CUSTOMER_UNPROFITABLE = 'customer.unprofitable'
WEBHOOK_EVENT_TYPE_PROVIDER_COST_SPIKE = 'provider.cost_spike'
WEBHOOK_EVENT_TYPE_WALLET_BALANCE_LOW = 'wallet.balance_low'
WEBHOOK_EVENT_TYPE_WALLET_BALANCE_CRITICAL = 'wallet.balance_critical'
WEBHOOK_EVENT_TYPE_WALLET_BALANCE_OVERAGE = 'wallet.balance_overage'
WEBHOOK_EVENT_TYPE_TOP_UP_REQUESTED = 'top_up.requested'
WEBHOOK_EVENT_TYPE_AUTO_TOP_UP_REQUIRES_ACTION = 'auto_top_up.requires_action'
WEBHOOK_EVENT_TYPE_WITHDRAWAL_REQUESTED = 'withdrawal.requested'
WEBHOOK_EVENT_TYPE_CREDIT_GRANT_EXPIRING = 'credit_grant.expiring'
WEBHOOK_EVENT_TYPE_CREDIT_GRANT_EXPIRED = 'credit_grant.expired'
WEBHOOK_EVENT_TYPE_USAGE_INVOICE_PUSHED = 'usage_invoice.pushed'
WEBHOOK_EVENT_TYPE_USAGE_INVOICE_PUSH_FAILED_PERMANENT = 'usage_invoice.push_failed_permanent'
WEBHOOK_EVENT_TYPE_REFERRAL_CREATED = 'referral.created'
WEBHOOK_EVENT_TYPE_REFERRAL_EXPIRED = 'referral.expired'
WEBHOOK_EVENT_TYPE_REFERRAL_REWARD_EARNED = 'referral.reward_earned'
WEBHOOK_EVENT_TYPE_REFERRAL_PAYOUT_DUE = 'referral.payout_due'
WEBHOOK_EVENT_TYPE_INVITATION_CREATED = 'invitation.created'
WEBHOOK_EVENT_TYPE_INVITATION_REVOKED = 'invitation.revoked'
WEBHOOK_EVENT_TYPE_MEMBER_ACTIVATED = 'member.activated'
WEBHOOK_EVENT_TYPE_SANDBOX_RESET_COMPLETED = 'sandbox.reset_completed'
WEBHOOK_EVENT_TYPE_TENANT_API_KEY_CREATED = 'tenant.api_key_created'
WEBHOOK_EVENT_TYPE_TENANT_API_KEY_ROTATED = 'tenant.api_key_rotated'
WEBHOOK_EVENT_TYPE_TENANT_API_KEY_REVOKED = 'tenant.api_key_revoked'

WEBHOOK_EVENT_TYPE_VALUES = frozenset({
    WEBHOOK_EVENT_TYPE_USAGE_RECORDED,
    WEBHOOK_EVENT_TYPE_USAGE_REFUNDED,
    WEBHOOK_EVENT_TYPE_REFUND_REQUESTED,
    WEBHOOK_EVENT_TYPE_TASK_KILLED,
    WEBHOOK_EVENT_TYPE_TASK_EXPIRED,
    WEBHOOK_EVENT_TYPE_SUBTASK_KILLED,
    WEBHOOK_EVENT_TYPE_SUBTASK_EXPIRED,
    WEBHOOK_EVENT_TYPE_CUSTOMER_SPEND_POOL_THRESHOLD_REACHED,
    WEBHOOK_EVENT_TYPE_WALLET_POLICY_SOFT_FLOOR_CROSSED,
    WEBHOOK_EVENT_TYPE_WALLET_POLICY_SOFT_FLOOR_CLEARED,
    WEBHOOK_EVENT_TYPE_CUSTOMER_STOPPED,
    WEBHOOK_EVENT_TYPE_CUSTOMER_STOP_CLEARED,
    WEBHOOK_EVENT_TYPE_CUSTOMER_SUSPENDED,
    WEBHOOK_EVENT_TYPE_CUSTOMER_DELETED,
    WEBHOOK_EVENT_TYPE_CUSTOMER_UNPROFITABLE,
    WEBHOOK_EVENT_TYPE_PROVIDER_COST_SPIKE,
    WEBHOOK_EVENT_TYPE_WALLET_BALANCE_LOW,
    WEBHOOK_EVENT_TYPE_WALLET_BALANCE_CRITICAL,
    WEBHOOK_EVENT_TYPE_WALLET_BALANCE_OVERAGE,
    WEBHOOK_EVENT_TYPE_TOP_UP_REQUESTED,
    WEBHOOK_EVENT_TYPE_AUTO_TOP_UP_REQUIRES_ACTION,
    WEBHOOK_EVENT_TYPE_WITHDRAWAL_REQUESTED,
    WEBHOOK_EVENT_TYPE_CREDIT_GRANT_EXPIRING,
    WEBHOOK_EVENT_TYPE_CREDIT_GRANT_EXPIRED,
    WEBHOOK_EVENT_TYPE_USAGE_INVOICE_PUSHED,
    WEBHOOK_EVENT_TYPE_USAGE_INVOICE_PUSH_FAILED_PERMANENT,
    WEBHOOK_EVENT_TYPE_REFERRAL_CREATED,
    WEBHOOK_EVENT_TYPE_REFERRAL_EXPIRED,
    WEBHOOK_EVENT_TYPE_REFERRAL_REWARD_EARNED,
    WEBHOOK_EVENT_TYPE_REFERRAL_PAYOUT_DUE,
    WEBHOOK_EVENT_TYPE_INVITATION_CREATED,
    WEBHOOK_EVENT_TYPE_INVITATION_REVOKED,
    WEBHOOK_EVENT_TYPE_MEMBER_ACTIVATED,
    WEBHOOK_EVENT_TYPE_SANDBOX_RESET_COMPLETED,
    WEBHOOK_EVENT_TYPE_TENANT_API_KEY_CREATED,
    WEBHOOK_EVENT_TYPE_TENANT_API_KEY_ROTATED,
    WEBHOOK_EVENT_TYPE_TENANT_API_KEY_REVOKED,
})
