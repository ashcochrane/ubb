// @generated from domain-vocabulary/ — do not edit by hand.
// Regenerate with `python -m tools.vocabulary --write`.

/**
 * Canonical vocabulary values and label keys, generated from the registry.
 *
 * `domain-vocabulary/` at the git root is the checked-in statement of what every
 * UBB-owned concept is called and what values it may take (ADR-0008 §2). This
 * module is that registry rendered as TypeScript, so the console holds a
 * canonical value by REFERENCE and cannot keep a second copy of it that drifts.
 *
 * Three names per valued concept:
 *
 *     <CONCEPT>_VALUES        a `closed` concept — exactly these, no more.
 *     <CONCEPT>_KNOWN_VALUES  an `open` concept — what UBB knows today. A value
 *                             that is not in it is still legal, so this array
 *                             never decides a rejection (ADR-0003) and the
 *                             concept's type admits any string.
 *     <CONCEPT>_LABEL_KEYS    the stable key each value's wording is looked up
 *                             under — keys, never words.
 *
 * **The English is deliberately absent.** ADR-0008 §4 draws the line at the point
 * vocabulary becomes copy: wording, capitalisation and translation change far
 * more often than the token underneath, and a vocabulary file that became the copy
 * deck would either turn into an i18n database or privilege English inside the
 * domain model. The catalogue that attaches words to these keys is the console's
 * own, and it is checked against these keys both ways (#210).
 *
 * `satisfies Record<..., string>` on each label map is load-bearing rather than
 * decorative: it is the console's own compiler proving the map covers every value
 * of its concept, at the moment a value is added to the registry.
 */

// --- affordability_reason ---------------------------------------------------
//
// open — UBB records the values it knows; consumers accept future and external
// ones. Checking is asymmetric — a registry-known value missing from a
// UBB-owned consumer is a defect, a runtime value the registry has never seen
// is legal.
//
// Why an affordability question was answered no. The question names what is
// being asked rather than the object inspected, so it stays true if a credit
// line or a grant later becomes an input. Open for the same reason as the stop
// vocabulary beside it: a refusal can arise from a control UBB gains later,
// and a caller must render one it has not seen rather than fail.
//
// Declared in concepts/spend-controls.yaml.

export const AFFORDABILITY_REASON_KNOWN_VALUES = [
  "insufficient_funds",
  "account_closed",
  "customer_stopped",
  "soft_floor_reached",
  "rate_limit_exceeded",
  "customer_spend_pool_exceeded",
  "customer_spend_pool_unavailable",
  "parent_task_not_active",
  "subtask_depth_exceeded",
] as const;

export type AffordabilityReasonKnown = (typeof AFFORDABILITY_REASON_KNOWN_VALUES)[number];

// An `open` concept: a value UBB has never seen is legal (ADR-0003), so the
// type admits any string. The intersection is what stops TypeScript collapsing
// the union to `string` and losing the known values a reader is offered.
export type AffordabilityReason = AffordabilityReasonKnown | (string & {});

export const AFFORDABILITY_REASON_LABEL_KEYS = {
  "insufficient_funds": "affordability_reason.insufficient_funds",
  "account_closed": "affordability_reason.account_closed",
  "customer_stopped": "affordability_reason.customer_stopped",
  "soft_floor_reached": "affordability_reason.soft_floor_reached",
  "rate_limit_exceeded": "affordability_reason.rate_limit_exceeded",
  "customer_spend_pool_exceeded": "affordability_reason.customer_spend_pool_exceeded",
  "customer_spend_pool_unavailable": "affordability_reason.customer_spend_pool_unavailable",
  "parent_task_not_active": "affordability_reason.parent_task_not_active",
  "subtask_depth_exceeded": "affordability_reason.subtask_depth_exceeded",
} as const satisfies Record<AffordabilityReasonKnown, string>;


// --- amount_representation --------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// What an extracted supplier-cost number actually represents, so the
// conversion to currency micros is generated once and exactly rather than
// written by hand in a repository UBB never sees. Declaring it is what keeps
// "no float enters money arithmetic" true across the boundary (#179 §3.4).
//
// Declared in concepts/economics.yaml.

export const AMOUNT_REPRESENTATION_VALUES = [
  "micros",
  "minor_units",
  "major_units_decimal",
] as const;

export type AmountRepresentation = (typeof AMOUNT_REPRESENTATION_VALUES)[number];

export const AMOUNT_REPRESENTATION_LABEL_KEYS = {
  "micros": "amount_representation.micros",
  "minor_units": "amount_representation.minor_units",
  "major_units_decimal": "amount_representation.major_units_decimal",
} as const satisfies Record<AmountRepresentation, string>;


// --- analytics_grouping_kind ------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// Whether a grouping axis is a column on the event or a join to a declared
// rollup. The namespace is deliberate: a field and a rollup have materially
// different cardinality and query cost, and hiding that behind identical
// looking strings is how a chart times out in production (#153 §5.3).
//
// Declared in concepts/economics.yaml.

export const ANALYTICS_GROUPING_KIND_VALUES = [
  "field",
  "rollup",
] as const;

export type AnalyticsGroupingKind = (typeof ANALYTICS_GROUPING_KIND_VALUES)[number];

export const ANALYTICS_GROUPING_KIND_LABEL_KEYS = {
  "field": "analytics_grouping_kind.field",
  "rollup": "analytics_grouping_kind.rollup",
} as const satisfies Record<AnalyticsGroupingKind, string>;


// --- analytics_measure ------------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// The four things the economic query can measure. Each name says which side of
// the trade it sits on, and `recorded_events` says plainly that it counts
// records at the tenant's declared granularity rather than units of work.
//
// Declared in concepts/economics.yaml.

export const ANALYTICS_MEASURE_VALUES = [
  "supplier_cogs",
  "customer_revenue",
  "gross_margin",
  "recorded_events",
] as const;

export type AnalyticsMeasure = (typeof ANALYTICS_MEASURE_VALUES)[number];

export const ANALYTICS_MEASURE_LABEL_KEYS = {
  "supplier_cogs": "analytics_measure.supplier_cogs",
  "customer_revenue": "analytics_measure.customer_revenue",
  "gross_margin": "analytics_measure.gross_margin",
  "recorded_events": "analytics_measure.recorded_events",
} as const satisfies Record<AnalyticsMeasure, string>;


// --- analytics_rollup -------------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// The aggregation axes UBB itself owns, one level above what the tenant
// declares. The tenant assigns members to them; the axes themselves are UBB's.
// Rollup membership is analytical taxonomy and may reclassify history, which
// is safe precisely because it touches no money (#153 §5.5).
//
// Declared in concepts/economics.yaml.

