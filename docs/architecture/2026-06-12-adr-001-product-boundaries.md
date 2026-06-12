# ADR-001: Product Boundaries — The Dependency Matrix

- **Status:** Accepted (2026-06-12)
- **Enforced by:** `ubb-platform/apps/platform/tests/test_product_boundaries.py` (AST walker, runs in the normal pytest suite / CI)
- **Supersedes:** the grep-based verification rules in `docs/plans/2026-02-09-decouple-customer-from-billing-design.md` §Verification

## Context

[two-product-separation.md](two-product-separation.md) states the golden rule: *"Usage never
touches payment providers. Billing never touches usage calculations. They communicate through
events and commands."* The decoupling design of 2026-02-09 operationalised that with three grep
rules (`grep -r "from apps.billing" apps/platform/` returns nothing, etc.).

Two things made that insufficient:

1. **The doc models two products; the codebase has four.** Metering, billing, subscriptions and
   referrals all sit on a shared platform kernel (`apps/platform`: tenants, customers,
   events/outbox, runs) plus `core/` plumbing and the `api/` composition layer. The grep rules
   never covered subscriptions or referrals, and never covered the `apps -> api` direction at all.
2. **Measured erosion.** At main (`c5a1a0e`) there were 0 unsanctioned runtime cross-product
   imports. Roughly 100 commits later (before the F3 boundary-restoration pass) there were
   **14 unsanctioned cross-product import statements plus 2 `apps -> api` layering inversions**.
   Almost all of them were *lazy* (function-body) imports — invisible to naive grep discipline and
   to Django's import-time failure modes — and the lazy-import circular-dependency workaround had
   already **self-propagated once**: the first instance was copied as the template for the next
   violation before F3.1 removed the pattern. After F3.1–F3.3 the count is 0 again.

Notably, the one violation the original design doc called out by name —
`usage_service` calling `AutoTopUpService` directly — had already been fixed properly:
`usage_service` has zero billing imports today; auto-top-up rides the outbox
(`balance.low` event -> billing handler).

Boundaries that are only prose get re-eroded. This ADR records the matrix; the AST test enforces
it on every CI run, including imports hidden inside function bodies.

## Decision

The dependency matrix, numbered exactly as enforced by `test_product_boundaries.py`:

1. **Anything may import `core/` and `apps/platform`.** They are the kernel: tenants, customers,
   the outbox, runs, auth, locking.
