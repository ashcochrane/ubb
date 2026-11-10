PRE-ASH BILLING READINESS - STAGE D RE-PROOF - NOT PRODUCTION OR RAIL-ACTIVATION EVIDENCE

# 02 - Technical system map at `a6738e78e96ab10eabd45dc10fafdc842b7de519`

Every citation is `path :: Symbol (line)` resolved against the anchor's tree on 2026-11-09 by
`R10-BILLING-STAGE-D-EVIDENCE/probes/resolve_symbols.py` (a regex per symbol; line numbers are the match lines).
Paths are relative to the repository root; `ubb-platform/` is the Django project. Labels: **CODE VERIFIED** (read),
**TEST VERIFIED** (the Stage D union run), **LOCALLY EXECUTED** (the Stage D probes), **LOCAL FAKE STRIPE KEY** (in
process under the sentinel, transport blocked, real objects). `R10-ASH-HANDOFF/02` (anchor `1bf0c0ca`) remains the
detailed reference for the kernel sections it covers (runtime, ingestion, Event Types, Tasks, pricing, postings,
economics, spend controls, auth, webhooks, configuration, release tooling); this map restates them briefly and adds
what Stage A-C5 built.

## 1. The shape (unchanged)

- Monorepo: `ubb-platform/` (Django 6.0.6, django-ninja `/api/v1`, Celery, PostgreSQL 16, Redis 7), `ubb-sdk/` (SDK
  5.0.0), `apps/ui` (the React console), `apps/codegen` (the Code Builder renderer), `domain-vocabulary/` (the registry),
  `openapi/` (the committed contract and gates), `tools/` (gates, forbidden terms, vocabulary, SDK coverage),
  `tests/contracts` and `tests/code_builder_execution`.
- Four products on a kernel, four channels: `docs/architecture/2026-06-12-adr-001-product-boundaries.md`;
  the AST walker `ubb-platform/apps/platform/tests/test_product_boundaries.py :: test_cross_product_imports_only_via_sanctioned_channels (256)`
  (11 passed, `00-static.txt`). Glossaries: `CONTEXT-MAP.md` → `ubb-platform/apps/<product>/CONTEXT.md`.
- Billing modes and products on the tenant: `ubb-platform/apps/platform/tenants/models.py :: class Tenant (311)`,
  `billing_mode (325)`, `products (324)`, `stripe_connected_account_id (313)`, `charges_enabled (330)`.
- The payment rail: `tenants/models.py :: class PaymentRailActivation (214)`, `the_rail_is_open_in (149)`,
  `refuse_a_rail_operation_while_it_is_closed (193)`; the door tests
  `api/v1/tests/test_a_money_mode_needs_its_payment_rail.py` (TEST VERIFIED).
- Customers and topology: `apps/platform/customers/models.py :: class Customer (34)`, `stripe_customer_id (43)`,
  `suspension_reason (85)`, `resolve_billing_owner (97)` (a pooled seat → its business; every other customer, an
  allocated seat included, is its own billing owner), `soft_delete (105)`; the seat-roster hooks
  `customers/hooks.py :: notify_seat_roster_changed (28)`, `notify_if_a_seat (34)`; the one creation path
  `api/v1/platform_endpoints.py :: create_customer (72)` calling the hook for a seat `(109)`.
- Kernel reads for the products: `apps/platform/queries.py :: get_tenant_stripe_account (25)`,
  `get_customer_stripe_id (35)`, `get_stripe_customer_holders (45)` (answers EVERY holder of a Stripe customer id in a
  connected-account/livemode namespace; never chooses one - C4).
- The outbox: `apps/platform/events/outbox.py :: write_event (43)`; `events/tasks.py :: process_single_event (54)`,
  `sweep_outbox (92)`, `cleanup_outbox (143)`; handler checkpoints keep re-dispatch idempotent (`09-convergence` §4).
- Event schemas the billing paths emit: `events/schemas.py :: WalletBalanceLow (458)`, `TopUpRequested (477)`,
  `CustomerSuspended (492)`, `CustomerReactivated (503)` (C2: exactly once on the real suspended → active transition;
  `reason_code` = the reason being left), `UsageInvoicePushed (577)`, `CustomerStopped (889)`, `CustomerStopCleared (947)`.