export const ANALYTICS_ROLLUP_VALUES = [
  "event_category",
  "measurement_concept",
] as const;

export type AnalyticsRollup = (typeof ANALYTICS_ROLLUP_VALUES)[number];

export const ANALYTICS_ROLLUP_LABEL_KEYS = {
  "event_category": "analytics_rollup.event_category",
  "measurement_concept": "analytics_rollup.measurement_concept",
} as const satisfies Record<AnalyticsRollup, string>;


// --- audit_action -----------------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// Every action the tenant governance ledger may record, as `noun.verb`. The
// ledger refuses an unregistered name, which is what stops the registered set
// from drifting from what is actually written. Closed for the same reason: UBB
// authors every one of them, and a name nothing may write is not an action.
//
// Declared in concepts/governance.yaml.

export const AUDIT_ACTION_VALUES = [
  "api_key.created",
  "api_key.rotated",
  "api_key.revoked",
  "invitation.created",
  "invitation.revoked",
  "member.role_changed",
  "member.removed",
  "tenant.config_changed",
  "sandbox.created",
  "sandbox.reset",
  "connect.started",
  "billing_profile.set",
  "auto_top_up.configured",
  "postpaid_config.set",
  "customer_spend_pool.set",
  "margin_threshold.set",
  "wallet.credited",
  "wallet.debited",
  "wallet.withdrawn",
  "top_up.requested",
  "usage.refunded",
  "grant.created",
  "grant.voided",
  "pricing_book.created",
  "pricing_book.assigned",
  "pricing_book.published",
  "cost_rate.added",
  "cost_rate.deleted",
  "pricing_rule.added",
  "pricing_rule.deleted",
  "customer_pricing_override.set",
  "event_type.declared",
  "measurement.declared",
  "grouping_field.declared",
  "task_type.declared",
  "tenant_supplied_revenue.recorded",
  "customer.created",
  "plan.created",
  "plan.updated",
  "plan.archived",
  "plan.assigned",
  "subscription.created",
  "subscription.canceled",
  "subscription.paused",
  "subscription.resumed",
  "subscription.seats_changed",
  "referral_program.created",
  "referral_program.updated",
  "referral_program.deactivated",
  "referral_program.reactivated",
  "referrer.registered",
  "referral.attributed",
  "referral.revoked",
  "webhook_config.created",
  "webhook_config.updated",
  "webhook_config.deleted",
  "webhook_config.secret_rotated",
  "system.preproduction_model_cutover",
] as const;

export type AuditAction = (typeof AUDIT_ACTION_VALUES)[number];

export const AUDIT_ACTION_LABEL_KEYS = {
  "api_key.created": "audit_action.api_key.created",
  "api_key.rotated": "audit_action.api_key.rotated",
  "api_key.revoked": "audit_action.api_key.revoked",
  "invitation.created": "audit_action.invitation.created",
  "invitation.revoked": "audit_action.invitation.revoked",
  "member.role_changed": "audit_action.member.role_changed",
  "member.removed": "audit_action.member.removed",
  "tenant.config_changed": "audit_action.tenant.config_changed",
  "sandbox.created": "audit_action.sandbox.created",
  "sandbox.reset": "audit_action.sandbox.reset",
  "connect.started": "audit_action.connect.started",
  "billing_profile.set": "audit_action.billing_profile.set",
  "auto_top_up.configured": "audit_action.auto_top_up.configured",
  "postpaid_config.set": "audit_action.postpaid_config.set",
  "customer_spend_pool.set": "audit_action.customer_spend_pool.set",
  "margin_threshold.set": "audit_action.margin_threshold.set",
  "wallet.credited": "audit_action.wallet.credited",
  "wallet.debited": "audit_action.wallet.debited",
  "wallet.withdrawn": "audit_action.wallet.withdrawn",
  "top_up.requested": "audit_action.top_up.requested",
  "usage.refunded": "audit_action.usage.refunded",
  "grant.created": "audit_action.grant.created",
  "grant.voided": "audit_action.grant.voided",
  "pricing_book.created": "audit_action.pricing_book.created",
  "pricing_book.assigned": "audit_action.pricing_book.assigned",
  "pricing_book.published": "audit_action.pricing_book.published",
  "cost_rate.added": "audit_action.cost_rate.added",
  "cost_rate.deleted": "audit_action.cost_rate.deleted",
  "pricing_rule.added": "audit_action.pricing_rule.added",
  "pricing_rule.deleted": "audit_action.pricing_rule.deleted",
  "customer_pricing_override.set": "audit_action.customer_pricing_override.set",
  "event_type.declared": "audit_action.event_type.declared",
  "measurement.declared": "audit_action.measurement.declared",
  "grouping_field.declared": "audit_action.grouping_field.declared",
  "task_type.declared": "audit_action.task_type.declared",
  "tenant_supplied_revenue.recorded": "audit_action.tenant_supplied_revenue.recorded",
  "customer.created": "audit_action.customer.created",
  "plan.created": "audit_action.plan.created",
  "plan.updated": "audit_action.plan.updated",
  "plan.archived": "audit_action.plan.archived",
  "plan.assigned": "audit_action.plan.assigned",
  "subscription.created": "audit_action.subscription.created",
  "subscription.canceled": "audit_action.subscription.canceled",
  "subscription.paused": "audit_action.subscription.paused",
  "subscription.resumed": "audit_action.subscription.resumed",
  "subscription.seats_changed": "audit_action.subscription.seats_changed",
  "referral_program.created": "audit_action.referral_program.created",
  "referral_program.updated": "audit_action.referral_program.updated",
  "referral_program.deactivated": "audit_action.referral_program.deactivated",
  "referral_program.reactivated": "audit_action.referral_program.reactivated",
  "referrer.registered": "audit_action.referrer.registered",
  "referral.attributed": "audit_action.referral.attributed",
  "referral.revoked": "audit_action.referral.revoked",
  "webhook_config.created": "audit_action.webhook_config.created",
  "webhook_config.updated": "audit_action.webhook_config.updated",
  "webhook_config.deleted": "audit_action.webhook_config.deleted",
  "webhook_config.secret_rotated": "audit_action.webhook_config.secret_rotated",
  "system.preproduction_model_cutover": "audit_action.system.preproduction_model_cutover",
} as const satisfies Record<AuditAction, string>;


// --- ceiling_basis ----------------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// What a Ceiling bounds. Cost and time genuinely are different columns in
// different units, so each ceiling field states its own basis and unit rather
// than one field switching unit, storage and comparison at once (#150 §2.3).
//
// Declared in concepts/spend-controls.yaml.

export const CEILING_BASIS_VALUES = [
  "cost",
  "time",
] as const;