2. **`apps/platform/**` and `core/**` never import products** (`apps.billing`, `apps.metering`,
   `apps.subscriptions`, `apps.referrals`). When the platform needs a product to react
   *synchronously* (e.g. a seat-roster change must push a Stripe quantity in the same
   transaction's `on_commit`), it goes through the listener registry in
   `apps/platform/customers/hooks.py` — products register listeners in their
   `AppConfig.ready()`. Asynchronous needs use the outbox. (`core/` may import only
   `apps.platform.*` among apps.)
3. **Product <-> product communication happens ONLY via four named channels:**
   - **Outbox events** — `apps.platform.events.outbox.write_event` + the handler registry.
     The default. Anything that can tolerate seconds of latency belongs here.
   - **Per-product `queries.py` read contracts** — module-level functions returning plain data
     (dicts/ints/lists, never ORM querysets or model instances). Today:
     `apps/metering/queries.py` and `apps/billing/queries.py`, importable by any product.
     (`apps/billing/queries.py` was promoted to the shared list for the F4.2 backfill
     closed-period guard: metering's `record_usage` consults
     `is_usage_period_closed()` before accepting a backdated `effective_at`.
     `apps/metering/queries.py` additionally carries one deliberate *consume*
     function — `clear_backfill_dirty_period()` — the ack half of the
     `BackfillDirtyPeriod` marker contract consumed by subscriptions.)
   - **Platform lifecycle hooks** — the `customers/hooks.py` registry above, for synchronous
     reactions to platform-owned lifecycle changes.
   - **Per-pair `ports.py` modules** — an explicit, documented call surface one product exposes
     to one other product. Currently only `apps/subscriptions/ports.py`, consumed by billing
     (invoice payment-failed fast path + dead-letter invoice repair).
4. **`api/v1` and `apps/*/api` are the composition layer.** They may import any product —
   wiring products together is their job. Products never import `api.*` (in either form: the
   top-level `api/` package or another product's `api/`... the test flags any `api`-rooted
   import from `apps/` or `core/`).
5. **Named exception — the "Stripe connector kit."** Three billing-owned modules are importable
   by subscriptions because they are shared Stripe infrastructure, not billing business logic:
   - `apps.billing.stripe.services.stripe_service` — the `stripe_call` wrapper (error mapping,
     retry) + the global Stripe API-version pin;
   - `apps.billing.stripe.models.StripeWebhookEvent` — deliberately **one** webhook dedup table
     across both webhook endpoints (billing's and subscriptions'), so a replayed Stripe event is
     deduplicated no matter which endpoint receives it;
   - `apps.billing.connectors.stripe.invoice_routing` — the AR state-transition table + invoice
     URL refresh helpers, which `apps/subscriptions/ports.py` builds on.
   If the products ever split into services, this kit's future home is a real shared package
   (`apps/connectors/`), at which point the exception disappears from the allowlist.
6. **Dev-only management commands are exempt** via the test's explicit file allowlist. Currently
   only `apps/platform/tenants/management/commands/seed_dev_data.py` (it seeds billing config
   for local dev; it never runs in production code paths).
7. **Generic model access via Django's app registry is the sanctioned pattern for
   platform-kernel maintenance sweeps** (F4.4 sandbox reset,
   `apps/platform/tenants/tasks.py`). The kernel must never import product modules
   (rule 2), and a reset that had to *name* every product model would silently leak
   rows whenever a new model shipped. The sandbox wipe therefore discovers
   tenant-scoped models generically (`django.apps.apps.get_models()`, any concrete
   model with a FK/O2O to `Tenant`) and addresses the keep-config exceptions by
   `app_label.ModelName` string labels — zero import edges, automatic coverage of
   new product models, and the AST walker stays authoritative for import discipline.
   This is data-plane janitorial work (delete rows by tenant), never business logic:
   a kernel sweep must not call product services or enforce product invariants.
8. **`apps/platform/tests/test_product_boundaries.py` IS the enforcement.** It walks the AST of
   every non-test, non-migration module under `apps/` and `core/` — all nodes, so lazy
   function-body imports are caught — resolves relative imports, and fails with `file:lineno`
   pointing back at this document. It supersedes the grep rules in the 2026-02-09 design doc.
   Changing the matrix means changing the test's allowlists *and* this ADR in the same commit.

## Consequences

- **Boundary drift is machine-checked in CI.** A new unsanctioned import fails the suite with the
  exact file and line, instead of being discovered N commits later by archaeology.
- **The service-split path stays real.** Each channel has a mechanical extraction story:
  `queries.py` -> HTTP endpoint, `ports.py` -> RPC, hooks -> events. Nothing crosses a boundary
  in a way that couldn't survive a network hop being inserted.
- **The hooks registry is synchronous coupling by another name — intentionally.** The F3 pass was
  required to be behavior-identical, and the seat-quantity push must bind to the roster change's
  own transaction commit. Migrating seat sync fully to the outbox is the recorded next step:
  `CustomerDeleted` is already emitted at the soft-delete site
  (`apps/platform/customers/models.py`), but the Stripe-webhook suspend paths
  (`apps/billing/connectors/stripe/webhooks.py`) call the hook directly and would need a
  customer-suspended event emitted at those sites first.

## Recorded follow-ups

- `api/v1/platform_endpoints.py` still calls `sync_seat_quantity_on_commit` directly on seat
  creation (line ~65). That is a *legal* direction (composition layer -> product) but
  inconsistent with the hook registry used everywhere else — candidate cleanup.
- There is **no periodic seat-quantity reconciler** today. The `seats.py` docstring used to claim
  an "hourly subscription sync" backstop that does not exist (fixed in the same commit as this
  ADR). The push is full-state (live seat count, not a delta), so any missed push self-corrects
  on the next roster change — but a roster that goes quiet after a failed push stays wrong until
  then. Adding a real seat reconcile task (or completing the outbox migration above, whose
  sweeper retries provide the same guarantee) is the recorded next step.

## Branch decision record (2026-06-12): `feat/ubb-ui-dashboard` status

Not a code boundary, but the same class of decision — recorded here so it is discoverable next
to the matrix it would otherwise violate.

- **What the branch is.** `feat/ubb-ui-dashboard` is a **fork**, not a feature branch: it carries
  the UI scaffold + Clerk auth **and a rival Card/Rate/Group pricing schema** whose migration
  numbers **collide** with the shipped RateCard engine's migrations
  (`apps/metering/pricing/` on this branch).
- **Owner's direction (2026-06-12).** UI work is **OUT of scope** for now.
- **Status: READ-ONLY SOURCE.** The branch's SDK retry commits were already cherry-picked in
  F0.5 (`65b18e6`…`8c98873` on `tl-changes-05-06-26`); anything else of value gets extracted the
  same way — commit by commit, reviewed against the shipped schema.
- **It must NEVER be merged wholesale.** A merge would import the rival pricing schema and the
  colliding migration numbers on top of the live RateCard engine.
- **When UI work resumes:** extract the UI / Clerk auth / dashboard endpoints onto a **fresh
  branch off current `main`** and **discard the fork's pricing commits** entirely.