- The audit ledger: `apps/platform/audit/ledger.py :: record (23)` (called inside the mutation's own transaction),
  `audit/actors.py :: operator_actor (70)`, `audit/models.py :: AuditRecord (21)`.
- Plans (a kernel concept): `apps/platform/plans/models.py :: Plan (8)`, `has_stripe_axes (123)`,
  `CustomerPlanAssignment (133)`; `plans/services.py :: PlanService.assign (69)`.

## 2. Metering (the economic truth; unchanged by Stage A-C5 except the owner pin)

`apps/metering/usage/models.py :: Posting (51)` with `billing_owner_id (371)` pinned at record time;
`Refund (1014)`; `apps/metering/queries.py :: billing_owner_recorded_anything (436)`,
`get_customer_ids_with_postings (575)`. Economics is read from postings only - every Stage D probe proved revenue and
cost unmoved by credits, grants, refunds, claw-backs, pushes and AR events (`03`, `04` step 13/15).

## 3. Billing - the wallet (prepaid)

- The wallet door: `apps/billing/locking.py :: the_currency_a_top_up_will_credit (42)`,
  `refuse_a_wallet_operation_without_a_wallet (58)` (Stage A; since C5 also asked by the six read-only routes - F-12),
  `lock_for_billing (80)` (the wallet is born here), `lock_top_up_attempt (135)`.
- Models: `apps/billing/wallets/models.py :: Wallet (56)`, `WalletTransaction (104)` (type, amount, `reference_id`,
  per-wallet unique `idempotency_key`), `CustomerBillingProfile (158)` (floors), `CreditGrant (202)`,
  `WalletReservation (327)`.
- Operations (one `_execute` with the replay probe): `apps/billing/wallets/operations.py :: IDEMPOTENCY_CONFLICT (87)`,
  `REFUND_TOTAL_BELOW_APPLIED (94)`, `_execute (152)`, `_replayed (227)`, `refund_usage (333)` (F-14: the refund
  transaction id on the first call and every replay; a non-refund key → `idempotency_conflict` → 409 `conflict`),
  the drawdown `(527)`, `credit_top_up (685)`, `claw_back_dispute (718)`, `stripe_refund_applied_micros_for (748)`,
  `claw_back_stripe_refund (757)` (C1b Q15: the increment of the cumulative, keyed `stripe_refund:{refund.id}` or
  `stripe_refund:{charge}:{amount_refunded}`; a decrease is refused with one structured ERROR).
- Floors, stops and the one reactivation site: `apps/billing/gating/services/live_counter.py :: LiveCounter (279)`,
  `_standing_money_cause (696)` (an open stop line under `enforcing`, else a durable wallet past its floor for the
  owner that is its own billing owner), `_maybe_unsuspend (736)` (THE site that moves suspended → active; asks the
  payment-failure rule first, then the money cause when `check_money_causes`; emits `customer.reactivated` once),
  `recover_from_durable_balance (846)` (F-1: the `off` lanes), `MANUAL_HOLD_REASON (865)` (`""`),
  `clear_manual_hold (868)`, `clear_payment_failed_suspension (883)` (F-6 + item 43), `resume (911)`, `read (966)`;
  the ledger `gating/models.py :: StopSignalState (116)`; `gating/services/stop_signal_service.py ::
  announced_balance (173)`, `open_stop_lines (373)`; the hourly passes `gating/tasks.py ::
  reconcile_customer_spend_pool_counters (11)`, `_per_owner_reconcile (42)`, `reconcile_live_ledgers (129)`;
  the start gate `gating/services/risk_service.py :: RiskService (63)`, `check (187)` (null balances off the lane).
  Read contracts: `apps/billing/queries.py :: get_customer_min_balance (51)`, `a_payment_failure_remains_for (65)`,
  `get_customer_balance (113)`.
- The manual hold (C4 item 41, C5 item 42): `apps/billing/gating/services/manual_hold.py :: HANDED_OVER (116)`,
  `_audit (157)`, `place_manual_hold (176)`, `release_manual_hold (213)` (ONE transaction, the Customer row lock
  before the reactivation site); the command
  `apps/billing/gating/management/commands/set_customer_manual_hold.py :: Command (28)`. Proved in `03-prepaid-*`
  step 9b (HELD / no-op / RELEASED / HANDED_OVER with the audit rows).
- Wallet jobs: `apps/billing/wallets/tasks.py :: release_reservations_left_open_on_terminal_work (18)`,
  `reconcile_wallet_balances (34)` (detect-only), `reconcile_usage_drawdowns (131)`, `expire_credit_grants (187)`.
- Top-ups: `apps/billing/topups/models.py :: AutoTopUpConfig (30)`, `TopUpAttempt (45)`, `stripe_charge_id (73)`;
  `topups/tasks.py :: expire_stale_topup_attempts (11)` (manual AND widget attempts since C1b);
  the shared door `api/v1/topups.py :: _mark_failed (61)`, `start_top_up (79)` (refuses BEFORE it writes - F-11/O-6;
  the typed 202 with no connector - F-5); the connector `apps/billing/connectors/stripe/stripe_api.py ::
  _charges_ready (28)`, `refuse_a_checkout_that_cannot_proceed (40)`, `create_checkout_session (96)`;
  the auto top-up charge `connectors/stripe/tasks.py :: charge_auto_top_up_task (31)` and the hourly
  `reconcile_topups_with_stripe (169)` (through the wrapper since C1a).

## 4. Billing - postpaid usage invoices and the platform fee

- Models: `apps/billing/invoicing/models.py :: CustomerUsageInvoice (102)`, `carried_below_minor_unit (164)`,
  `historical_billing_owner_id (173)`, `UsageInvoiceLineItem (186)`, `PostpaidResidualLedger (206)`,
  `PostpaidUsageConfig (229)`; the rules migration `invoicing/migrations/0002_skip_reason_below_minor_unit.py (13)`.
- The push: `apps/billing/invoicing/services/postpaid_service.py :: _a_raise_counts_an_attempt (63)` (F-8),
  `aggregate_lines (110)`, `_park_failed_permanent (209)`, `push_customer_period (250)` (Stage 1 the committed claim;
  Stage 2 supersede/caps/snapshot/aggregation/skips/carry; Phase 2 Stripe through the wrapper; Phase 3 record -
  `below_minor_unit (453)` instead of `pushed` when nothing reached a minor unit, F-9), `_push_to_stripe (498)`,
  `_resolve_consolidation_target (690)`, `_push_consolidated (728)`; the caps `config/settings.py ::
  UBB_POSTPAID_PUSH_MAX_ATTEMPTS (313)`, `UBB_POSTPAID_PUSH_MAX_AGE_HOURS (314)`.
- The jobs: `apps/billing/invoicing/tasks.py :: _prior_month (83)`, `close_postpaid_usage_periods (94)` (targets
  `apps/billing/accounts.py :: billing_owner_ids (9)` - F-7), `reconcile_postpaid_usage (135)`,
  `_recover_skipped_usage_invoices (167)`, `reconcile_invoice_payment_status (197)` (the AR poller),
  `_restore_payment_failed_owners (278)` (the hourly payment_failed backstop; selects by the current reason, so a
  customer handed over to `hard_floor` is never selected - `09-convergence` §7); the operator command
  `invoicing/management/commands/repush_usage_invoice.py :: Command (13)`.
- AR routing and the frozen owner: `apps/billing/connectors/stripe/invoice_routing.py :: livemode_filter (43)`,
  `reject_for_mode (53)`, `AR_ALLOWED (75)`, `ar_transition_allowed (87)`, `SETTLED_PAYMENT_STATUSES (125)`,
  `settle_failure_stamp (129)`; `api/v1/webhooks.py :: _reconcile_customer_invoice (117)` (a subscription invoice
  before its mirror raises → retryable, item 36; the `SubscriptionInvoice.billing_owner` resolved ONCE at creation),
  `_apply_usage_invoice_status (234)`, `handle_invoice_paid (280)`; the failure side
  `connectors/stripe/webhooks.py :: _suspend_with_cause (206)`, `_mark_invoice_payment_failed (226)`,
  `handle_invoice_payment_failed (279)`.
- The platform fee: `apps/billing/tenant_billing/models.py :: TenantBillingPeriod (46)`, `TenantInvoice (103)`,
  `PlatformFeeCarry (164)`, `is_a_stripe_customer_id (214)`, `BillingTenantConfig (223)`;
  `tenant_billing/services.py :: TenantBillingService (21)`, `get_or_create_current_period (23)`,
  `accumulate_usage (55)`, `close_period (278)`, `reconcile_period (392)`; `tenant_billing/tasks.py ::
  reconcile_tenant_billing_periods (88)`, `generate_tenant_platform_invoices (116)`, `_platform_customer_problem (196)`,
  `_create_tenant_invoice (217)`; the Stripe side `apps/billing/stripe/services/stripe_service.py ::
  create_tenant_platform_invoice (219)` (`platform-invoice-{period}`, `platform-item-…`, `platform-finalize-…`); the
  operator command `tenant_billing/management/commands/set_platform_billing_customer.py :: Command (44)`, `_verify (108)`
  (F-10, audited `tenant.platform_billing_customer_set`).
- The public shape (F-15): `api/v1/schemas.py :: UsageInvoiceBase (2562)`, `usage_invoice_base_out (2594)`,
  `_OperatorUsageInvoice (2621)` (adds only `push_attempts`, `last_attempt_error`), `UsageInvoiceOut (2637)`,
  `TenantUsageInvoiceOut (2653)`, and the `/me` schema built on the base (`api/v1/me_endpoints.py ::
  list_usage_invoices (336)`).

## 5. The Stripe boundary (connector kit)

- The wrapper: `apps/billing/stripe/services/stripe_service.py :: field (34)` (attribute read on a real
  StripeObject, tolerant of a dict for its own tests), `validate_amount_micros (66)`, `micros_to_cents (72)`,
  `api_key_for_tenant (101)`, `stripe_call (119)` (refuses an empty key with `StripeNotConfigured` before any request;
  injects `api_key` and `idempotency_key`; retries `APIConnectionError`/`RateLimitError`/`APIError` with backoff →
  `StripeTransientError`; `CardError` → `StripePaymentError` carrying `decline_code` and `payment_intent_id` (O-1);
  the rest → `StripeFatalError`). Exceptions: `core/exceptions.py :: StripeTransientError (34)`,
  `StripePaymentError (39)`, `StripeFatalError (53)`, `StripeNotConfigured (66)` (→ 503 `service_unavailable`),
  `PaymentNotAvailable (79)` (→ 409 `payment_not_available`), `NoWalletSubjectError (155)` (→ 403
  `feature_not_enabled`); the mapping `api/v1/problems.py :: (174, 201, 216, 226, 241)`.
- The CI guards: `apps/billing/stripe/tests/test_stripe_call_api_key_ci.py` - the raw-SDK AST walker (every
  `stripe.<Resource>.<verb>(` off the allowlist, function-local imports included, a planted negative control) and the
  C1a `.get` ratchet (TEST VERIFIED; also run by `05-stripe-levels`). The formerly raw sites, now through the wrapper
  (F-2): `connectors/stripe/webhooks.py :: handle_checkout_completed (35)` (`PaymentIntent.retrieve`),
  `connectors/stripe/tasks.py :: reconcile_topups_with_stripe (169)`, `apps/subscriptions/stripe/sync.py ::
  sync_subscriptions (24)`, `connectors/stripe/connect.py :: build_authorize_url (46)`, `complete_oauth (58)`,
  `api/v1/connect_endpoints.py :: connect_status (40)`.
- The receivers (C1b): `apps/billing/stripe/models.py :: WEBHOOK_RECEIVERS (24)`, `StripeWebhookEvent (32)`, the pair
  unique `uq_stripe_webhook_event_receiver_event (61)`; migration `stripe/migrations/0002_stripewebhookevent_receiver.py (14)`;
  the core `apps/billing/stripe/receiver.py :: PROCESSING_TTL_MINUTES (66)`, `register_receiver (83)`,
  `registered_receiver (96)`, `receive_stripe_event (106)` (verify with THIS receiver's secret, the mode gate),
  `process_stripe_event (138)` (dedup + CAS, dispatch to the receiver's own map, classification: `ObjectDoesNotExist`
  and unexpected errors → retryable 500; `StripeFatalError` and the billing receiver's `NoWalletSubjectError` →
  recorded, 200). The billing receiver `api/v1/webhooks.py :: stripe_webhook (51)`, `stripe_webhook_test (74)`,
  `_stripe_webhook (93)`, `WEBHOOK_HANDLERS (380)`, `register_receiver (403)` (`config/urls.py (17-20)`:
  `/api/v1/webhooks/stripe[/test]`); the subscriptions receiver `apps/subscriptions/api/endpoints.py ::
  SUBSCRIPTIONS_WEBHOOK_HANDLERS (149)`, `subscriptions_stripe_webhook (158)`, `subscriptions_stripe_webhook_test (183)`,
  `register_receiver (213)` (`/api/v1/subscriptions/webhooks/stripe[/test]`; its own
  `config/settings.py :: STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET (378)`, `STRIPE_SUBSCRIPTIONS_TEST_WEBHOOK_SECRET (379)`;
  blank → 400, no fallback). Handlers on the billing side: `connectors/stripe/webhooks.py :: handle_checkout_completed (35)`,
  `handle_charge_dispute_created (312)`, `handle_charge_dispute_closed (341)`, `_attempt_for_charge (429)`,
  `handle_charge_refunded (454)`, `REFUND_REVERSAL_STATUSES (545)`, `handle_charge_refund_updated (548)` (Q19
  alert-only), `handle_payment_intent_succeeded (608)`, `handle_payment_intent_payment_failed (628)`.
- The operator recovery: `apps/billing/stripe/management/commands/reprocess_webhook.py :: Command (62)`, `_retrieve (176)`
  (through `stripe_call(stripe.Event.retrieve)` under the `--tenant`'s key and connected account), `_agree (193)`
  (id, type, account, livemode must agree) → `process_stripe_event` on the SAME row (item 36). Cleanup
  `apps/billing/stripe/tasks.py :: cleanup_webhook_events (11)`. Receipts: `connectors/stripe/receipts.py ::
  create_topup_receipt (20)`.

## 6. Subscriptions

- Models: `apps/subscriptions/models.py :: StripeSubscription (30)` (the mirror; `customer`/`tenant` = its binding),
  `SubscriptionInvoice (95)`, `billing_owner (127)` (NOT NULL, frozen by a DB trigger; migration
  `subscriptions/migrations/0002_subscriptioninvoice_billing_owner.py (29)`), `CustomerSubscriptionItem (188)`.
- Orchestration: `apps/subscriptions/orchestration/service.py :: OrchestrationError (50)`,
  `ensure_plan_provisioned (117)`, `subscribe (185)` (every refusal before any write; `on_bound` runs in the mirror's
  transaction - A-1), `set_seats (270)` (`seat-qty-{si}-{change_event_id}`), `cancel (318)`, `pause (363)`,
  `resume (389)`, `update_plan_prices (421)`, `_ensure_stripe_customer (555)`, `_bind_explicit_owner (578)`
  (bind once; a different binding fails closed), `_persist_mirror (612)` (reads the REAL `stripe.Subscription`);
  the route `apps/subscriptions/api/endpoints.py :: _lifecycle_call (227)`, `subscribe_customer (270)`
  (StripeTransientError → 503; StripePaymentError/StripeFatalError/OrchestrationError → 422; assignment + both audit
  rows inside `on_bound`).
- Seats (A-2, item 40): `apps/subscriptions/orchestration/seats.py :: seat_count (52)`,
  `businesses_with_an_active_seat_subscription (85)`, `_push (97)` (never raises; logs `seat.qty_push_failed` /
  `seat.qty_reconcile_failed` on `ubb.billing`), `sync_seat_quantity_on_commit (131)` (the roster listener; one push
  per transaction), `reconcile_change_id (205)` (`reconcile-{si}-{episode}-{count}`, the episode = the seat item's
  `updated_at`), `reconcile_seat_quantity (238)`; the hourly `apps/subscriptions/tasks.py ::
  reconcile_subscription_seat_quantities (292)` (`config/settings.py (265)`, at :47 after the mirror sync at :35 `(259)`).
- Identity (items 30/33-38): `apps/subscriptions/stripe/binding.py :: AmbiguousMirrorOwner (54)`,
  `resolve_new_mirror_owner (80)` (exactly one holder binds; zero UNRESOLVED; several AMBIGUOUS → the ERROR
  `subscription.mirror_ambiguous`), `log_unbound (96)`, `mutable_facts (117)`, `refresh_mutable_facts (136)`,
  `create_bound_mirror (146)`; the sync `stripe/sync.py :: sync_subscriptions (24)`, `_sync_one (96)` (an existing
  mirror refreshed, never rebound; another tenant's mirror or candidate skipped); the webhooks
  `apps/subscriptions/api/webhooks.py :: handle_subscription_created (18)` (an existing mirror FIRST - item 37),
  `handle_subscription_updated (66)`, `handle_subscription_deleted (101)`; the object reads
  `stripe/items.py :: mirrored_amounts (49)`, `paid_amounts (80)`, `_product_name (108)`.
- The port billing consumes: `apps/subscriptions/ports.py :: mark_invoice_payment_failed_for_subscription (54)`,
  `has_unsettled_subscription_payment_failure (101)`, `settle_subscription_invoice_payment_failure (116)`,
  `repair_subscription_invoice (142)`. Other jobs: `tasks.py :: reconcile_cost_accumulators (119)`,
  `sync_tenant_subscriptions_task (256)`, `reconcile_subscription_mirrors (268)`.

## 7. Referrals (A-3)

`apps/referrals/api/schemas.py :: one_reward_figure_by_type (51)`, `ProgramCreateRequest (66)`;
`apps/referrals/api/endpoints.py :: create_program (90)`, `update_program (141)` (the stored old-type figure cleared on
a type change; the resulting row held to the one rule, refusing a caller-supplied figure of the wrong unit by name);
`apps/referrals/rewards/services.py :: share_of (22)` (÷ 10,000 exactly, half-up), `flat_fee_micros (33)`,
`calculate_reward (40)`; `rewards/reconciliation.py :: reconcile_referral (21)` (the flat fee on exactly one ledger
row, `flat_fee_paid`), `reconcile_all_referrals (142)`; the real-time handler `apps/referrals/handlers.py (19, 66, 145)`;
`apps/referrals/tasks.py :: reconcile_all_referrals_task (14)` (the current month); the migration
`referrals/migrations/0002_reward_units_in_micros_and_basis_points.py (64)` (no `RunPython` - FINAL Reading 8).

## 8. The public API, the SDK and the Code Builder

- Routes named in this handoff: `api/v1/billing_endpoints.py :: get_balance (73)`, `debit (122)`, `credit (178)`
  (`customer_id: UUID` - `api/v1/schemas.py :: DebitRequest (1669)`, `CreditRequest (1697)`), `configure_auto_top_up (227)`
  (`ConfigureAutoTopUpRequest (1479)`), `create_top_up (268)` (`TopUpCheckoutResponse (1504)` | `TopUpAcceptedResponse (1512)`),
  `withdraw (283)`, `affordability (325)` (`AffordabilityResponse (138)`), `refund_usage (362)` (`RefundResponse (1551)`),
  `get_transactions (430)`, `create_grant (458)`, `list_grants (511)`, `void_grant (535)`; `api/v1/me_endpoints.py ::
  get_balance (210)`, `list_grants (260)`, `get_transactions (288)`, `create_top_up (313)`, `get_invoices (327)`,
  `list_usage_invoices (336)`, `get_my_economics (464)`, `list_subscription_invoices (504)`; plans
  `api/v1/plan_endpoints.py :: create_plan (97)`, `archive_plan (212)`, `assign_plan (238)`; Connect
  `api/v1/connect_endpoints.py :: connect_start (24)`, `connect_status (40)`, `connect_callback (63)`.
- The contract: `openapi/v1.json` (byte-identical to `ubb-platform/scripts/export_openapi.py`'s output; the
  `audit_action` enum carries the manual-hold actions `(498-499)`; `TopUpAcceptedResponse (11545)`;
  `reward_share_basis_points (7394…)`); the gates `openapi/contract_gate.py` (cumulative breaking gate against
  `api-v1-cutover`; `--baseline origin/main --emit` for authoring), `openapi/oasdiff-err-ignore.txt` /
  `oasdiff-warn-ignore.txt` (the 14 generated C5 entries: F-13's `customer_id` format `(69, 92-93)`, A-3's
  `reward_value`/`estimated_cost_percentage` removals `(74-97)`), `openapi/README.md`; the registry
  `domain-vocabulary/concepts/governance.yaml (40, 56-57)`, `webhooks.yaml (42, 47)`, `billing.yaml` (`below_minor_unit
  (146…)`, `usage_invoice_payment_status (229)`, `top_up_request_status (259)`); the generated constants
  `ubb-platform/core/vocabulary.py :: AUDIT_ACTION_TENANT_PLATFORM_BILLING_CUSTOMER_SET (200)`,
  `AUDIT_ACTION_CUSTOMER_MANUAL_HOLD_SET (201)`, `…_RELEASED (202)`, `REWARD_TYPE_FLAT_FEE (1824)`,
  `SKIP_REASON_BELOW_MINOR_UNIT (1875)`, `TOP_UP_REQUEST_STATUS_TOPUP_REQUESTED (2207)`,
  `USAGE_INVOICE_PAYMENT_STATUS_PAID (2356)`, `WEBHOOK_EVENT_TYPE_CUSTOMER_SUSPENDED (2462)`, `…_REACTIVATED (2463)`.
- SDK 5.0.0: `ubb-sdk/pyproject.toml :: version (14)`, `ubb/__init__.py :: __version__ (89)`;
  `ubb/billing.py :: debit (63)`, `credit (91)` (UUID), `refund (128)`, `get_balance (141)`, `create_top_up (173)`
  (the typed union), `configure_auto_top_up (200)` (all required), `get_usage_invoices (260)` (the page envelope);
  `ubb/client.py :: create_widget_token (126)`, `subscribe_customer (366)`, `set_seats (380)`, `update_tenant_config (469)`
  (the seven O-5 fields with the generated `UNSET`), `create_top_up (657)`, `configure_auto_top_up (671)`;
  `ubb/referrals.py :: create_program (50)` (explicit units), `update_program (91)`; `ubb-sdk/MIGRATION.md §27 (1289)`,
  `CHANGELOG.md "5.0.0" (7…)`; the generated core `ubb-sdk/codegen/generate_core.py`; the coverage manifest
  `tools/sdk_operations`. **Released 2026-11-09** (the owner's separate act): annotated tag `sdk-v5.0.0` (object `fbf765b7…`) on
  `b41b395f59d798cec83289d83d5ec71f83201c7f`; wheel `ubb_sdk-5.0.0-py3-none-any.whl`, SHA-256
  `56d28b90876beff35532e48df6a5fb8545f665f9c781b40d9febf0b418555948`, built by the tag's `ubb-sdk/release/build_wheel.py` (two builds,
  one hash) and verified in a clean venv; handed over in `R10-SDK-V5-RELEASE/`; not published to PyPI.
- The Code Builder: `api/v1/integration_blueprint.py :: SDK_MAJOR_VERSION (237)` (`python_sdk: 5`);
  `apps/codegen/src/catalogue.ts :: CATALOGUE_VERSION (37)` = 11, `sdkMajorVersion (137)` = 5; the fixtures
  `apps/codegen/fixtures/blueprints/*.json` carry `sdk_major_version 5` (shell `null`); the execution suite
  `tests/code_builder_execution` renders and runs the generated integrations in Docker (80 passed).
- The console: `apps/ui/src/hooks/use-tenant-config.ts :: useHoldsAWallet (185)` (wallet-only panels only where the
  mode keeps a wallet), `apps/ui/src/lib/usage-invoice.ts (16, 23…)`, `apps/ui/src/locales/en.json (36-37)`; the
  billing-page credit/debit forms take a labelled Platform Customer UUID (F-13).

## 9. The operator commands

| Command | Does | Cited |
|---|---|---|
| `manage.py set_customer_manual_hold --customer <uuid> --state held\|released --operator <id>` | the ONE manual-hold workflow; audited | §3 |
| `manage.py set_platform_billing_customer --tenant <id> --stripe-customer-id cus_… [--verify] [--operator <id>]` | UBB's platform-fee customer for the tenant; `--verify` through the wrapper, refused without a key; audited | §4 |
| `manage.py reprocess_webhook <event id> --receiver billing\|subscriptions --tenant <id>` | re-runs one failed retryable receiver row on its own record after retrieving the Event through the wrapper | §5 |
| `manage.py repush_usage_invoice <row id> [--rebill-void]` | pending again (same key family) / a new generation | §4 |
| `manage.py seed_dev_data` | development seeding only (refuses a money mode without the rail) | - |

## 10. The hourly / daily jobs (`config/settings.py :: CELERY_BEAT_SCHEDULE (166)`)

`expire-stale-topup-attempts (167)`, `reconcile-wallet-balances (171)`, `expire-credit-grants (175)`,
`generate-tenant-platform-invoices (191)`, `reconcile-topups-with-stripe (227)`, `reconcile-live-ledgers (255)`,
`reconcile-subscription-mirrors (259)`, `reconcile-subscription-seat-quantities (265)`, `close-postpaid-usage-periods (272)`,
`reconcile-postpaid-usage (279)`, `reconcile-usage-drawdowns (283)`, `reconcile-invoice-payment-status (297)`, plus the
outbox sweep/cleanup, the accumulator reconcile, the referrals daily task and the webhook cleanups. Every one was
driven by hand from a recoverable state in Stage D (`09-convergence`, `03`, `04`, `06`); `test_beat_schedule.py`
pins the schedule (TEST VERIFIED).

## 11. Authentication, configuration, the Clerk path

API keys (`ubb_live_`/`ubb_test_`, SHA-256 stored), widget tokens (`core/widget_auth.py :: create_widget_token (12)`,
verify `(23)`), Clerk member sign-in (`core/clerk_auth.py :: verify_member_token (68)`; RS256 via PEM or JWKS; the
structured warning `clerk.rs256_backend_unavailable (100)` and fail-closed when the backend is missing). The lock
`ubb-platform/requirements.lock.txt` pins `cffi (20)`, `cryptography (27)`, `PyJWT (49)`, `stripe (58)`,
`pycparser (45)`; `requirements.txt (14)` declares `PyJWT[crypto]`. Tests `core/tests/test_clerk_auth.py ::
RS256PemModeTest (116)`, `RS256JwksModeTest (165)` (the F-16 proof, `13-f16-clean-env-proof.txt`).

## 12. CI, contracts and the gates (`.github/workflows/ci.yml`)

Jobs: `test` (system check, `makemigrations --check`, the platform suite, the SDK suite), `contracts` (vocabulary
regeneration zero-diff, SDK coverage manifest zero-diff, the contract suite, the migration-ledger ratchet, the SDK
coverage ratchet), `conformance` (Schemathesis, non-blocking), `contract` (spec drift zero-diff, SDK core and exception
regeneration zero-diff, the cumulative breaking gate vs `api-v1-cutover`, the UI snapshot/types/typecheck/tests),
`codegen` (typecheck, lint, the renderer suite with the shell tools) and `code-builder-execution`. Native required
checks on `main` are not configured (`05` §5). Stage D ran every local equivalent (`00-static.txt`, `10-console-codegen.txt`,
`12-suite-*`).

## 13. Data-flow walkthroughs proven in Stage D (where to read them)

- A prepaid credit → drawdown → floor → recovery (`off` and `enforcing`): `03-prepaid-off.txt` / `03-prepaid-enforcing.txt`
  steps 3-9.
- A manual hold → floor → release (HANDED_OVER) → recovery: `03-prepaid-*` step 9b.
- A Stripe checkout credit (real objects) → partial/duplicate/second/full refunds → a failed refund alert: `03-prepaid-*` step 13.
- A postpaid month → skips → push (real objects) → resume → failures → repush → AR → the hand-over → the platform fee: `04-postpaid.txt`.
- A subscription opened through the route (A-1) → seats and the converging reconciler → lifecycle → re-price → sync →
  webhooks through the subscriptions receiver → an invoice before its mirror and its recovery → bind-once: `06-plans-subscriptions.txt`.
- A referral program in basis points and a flat fee paid once: `07-referrals.txt`.