export type CeilingBasis = (typeof CEILING_BASIS_VALUES)[number];

export const CEILING_BASIS_LABEL_KEYS = {
  "cost": "ceiling_basis.cost",
  "time": "ceiling_basis.time",
} as const satisfies Record<CeilingBasis, string>;


// --- ceiling_status ---------------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// What a ceiling assessment concluded for one Task. `indeterminate` is kept
// distinct from an unresolved cost on purpose: an unresolved cost is a missing
// value, and `indeterminate` is the resulting inability to evaluate the
// ceiling (#158 §12.2).
//
// Declared in concepts/spend-controls.yaml.
//
// Decision rule, declared as registry data and proved total and unambiguous by
// the compiler:
//
//   The lower-bound rule (#158 §12.3). Once the KNOWN portion of accumulated
//   COGS has reached the ceiling, costs still unresolved cannot argue the Task
//   back under it — this is a spend-control safety invariant rather than a
//   naming detail, which is why it is carried beside the values as data. `>=`
//   is the comparison, so a ceiling is reached rather than exceeded.
//
//   a_ceiling_applies=false, known_cogs_at_or_above_ceiling=any,
//   unresolved_costs_remain=any
//     -> not_applicable
//        Nothing was evaluated, so nothing was concluded. `indeterminate`
//        means UBB tried and could not tell, never that there was nothing to
//        try (#158 §12.4).
//
//   a_ceiling_applies=true, known_cogs_at_or_above_ceiling=true,
//   unresolved_costs_remain=any
//     -> ceiling_reached
//        The known accumulated COGS is already at or above the ceiling. Costs
//        that are still unresolved can only add to it, so no later resolution
//        can reverse this answer — reporting anything softer here would let an
//        unresolved cost buy a Task more spending.
//
//   a_ceiling_applies=true, known_cogs_at_or_above_ceiling=false,
//   unresolved_costs_remain=true
//     -> indeterminate
//        The known lower bound is still below the ceiling and at least one
//        applicable cost is unresolved, so UBB cannot prove the Task is inside
//        it. This is the only case the word covers.
//
//   a_ceiling_applies=true, known_cogs_at_or_above_ceiling=false,
//   unresolved_costs_remain=false
//     -> within_ceiling
//        Every applicable cost is resolved and the total is below the ceiling,
//        which is the only state in which UBB can say so positively.

export const CEILING_STATUS_VALUES = [
  "within_ceiling",
  "ceiling_reached",
  "indeterminate",
  "not_applicable",
] as const;

export type CeilingStatus = (typeof CEILING_STATUS_VALUES)[number];

export const CEILING_STATUS_LABEL_KEYS = {
  "within_ceiling": "ceiling_status.within_ceiling",
  "ceiling_reached": "ceiling_status.ceiling_reached",
  "indeterminate": "ceiling_status.indeterminate",
  "not_applicable": "ceiling_status.not_applicable",
} as const satisfies Record<CeilingStatus, string>;


// --- control_family ---------------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// Which of the four spend controls a signal came from. The same four words are
// the webhook namespace, the analytics family and this field, because one
// public concept gets one public name (ADR-0006 §2). A Ceiling bounds one unit
// of work, a customer spend pool bounds one customer's charges over a period,
// a wallet policy holds the floors, and admission control bounds the rate of
// new work and says nothing about supplier cost at all.
//
// Declared in concepts/spend-controls.yaml.

export const CONTROL_FAMILY_VALUES = [
  "ceiling",
  "customer_spend_pool",
  "wallet_policy",
  "admission_control",
] as const;

export type ControlFamily = (typeof CONTROL_FAMILY_VALUES)[number];

export const CONTROL_FAMILY_LABEL_KEYS = {
  "ceiling": "control_family.ceiling",
  "customer_spend_pool": "control_family.customer_spend_pool",
  "wallet_policy": "control_family.wallet_policy",
  "admission_control": "control_family.admission_control",
} as const satisfies Record<ControlFamily, string>;


// --- costing_method ---------------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// How an Event Type's supplier COGS is derived — `calculated` from declared
// Measurements against CostRates, or `reported` from a value the provider or
// the caller supplies. "Method" means how an amount is derived, and never
// which operating regime applies (ADR-0006 §3).
//
// Declared in concepts/economics.yaml.

export const COSTING_METHOD_VALUES = [
  "calculated",
  "reported",
] as const;

export type CostingMethod = (typeof COSTING_METHOD_VALUES)[number];

export const COSTING_METHOD_LABEL_KEYS = {
  "calculated": "costing_method.calculated",
  "reported": "costing_method.reported",
} as const satisfies Record<CostingMethod, string>;


// --- costing_status ---------------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// Whether supplier COGS for a subject is settled. `unresolved` and a NULL
// amount are one fact and travel together; zero is a resolved amount and means
// something else entirely (ADR-0007 §2).
//
// Declared in concepts/economics.yaml.

export const COSTING_STATUS_VALUES = [
  "known",
  "unresolved",
  "not_applicable",
] as const;

export type CostingStatus = (typeof COSTING_STATUS_VALUES)[number];

export const COSTING_STATUS_LABEL_KEYS = {
  "known": "costing_status.known",
  "unresolved": "costing_status.unresolved",
  "not_applicable": "costing_status.not_applicable",
} as const satisfies Record<CostingStatus, string>;


// --- customer_billing_mode --------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// What UBB does about money for a tenant's customers. `external` means the
// tenant bills their customers somewhere else and UBB only meters; `prepaid`
// and `postpaid` mean UBB drives the money, and neither may be activated
// before its payment rail has been (ADR-0008 §6).
//
// Declared in concepts/economics.yaml.

export const CUSTOMER_BILLING_MODE_VALUES = [
  "external",
  "prepaid",
  "postpaid",
] as const;

export type CustomerBillingMode = (typeof CUSTOMER_BILLING_MODE_VALUES)[number];

export const CUSTOMER_BILLING_MODE_LABEL_KEYS = {
  "external": "customer_billing_mode.external",
  "prepaid": "customer_billing_mode.prepaid",
  "postpaid": "customer_billing_mode.postpaid",
} as const satisfies Record<CustomerBillingMode, string>;


// --- declaration_status -----------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// Whether a tenant's declaration is still being drafted or has been published
// for integrations to be generated against. Publication is what pins the
// response shape, the structured paths and the reported-cost mapping, because
// an incorrect mapping produces an incorrect supplier cost — so a later change
// is a revised publication, never a silent reinterpretation of integrations
// already generated and deployed (#193 §B7).
//
// Declared in concepts/economics.yaml.

export const DECLARATION_STATUS_VALUES = [
  "draft",
  "published",
] as const;

export type DeclarationStatus = (typeof DECLARATION_STATUS_VALUES)[number];

export const DECLARATION_STATUS_LABEL_KEYS = {
  "draft": "declaration_status.draft",
  "published": "declaration_status.published",
} as const satisfies Record<DeclarationStatus, string>;


// --- event_type_key ---------------------------------------------------------
//
// tenant_defined — The tenant owns the values. UBB defines the field and its
// validation contract and never enumerates the set — map #137 constraint 5 as
// a schema rule, so the registry cannot become the vendor catalogue that
// constraint forbids UBB to ship.
//
// The key a tenant gives one of its own registered Event Types. UBB owns the
// entity, its costing declaration and its validation contract, and never
// enumerates the keys: doing so would make the registry a catalogue of the
// tenant's providers and calls, which map #137 constraint 5 forbids UBB to
// ship.
//
// Declared in concepts/economics.yaml.
//
// No constants: this kind declares no values by construction. The section is
// here so that fact is visible, rather than looking like a concept the
// generator lost.


// --- external_task_id -------------------------------------------------------
//
// free_text — Not vocabulary. Recorded here so that "is this a value set?" is
// answered once, in data, rather than re-litigated by whoever next wants to
// add an enum to it.
//
// The caller's own identifier for a Task, carried so an engineer can find
// their side of the record from UBB's. Opaque to UBB, which neither parses it
// nor groups on it.
//
// Declared in concepts/tasks.yaml.
//
// No constants: this kind declares no values by construction. The section is
// here so that fact is visible, rather than looking like a concept the
// generator lost.


// --- grouping_field_value ---------------------------------------------------
//
// tenant_defined — The tenant owns the values. UBB defines the field and its
// validation contract and never enumerates the set — map #137 constraint 5 as
// a schema rule, so the registry cannot become the vendor catalogue that
// constraint forbids UBB to ship.
//
// A value a tenant reports on one of its own declared grouping fields — a
// model name, a region, a customer tier. UBB bounds the keyspace (ADR-0005's
// cardinality cap) and never enumerates the values: doing so would make the
// registry a catalogue of the tenant's suppliers and models, which map #137
// constraint 5 forbids UBB to ship.
//
// Declared in concepts/economics.yaml.
//
// No constants: this kind declares no values by construction. The section is
// here so that fact is visible, rather than looking like a concept the
// generator lost.


// --- idempotency_key --------------------------------------------------------
//
// free_text — Not vocabulary. Recorded here so that "is this a value set?" is
// answered once, in data, rather than re-litigated by whoever next wants to
// add an enum to it.
//
// The caller's key for making a retried write safe. Opaque to UBB beyond its
// length bound, and the only caller-supplied correlation value on the
// recording path — which is what made the second one removable: it had no
// uniqueness constraint, no lookup, no filter and no read that changed any
// behaviour, while carrying an index write on the hottest path in the system
// (#179 §4).
//
// Declared in concepts/retired.yaml.
//
// No constants: this kind declares no values by construction. The section is
// here so that fact is visible, rather than looking like a concept the
// generator lost.


// --- live_counter_maintenance_enabled ---------------------------------------
//
// free_text — Not vocabulary. Recorded here so that "is this a value set?" is
// answered once, in data, rather than re-litigated by whoever next wants to
// add an enum to it.
//
// The per-tenant switch selecting WHEN the live spend counters are maintained:
// ON debits them synchronously on the recording path and checks the crossing
// there, so the ack itself carries the stop verdict; OFF does no counter work
// at record time and the durable drawdown detects instead, at its own latency.
// It was named for the arrival-time ingest lane. Slice 1 (#192) deleted that
// lane and kept the switch, because it never was the lane's switch — it also
// gates both reconciles' counter legs and the upward repair, none of which is
// arrival-shaped, and the conflation cost a whole ticket (#233) to unpick when
// `repair.py` was read under the wrong meaning. Renamed by #246 while the
// pre-live contract window was still open (ADR-0007 §5), because after
// platform admission the same word costs a 90-day deprecation cycle.
//
// Declared in concepts/retired.yaml.
//
// No constants: this kind declares no values by construction. The section is
// here so that fact is visible, rather than looking like a concept the
// generator lost.


// --- measure_status ---------------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// What one requested measure's amount is worth in a response. Four facts that
// used to be one integer: `incomplete` says some input is still unresolved,
// `unavailable_at_requested_grain` says the number exists but cannot be
// attributed this finely, and `not_applicable` says the measure does not apply
// here. No query may coerce any of them to zero (#153 §8.5).
//
// Declared in concepts/economics.yaml.

export const MEASURE_STATUS_VALUES = [
  "known",
  "incomplete",
  "unavailable_at_requested_grain",
  "not_applicable",
] as const;

export type MeasureStatus = (typeof MEASURE_STATUS_VALUES)[number];

export const MEASURE_STATUS_LABEL_KEYS = {
  "known": "measure_status.known",
  "incomplete": "measure_status.incomplete",
  "unavailable_at_requested_grain": "measure_status.unavailable_at_requested_grain",
  "not_applicable": "measure_status.not_applicable",
} as const satisfies Record<MeasureStatus, string>;


// --- measurement_key --------------------------------------------------------
//
// tenant_defined — The tenant owns the values. UBB defines the field and its
// validation contract and never enumerates the set — map #137 constraint 5 as
// a schema rule, so the registry cannot become the vendor catalogue that
// constraint forbids UBB to ship.
//
// The key a tenant gives one of its own declared measurable quantities. UBB
// owns the entity, its unit and its value type, and never enumerates the keys.
// The industry uses the retired word for the metered ENTITY rather than for
// the quantity inside it, so keeping it here would have guaranteed
// mis-translation at every integration boundary (#145 §10).
//
// Declared in concepts/retired.yaml.
//
// No constants: this kind declares no values by construction. The section is
// here so that fact is visible, rather than looking like a concept the
// generator lost.


// --- metadata_key -----------------------------------------------------------
//
// tenant_defined — The tenant owns the values. UBB defines the field and its
// validation contract and never enumerates the set — map #137 constraint 5 as
// a schema rule, so the registry cannot become the vendor catalogue that
// constraint forbids UBB to ship.
//
// A key in the one open bag a tenant may attach to a record. Filterable, never
// groupable — grouping is what declared Grouping Fields are for, and the bag
// exists precisely because not everything a caller wants to keep should become
// an analytics axis with a cardinality bound.
//
// Declared in concepts/retired.yaml.
//
// No constants: this kind declares no values by construction. The section is
// here so that fact is visible, rather than looking like a concept the
// generator lost.


// --- payment_rail -----------------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// A mechanism through which UBB collects a tenant's customer money. Named for
// the mechanism rather than after any one provider, because activation is
// scoped per rail: one successful transaction on one rail is never read as
// proof that another is ready. Each rail carries its own readiness evidence
// and its own named approver.
//
// Declared in concepts/payment-rails.yaml.

export const PAYMENT_RAIL_VALUES = [
  "stripe",
] as const;

export type PaymentRail = (typeof PAYMENT_RAIL_VALUES)[number];

export const PAYMENT_RAIL_LABEL_KEYS = {
  "stripe": "payment_rail.stripe",
} as const satisfies Record<PaymentRail, string>;


// --- payment_rail_environment -----------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// Which environment a rail activation was evidenced in. The distinction is the
// whole point of recording it: an automated round trip in one proves the
// integration works, and only a controlled transaction in the other proves
// money moved, was received, and reconciled exactly once.
//
// Declared in concepts/payment-rails.yaml.

export const PAYMENT_RAIL_ENVIRONMENT_VALUES = [
  "test",
  "live",
] as const;

export type PaymentRailEnvironment = (typeof PAYMENT_RAIL_ENVIRONMENT_VALUES)[number];

export const PAYMENT_RAIL_ENVIRONMENT_LABEL_KEYS = {
  "test": "payment_rail_environment.test",
  "live": "payment_rail_environment.live",
} as const satisfies Record<PaymentRailEnvironment, string>;


// --- plan_name --------------------------------------------------------------
//
// free_text — Not vocabulary. Recorded here so that "is this a value set?" is
// answered once, in data, rather than re-litigated by whoever next wants to
// add an enum to it.
//
// The display name a tenant gives a plan. Prose a human typed, not a token —
// it is recorded here so that "should plan names be an enum?" is answered
// once, in data, and never re-opened. A `free_text` concept declares no values
// by construction; that absence IS its content.
//
// Declared in concepts/economics.yaml.
//
// No constants: this kind declares no values by construction. The section is
// here so that fact is visible, rather than looking like a concept the
// generator lost.


// --- pricing_book_name ------------------------------------------------------
//
// free_text — Not vocabulary. Recorded here so that "is this a value set?" is
// answered once, in data, rather than re-litigated by whoever next wants to
// add an enum to it.
//
// The display name a tenant gives a book of pricing rules. Prose a human
// typed. The record it names replaced an entity that carried supplier cost and
// customer price in one table discriminated by a column, which is the
// conflation the cost/price split exists to end (#138, #148 §5.4).
//
// Declared in concepts/retired.yaml.
//
// No constants: this kind declares no values by construction. The section is
// here so that fact is visible, rather than looking like a concept the
// generator lost.


// --- pricing_method ---------------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// How a resolved pricing rule derives customer price — as a margin applied
// over supplier cost, or as a price attached directly to the event. One method
// per rule; a rule that wanted both would be two rules.
//
// Declared in concepts/economics.yaml.

export const PRICING_METHOD_VALUES = [
  "margin_over_cost",
  "direct_event_price",
] as const;

export type PricingMethod = (typeof PRICING_METHOD_VALUES)[number];

export const PRICING_METHOD_LABEL_KEYS = {
  "margin_over_cost": "pricing_method.margin_over_cost",
  "direct_event_price": "pricing_method.direct_event_price",
} as const satisfies Record<PricingMethod, string>;


// --- pricing_mode -----------------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// Which pricing regime governs a whole Task — every event priced as it
// arrives, or one agreed price for the delivered Task. Declared on the Task
// kind and snapshotted onto the Task; both carry the same word deliberately,
// because they are one concept at two scopes and the model name already
// supplies the scope.
//
// Declared in concepts/economics.yaml.

export const PRICING_MODE_VALUES = [
  "event_priced",
  "fixed",
] as const;

export type PricingMode = (typeof PRICING_MODE_VALUES)[number];

export const PRICING_MODE_LABEL_KEYS = {
  "event_priced": "pricing_mode.event_priced",
  "fixed": "pricing_mode.fixed",
} as const satisfies Record<PricingMode, string>;


// --- pricing_receipt_subject_type -------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// What a Pricing Receipt explains — one usage row, or one canonical Charge.
// The receipt is the authoritative record of ECONOMIC RESOLUTION, not a
// guarantee that customer revenue exists: a metering-only tenant has receipts
// (ADR-0006). Its `provenance` section survives as a section name.
//
// Declared in concepts/economics.yaml.

export const PRICING_RECEIPT_SUBJECT_TYPE_VALUES = [
  "usage_event",
  "charge",
] as const;

export type PricingReceiptSubjectType = (typeof PRICING_RECEIPT_SUBJECT_TYPE_VALUES)[number];

export const PRICING_RECEIPT_SUBJECT_TYPE_LABEL_KEYS = {
  "usage_event": "pricing_receipt_subject_type.usage_event",
  "charge": "pricing_receipt_subject_type.charge",
} as const satisfies Record<PricingReceiptSubjectType, string>;


// --- pricing_status ---------------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// Whether customer price for a subject is settled, and if not, why not.
// `waived` is a decision somebody made; `unknown` is information UBB does not
// have; `not_applicable` is a subject that generates no customer revenue at
// this level, such as an event inside a Task sold for one agreed price.
//
// Declared in concepts/economics.yaml.

export const PRICING_STATUS_VALUES = [
  "known",
  "waived",
  "unknown",
  "not_applicable",
] as const;

export type PricingStatus = (typeof PRICING_STATUS_VALUES)[number];

export const PRICING_STATUS_LABEL_KEYS = {
  "known": "pricing_status.known",
  "waived": "pricing_status.waived",
  "unknown": "pricing_status.unknown",
  "not_applicable": "pricing_status.not_applicable",
} as const satisfies Record<PricingStatus, string>;


// --- rate_structure ---------------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// The arithmetic shape of a rate — an amount per unit of quantity, or a
// component that applies once regardless of quantity. "Structure" means the
// mathematical shape and nothing else (ADR-0006 §3).
//
// Declared in concepts/economics.yaml.

export const RATE_STRUCTURE_VALUES = [
  "per_unit",
  "fixed_component",
] as const;

export type RateStructure = (typeof RATE_STRUCTURE_VALUES)[number];

export const RATE_STRUCTURE_LABEL_KEYS = {
  "per_unit": "rate_structure.per_unit",
  "fixed_component": "rate_structure.fixed_component",
} as const satisfies Record<RateStructure, string>;


// --- reason_code ------------------------------------------------------------
//
// open — UBB records the values it knows; consumers accept future and external
// ones. Checking is asymmetric — a registry-known value missing from a
// UBB-owned consumer is a defect, a runtime value the registry has never seen
// is legal.
//
// Why work was stopped, or why a bound was reported as reached. Open rather
// than closed because a stop can originate outside UBB — a provider refusal, a
// tenant's own control — and a value UBB has never seen must still travel
// rather than be rejected at the boundary. The asymmetry is the whole point: a
// value listed here and missing from a UBB-owned consumer is a defect; a value
// the registry has never seen is legal.
//
// Declared in concepts/spend-controls.yaml.

export const REASON_CODE_KNOWN_VALUES = [
  "task_cogs_ceiling",
  "customer_spend_pool",
  "parent_killed",
  "silence_window",
  "hard_floor",
] as const;

export type ReasonCodeKnown = (typeof REASON_CODE_KNOWN_VALUES)[number];

// An `open` concept: a value UBB has never seen is legal (ADR-0003), so the
// type admits any string. The intersection is what stops TypeScript collapsing
// the union to `string` and losing the known values a reader is offered.
export type ReasonCode = ReasonCodeKnown | (string & {});

export const REASON_CODE_LABEL_KEYS = {
  "task_cogs_ceiling": "reason_code.task_cogs_ceiling",
  "customer_spend_pool": "reason_code.customer_spend_pool",
  "parent_killed": "reason_code.parent_killed",
  "silence_window": "reason_code.silence_window",
  "hard_floor": "reason_code.hard_floor",
} as const satisfies Record<ReasonCodeKnown, string>;


// --- reason_detail ----------------------------------------------------------
//
// free_text — Not vocabulary. Recorded here so that "is this a value set?" is
// answered once, in data, rather than re-litigated by whoever next wants to
// add an enum to it.
//
// The sentence a caller may attach beside a reason code when a Task did not
// deliver. Display only, and never grouped on — it is the cardinality guard
// that lets the code beside it stay a small closed vocabulary (#140 §3.3).
//
// Declared in concepts/tasks.yaml.
//
// No constants: this kind declares no values by construction. The section is
// here so that fact is visible, rather than looking like a concept the
// generator lost.


// --- source_kind ------------------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// Where a declared quantity comes from, and how the Code Builder is to obtain
// it. An Event Type's reported-cost mapping shares this source vocabulary but
// NARROWS it: a fixed per-call supplier cost is a configured cost rule, not a
// number that arrives per event, so `constant` is refused there (#156 §4, #179
// §3.3). Sharing the source declaration is the reuse worth having; sharing the
// whole set would let one costing method mean two things.
//
// Declared in concepts/economics.yaml.

export const SOURCE_KIND_VALUES = [
  "provider_response",
  "caller_supplied",
  "derived",
  "constant",
] as const;

export type SourceKind = (typeof SOURCE_KIND_VALUES)[number];

export const SOURCE_KIND_LABEL_KEYS = {
  "provider_response": "source_kind.provider_response",
  "caller_supplied": "source_kind.caller_supplied",
  "derived": "source_kind.derived",
  "constant": "source_kind.constant",
} as const satisfies Record<SourceKind, string>;


// --- source_shape_id --------------------------------------------------------
//
// open — UBB records the values it knows; consumers accept future and external
// ones. Checking is asymmetric — a registry-known value missing from a
// UBB-owned consumer is a defect, a runtime value the registry has never seen
// is legal.
//
// Which provider response shape a tenant's declared paths are written against,
// declared once at the Event Type so two quantities beneath it can never
// disagree about which client they are mapped to. UBB uses it to WARN that a
// path looks inconsistent with a shape it knows, and never to substitute one:
// rendering a supplier's own field name would make UBB's catalogue
// commercially load-bearing by the back door.
//
// Declared in concepts/economics.yaml.

export const SOURCE_SHAPE_ID_KNOWN_VALUES = [
  "google.gemini.rest.v1",
  "google.genai.python.v1",
  "openai.responses.python.v1",
  "custom",
] as const;

export type SourceShapeIdKnown = (typeof SOURCE_SHAPE_ID_KNOWN_VALUES)[number];

// An `open` concept: a value UBB has never seen is legal (ADR-0003), so the
// type admits any string. The intersection is what stops TypeScript collapsing
// the union to `string` and losing the known values a reader is offered.
export type SourceShapeId = SourceShapeIdKnown | (string & {});

export const SOURCE_SHAPE_ID_LABEL_KEYS = {
  "google.gemini.rest.v1": "source_shape_id.google.gemini.rest.v1",
  "google.genai.python.v1": "source_shape_id.google.genai.python.v1",
  "openai.responses.python.v1": "source_shape_id.openai.responses.python.v1",
  "custom": "source_shape_id.custom",
} as const satisfies Record<SourceShapeIdKnown, string>;


// --- source_shape_label -----------------------------------------------------
//
// free_text — Not vocabulary. Recorded here so that "is this a value set?" is
// answered once, in data, rather than re-litigated by whoever next wants to
// add an enum to it.
//
// The name a tenant gives a response shape UBB does not recognise — their own
// wrapper around a supplier's client. Prose a human typed, and deliberately
// unvalidated: UBB generates from the declared path and performs no shape
// checking at all in this case, so there is nothing to check the name against
// and nothing for UBB to enumerate. Declaring a wrapper of one's own is a
// supported case rather than a blocked one (#193 §C7).
//
// Declared in concepts/economics.yaml.
//
// No constants: this kind declares no values by construction. The section is
// here so that fact is visible, rather than looking like a concept the
// generator lost.


// --- spend_pool_enforce_mode ------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// Whether a customer spend pool only announces a crossing or also stops work.
// A blocking pool enforces identically for `prepaid` and `postpaid` — mode
// decides who invoices, not whether the bound bites (#150 §7.1).
//
// Declared in concepts/spend-controls.yaml.

export const SPEND_POOL_ENFORCE_MODE_VALUES = [
  "alert_only",
  "blocking",
] as const;

export type SpendPoolEnforceMode = (typeof SPEND_POOL_ENFORCE_MODE_VALUES)[number];

export const SPEND_POOL_ENFORCE_MODE_LABEL_KEYS = {
  "alert_only": "spend_pool_enforce_mode.alert_only",
  "blocking": "spend_pool_enforce_mode.blocking",
} as const satisfies Record<SpendPoolEnforceMode, string>;


// --- stop_behavior ----------------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// What the generated integration wrapper does when UBB signals a spend stop.
// The default raises, and the signal derives from `BaseException` so a
// tenant's own broad handler cannot swallow it; `return` is available for
// callers who deliberately want to inspect the signal in line, and the
// generated code says which one it selected (#179 §1).
//
// Declared in concepts/tasks.yaml.

export const STOP_BEHAVIOR_VALUES = [
  "raise",
  "return",
] as const;

export type StopBehavior = (typeof STOP_BEHAVIOR_VALUES)[number];

export const STOP_BEHAVIOR_LABEL_KEYS = {
  "raise": "stop_behavior.raise",
  "return": "stop_behavior.return",
} as const satisfies Record<StopBehavior, string>;


// --- task_outcome -----------------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// What the tenant declares when it closes a Task, and the only thing that
// decides whether a Charge fires. It is a separate concept from the resulting
// status because the caller declares an outcome and UBB records a state: a
// Task UBB already stopped does not become `delivered` because a worker said
// so late.
//
// Declared in concepts/tasks.yaml.

export const TASK_OUTCOME_VALUES = [
  "delivered",
  "failed",
  "cancelled",
] as const;

export type TaskOutcome = (typeof TASK_OUTCOME_VALUES)[number];

export const TASK_OUTCOME_LABEL_KEYS = {
  "delivered": "task_outcome.delivered",
  "failed": "task_outcome.failed",
  "cancelled": "task_outcome.cancelled",
} as const satisfies Record<TaskOutcome, string>;


// --- task_status ------------------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// The durable state a Task or Subtask is in. `active` is the only non-terminal
// one. The three the tenant declares are reachable only by an explicit close;
// the two UBB writes are reachable only by UBB — `killed` means UBB stopped it
// on a spend signal and nothing else, and `expired` means nobody ever told UBB
// how it ended.
//
// Declared in concepts/tasks.yaml.

export const TASK_STATUS_VALUES = [
  "active",
  "completed",
  "failed",
  "cancelled",
  "killed",
  "expired",
] as const;

export type TaskStatus = (typeof TASK_STATUS_VALUES)[number];

export const TASK_STATUS_LABEL_KEYS = {
  "active": "task_status.active",
  "completed": "task_status.completed",
  "failed": "task_status.failed",
  "cancelled": "task_status.cancelled",
  "killed": "task_status.killed",
  "expired": "task_status.expired",
} as const satisfies Record<TaskStatus, string>;


// --- task_type_key ----------------------------------------------------------
//
// tenant_defined — The tenant owns the values. UBB defines the field and its
// validation contract and never enumerates the set — map #137 constraint 5 as
// a schema rule, so the registry cannot become the vendor catalogue that
// constraint forbids UBB to ship.
//
// The key a tenant gives one of its own declared Task kinds. UBB owns the
// entity and its declaration rules and never enumerates the keys — map #137
// constraint 5, which is why the registry cannot become a catalogue of what
// the tenant sells.
//
// Declared in concepts/tasks.yaml.
//
// No constants: this kind declares no values by construction. The section is
// here so that fact is visible, rather than looking like a concept the
// generator lost.


// --- task_type_kind ---------------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// Which level a declared Task kind may be used at. It survives the collapse of
// the two type columns into one because it is what lets a declaration be
// refused at declaration time rather than at use — a kind meant for contained
// work cannot be declared with a whole-Task pricing regime.
//
// Declared in concepts/tasks.yaml.

export const TASK_TYPE_KIND_VALUES = [
  "task",
  "subtask",
] as const;

export type TaskTypeKind = (typeof TASK_TYPE_KIND_VALUES)[number];

export const TASK_TYPE_KIND_LABEL_KEYS = {
  "task": "task_type_kind.task",
  "subtask": "task_type_kind.subtask",
} as const satisfies Record<TaskTypeKind, string>;


// --- tenant_posture ---------------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// Whether UBB creates this tenant's customer charges at all. DERIVED from
// `customer_billing_mode` and never stored (ADR-0006 §4) — a second writable
// copy could disagree with the first, and the wrong one is always the one
// nobody is looking at. It is served read-only so callers need not reconstruct
// the mapping.
//
// Declared in concepts/economics.yaml.

export const TENANT_POSTURE_VALUES = [
  "metering_only",
  "full_billing",
] as const;

export type TenantPosture = (typeof TENANT_POSTURE_VALUES)[number];

export const TENANT_POSTURE_LABEL_KEYS = {
  "metering_only": "tenant_posture.metering_only",
  "full_billing": "tenant_posture.full_billing",
} as const satisfies Record<TenantPosture, string>;


// --- tenant_product ---------------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// The products a tenant has enabled. Three, not four: the second recording
// lane was deleted along with the flag that switched it on, because there is
// one recording core and a tenant should not be choosing between two of them
// (#149 §6). Subscription lifecycle gates on `billing` rather than on a flag
// of its own.
//
// Declared in concepts/economics.yaml.

export const TENANT_PRODUCT_VALUES = [
  "metering",
  "billing",
  "referrals",
] as const;

export type TenantProduct = (typeof TENANT_PRODUCT_VALUES)[number];

export const TENANT_PRODUCT_LABEL_KEYS = {
  "metering": "tenant_product.metering",
  "billing": "tenant_product.billing",
  "referrals": "tenant_product.referrals",
} as const satisfies Record<TenantProduct, string>;


// --- trigger_source ---------------------------------------------------------
//
// open — UBB records the values it knows; consumers accept future and external
// ones. Checking is asymmetric — a registry-known value missing from a
// UBB-owned consumer is a defect, a runtime value the registry has never seen
// is legal.
//
// The mechanism that applied a transition — which is a different question from
// the business cause, and both travel as structured fields so a webhook never
// has to carry either in its name (ADR-0006 §5). Open because the set grows
// whenever UBB adds an enforcement path, and a consumer must accept one it has
// not seen rather than reject the event carrying it.
//
// Declared in concepts/tasks.yaml.

export const TRIGGER_SOURCE_KNOWN_VALUES = [
  "usage_ingest",
  "enforcement_patrol",
  "parent_cascade",
  "pool_crossing",
  "stale_reaper",
] as const;

export type TriggerSourceKnown = (typeof TRIGGER_SOURCE_KNOWN_VALUES)[number];

// An `open` concept: a value UBB has never seen is legal (ADR-0003), so the
// type admits any string. The intersection is what stops TypeScript collapsing
// the union to `string` and losing the known values a reader is offered.
export type TriggerSource = TriggerSourceKnown | (string & {});

export const TRIGGER_SOURCE_LABEL_KEYS = {
  "usage_ingest": "trigger_source.usage_ingest",
  "enforcement_patrol": "trigger_source.enforcement_patrol",
  "parent_cascade": "trigger_source.parent_cascade",
  "pool_crossing": "trigger_source.pool_crossing",
  "stale_reaper": "trigger_source.stale_reaper",
} as const satisfies Record<TriggerSourceKnown, string>;


// --- unit -------------------------------------------------------------------
//
// open — UBB records the values it knows; consumers accept future and external
// ones. Checking is asymmetric — a registry-known value missing from a
// UBB-owned consumer is a defect, a runtime value the registry has never seen
// is legal.
//
// What one declared quantity is counted in — the noun beside the number, so an
// amount of 1,500 means something without the reader knowing which supplier
// produced it. UBB owns the field and records the spellings it has met; it
// never bounds the set, because the quantity a tenant sells is the tenant's to
// choose.
//
// Declared in concepts/economics.yaml.

export const UNIT_KNOWN_VALUES = [
  "token",
  "search",
  "call",
  "second",
  "byte",
] as const;

export type UnitKnown = (typeof UNIT_KNOWN_VALUES)[number];

// An `open` concept: a value UBB has never seen is legal (ADR-0003), so the
// type admits any string. The intersection is what stops TypeScript collapsing
// the union to `string` and losing the known values a reader is offered.
export type Unit = UnitKnown | (string & {});

export const UNIT_LABEL_KEYS = {
  "token": "unit.token",
  "search": "unit.search",
  "call": "unit.call",
  "second": "unit.second",
  "byte": "unit.byte",
} as const satisfies Record<UnitKnown, string>;


// --- usage_event_kind -------------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// The nature of one usage row, and NOTHING else — not the tenant, not how COGS
// was derived, not how customer price was calculated (ADR-0006 §3.8).
// `metered_usage` is a real event for work that occurred; `task_charge` is the
// synthetic posting projected from the canonical Charge when a Task sold for
// one agreed price is delivered.
//
// Declared in concepts/economics.yaml.

export const USAGE_EVENT_KIND_VALUES = [
  "metered_usage",
  "task_charge",
] as const;

export type UsageEventKind = (typeof USAGE_EVENT_KIND_VALUES)[number];

export const USAGE_EVENT_KIND_LABEL_KEYS = {
  "metered_usage": "usage_event_kind.metered_usage",
  "task_charge": "usage_event_kind.task_charge",
} as const satisfies Record<UsageEventKind, string>;


// --- webhook_event_type -----------------------------------------------------
//
// closed — UBB owns the whole value set — exactly these values, no more.
//
// Every event UBB publishes, named `<domain owner>.<past-tense state
// entered>`. A resource lifecycle transition is owned by the resource; a
// control's own state change is owned by the declared control family. Cause
// and mechanism never appear in the name — they travel as structured payload
// fields, so a subscriber classifies by subscribing rather than by parsing.
// Closed because UBB authors every one of them and a subscriber may only
// subscribe to a name UBB publishes.
//
// Declared in concepts/webhooks.yaml.

export const WEBHOOK_EVENT_TYPE_VALUES = [
  "usage.recorded",
  "usage.refunded",
  "refund.requested",
  "task.killed",
  "task.expired",
  "subtask.killed",
  "subtask.expired",
  "customer_spend_pool.threshold_reached",
  "wallet_policy.soft_floor_crossed",
  "wallet_policy.soft_floor_cleared",
  "customer.stopped",
  "customer.stop_cleared",
  "customer.suspended",
  "customer.deleted",
  "customer.unprofitable",
  "provider.cost_spike",
  "wallet.balance_low",
  "wallet.balance_critical",
  "wallet.balance_overage",
  "top_up.requested",
  "auto_top_up.requires_action",
  "withdrawal.requested",
  "credit_grant.expiring",
  "credit_grant.expired",
  "usage_invoice.pushed",
  "usage_invoice.push_failed_permanent",
  "referral.created",
  "referral.expired",
  "referral.reward_earned",
  "referral.payout_due",
  "invitation.created",
  "invitation.revoked",
  "member.activated",
  "sandbox.reset_completed",
  "tenant.api_key_created",
  "tenant.api_key_rotated",
  "tenant.api_key_revoked",
] as const;

export type WebhookEventType = (typeof WEBHOOK_EVENT_TYPE_VALUES)[number];

export const WEBHOOK_EVENT_TYPE_LABEL_KEYS = {
  "usage.recorded": "webhook_event_type.usage.recorded",
  "usage.refunded": "webhook_event_type.usage.refunded",
  "refund.requested": "webhook_event_type.refund.requested",
  "task.killed": "webhook_event_type.task.killed",
  "task.expired": "webhook_event_type.task.expired",
  "subtask.killed": "webhook_event_type.subtask.killed",
  "subtask.expired": "webhook_event_type.subtask.expired",
  "customer_spend_pool.threshold_reached": "webhook_event_type.customer_spend_pool.threshold_reached",
  "wallet_policy.soft_floor_crossed": "webhook_event_type.wallet_policy.soft_floor_crossed",
  "wallet_policy.soft_floor_cleared": "webhook_event_type.wallet_policy.soft_floor_cleared",
  "customer.stopped": "webhook_event_type.customer.stopped",
  "customer.stop_cleared": "webhook_event_type.customer.stop_cleared",
  "customer.suspended": "webhook_event_type.customer.suspended",
  "customer.deleted": "webhook_event_type.customer.deleted",
  "customer.unprofitable": "webhook_event_type.customer.unprofitable",
  "provider.cost_spike": "webhook_event_type.provider.cost_spike",
  "wallet.balance_low": "webhook_event_type.wallet.balance_low",
  "wallet.balance_critical": "webhook_event_type.wallet.balance_critical",
  "wallet.balance_overage": "webhook_event_type.wallet.balance_overage",
  "top_up.requested": "webhook_event_type.top_up.requested",
  "auto_top_up.requires_action": "webhook_event_type.auto_top_up.requires_action",
  "withdrawal.requested": "webhook_event_type.withdrawal.requested",
  "credit_grant.expiring": "webhook_event_type.credit_grant.expiring",
  "credit_grant.expired": "webhook_event_type.credit_grant.expired",
  "usage_invoice.pushed": "webhook_event_type.usage_invoice.pushed",
  "usage_invoice.push_failed_permanent": "webhook_event_type.usage_invoice.push_failed_permanent",
  "referral.created": "webhook_event_type.referral.created",
  "referral.expired": "webhook_event_type.referral.expired",
  "referral.reward_earned": "webhook_event_type.referral.reward_earned",
  "referral.payout_due": "webhook_event_type.referral.payout_due",
  "invitation.created": "webhook_event_type.invitation.created",
  "invitation.revoked": "webhook_event_type.invitation.revoked",
  "member.activated": "webhook_event_type.member.activated",
  "sandbox.reset_completed": "webhook_event_type.sandbox.reset_completed",
  "tenant.api_key_created": "webhook_event_type.tenant.api_key_created",
  "tenant.api_key_rotated": "webhook_event_type.tenant.api_key_rotated",
  "tenant.api_key_revoked": "webhook_event_type.tenant.api_key_revoked",
} as const satisfies Record<WebhookEventType, string>;
