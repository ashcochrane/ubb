# Track-Mode Tenant Onboarding — Design

**Date:** 2026-04-21
**Status:** Draft
**Scope:** Onboarding flow for a new tenant using "track costs" mode only. Revenue and billing modes are out of scope for this spec.

---

## 1. Goal

Take a Clerk-authenticated user who has never used the platform and land them on a usable dashboard with:

- A `Tenant` row (products=`["metering"]`).
- A `TenantUser` row linking their Clerk user ID to the tenant as `owner`.
- One `TenantApiKey` they can use to send usage events.
- Optionally, a first pricing card and the SDK snippet needed to integrate.

"Usable" means: the dashboard renders, API calls authenticate, and the user has everything they need to start sending usage events from their own codebase.

---

## 2. Non-goals

- Revenue-mode or billing-mode onboarding (Stripe key validation, customer matching, margin config). The existing `features/onboarding/components/{stripe-key-step,customer-mapping-step,margin-config-step,review-step}.tsx` files are being **deleted** in this work to avoid bitrot. They will be reintroduced with fresh eyes when those modes ship.
- Teammate invites / multi-user tenants. Schema already enforces one Clerk user = one Tenant via `TenantUser.clerk_user_id unique=True`.
- API key rotation / regeneration UI. Users who lose the key displayed in Step 3 are a known edge case for this phase.
- Abandoned-wizard re-engagement email.
- End-to-end (Playwright) browser tests.

---

## 3. Key decisions

### 3.1 Provisioning trigger: explicit endpoint, not Clerk webhook

We use pattern **C** (explicit wizard-driven endpoint) now, with the architecture structured so pattern **A** (Clerk `user.created` webhook) becomes a one-file addition later.

Rationale for C now:
- No public webhook URL required (no ngrok or deployment).
- No webhook signing / retry / idempotency handling to build.
- Matches where the product is: early, local, pre-deployment.

Why A is the long-term answer and will be migrated to later:
- Clerk users can be created via OAuth, email signup, invites, or the Clerk dashboard. Only a webhook catches all paths.
- Decouples "account exists" from "user clicked something in your UI."

Migration path (tracked as follow-up): add `POST /webhooks/clerk/user.created` that calls the same `provision_tenant_for_clerk_user` service function with a placeholder tenant name. Wizard Step 1 changes from `POST /platform/tenant` (create) to `PATCH /platform/tenant` (rename). Nothing else changes.

### 3.2 Data collected: guided but skippable

- **Step 1** — workspace name. Required. Creates Tenant, TenantUser, TenantApiKey.
- **Step 2** — first pricing card. Strongly encouraged, "Skip for now" available.
- **Step 3** — SDK snippet with API key and copy button. Informational. "Done" completes onboarding.

A persistent getting-started checklist on the dashboard shows whichever items were skipped.

### 3.3 Gating: redirect + explicit completion flag

- Any authed user hitting `/_app/*` routes without a completed onboarding is redirected to `/onboarding`.
- Completion is tracked via `Tenant.onboarding_completed_at` (nullable `DateTimeField`, indexed).
- Tenant-exists-means-onboarded is explicitly rejected because it conflates "user finished the wizard" with "user entered a name then closed the tab."

### 3.4 Scope guardrails (locked)

- One Clerk user owns exactly one tenant (enforced by schema).
- No invite / teammate flow in this spec.
- Existing TenantUser → skip wizard, go to dashboard.
- Visiting `/onboarding` when already completed → redirect to `/`.

---

## 4. Architecture

Four pieces:

### 4.1 Provisioning service — `apps/platform/tenants/services.py` (new file)

```python
def provision_tenant_for_clerk_user(
    clerk_user_id: str,
    tenant_name: str,
) -> tuple[Tenant, TenantUser, str]:
    """Create a tenant, tenant user, and API key for a Clerk user.

    Idempotent: if a TenantUser already exists for clerk_user_id, returns
    the existing tenant with raw_api_key=None (keys are returned once only).

    Fetches the canonical email from the Clerk Backend API using
    CLERK_SECRET_KEY. Do not accept email from the client.

    Wraps all writes in a single transaction.atomic() block.
    Emits a 'TenantProvisioned' outbox event on first creation.
    """
```

Single entry point for both the endpoint now and the Clerk webhook later. This is the seam that makes the A-migration trivial.

### 4.2 Platform `me` endpoint

`GET /api/v1/platform/me` — authed by Clerk JWT.

```json
{
  "tenant_user": { "id": "...", "email": "...", "role": "owner" } | null,
  "tenant": {
    "id": "...",
    "name": "...",
    "products": ["metering"],
    "pricing_cards_count": 0,
    "usage_events_count": 0
  } | null,
  "onboarding_completed": true | false
}
```

Called by the UI on app boot via `useMe()`. Single round-trip for auth context plus the counts needed by the getting-started checklist (avoids N+1 requests on dashboard load).

### 4.3 Onboarding endpoints — `api/v1/platform_endpoints.py`

- `POST /api/v1/platform/tenant` — body `{ "name": "..." }`. Calls `provision_tenant_for_clerk_user`. Returns `{ tenant, api_key }` on first creation, `{ tenant, api_key: null }` on idempotent replay.
- `PATCH /api/v1/platform/tenant` — body may contain `{ "name"?, "complete_onboarding"?: true }`. Updates the caller's tenant only (enforced by `request.tenant.id` from middleware). When `complete_onboarding: true` is present, the server sets `onboarding_completed_at = timezone.now()`. Clients never send raw timestamps.

The `PATCH` endpoint replaces a separate `/onboard/complete` action. This is more RESTful and generalizes to future tenant-update flows (margin defaults, branding, etc.) without spawning new action URLs.

### 4.4 UI routing guard — `ubb-ui/src/app/routes/_app/route.tsx`

```ts
beforeLoad: async ({ context }) => {
  const me = await context.queryClient.ensureQueryData(meQueryOptions);
  if (!me.tenantUser || !me.onboardingCompleted) {
    throw redirect({ to: "/onboarding" });
  }
}
```

`ensureQueryData` reads from cache or fetches. No separate "prefetch in root route" — one pattern, no drift. Canonical TanStack Router pattern.

Inverse guard on `/onboarding` route: if `onboardingCompleted === true`, redirect to `/`.

### 4.5 First-login flow

```
Clerk sign-in
  → UI calls GET /platform/me
  → tenant_user=null
  → redirect to /onboarding
  → user submits workspace name
  → POST /platform/tenant
  → tenant + tenant_user + api_key created in one transaction
  → outbox emits TenantProvisioned
  → wizard shows Step 2 (create first card, skippable) and Step 3 (SDK snippet)
  → user hits Done
  → PATCH /platform/tenant { complete_onboarding: true }
  → invalidate useMe query
  → redirect to dashboard
```

---

## 5. Data model changes

### 5.1 `Tenant` migration

Add one field:

```python
onboarding_completed_at = models.DateTimeField(
    null=True, blank=True, db_index=True,
)
```

Indexed because `/platform/me` reads it on every authed dashboard request.

No other schema changes. `products`, `default_margin_pct`, `name`, `widget_secret` already exist and are sufficient.

### 5.2 `TenantUser` — no change

Existing fields cover everything:
- `clerk_user_id` (unique) — set from JWT `sub`.
- `email` — set from Clerk Backend API lookup.
- `role` — set to `"owner"` for the first (and only) user of a tenant.

### 5.3 Provisioning writes (all inside one `transaction.atomic()`)

1. `Tenant.objects.create(name=<from wizard>, products=["metering"], onboarding_completed_at=None)`.
2. `TenantUser.objects.create(tenant=tenant, clerk_user_id=<from JWT sub>, email=<from Clerk API>, role="owner")`.
3. `TenantApiKey.create_key(tenant, label="default")`.
4. `OutboxEvent.objects.create(event_type="TenantProvisioned", payload={"tenant_id": ..., "clerk_user_id": ..., "mode": "track"})`.

Concurrent provisioning is fenced by the `TenantUser.clerk_user_id` unique constraint. On `IntegrityError`, the handler returns the already-existing tenant without raising.

### 5.4 Outbox event — `TenantProvisioned`

New event type. No handlers registered in this spec — track mode has none. Documented in `apps/platform/events/` as "emitted whenever a new tenant is created; safe to subscribe." When billing/subscriptions apps need it later (e.g., to provision a default margin config or Stripe Connect application link), they register a handler without touching provisioning code.

### 5.5 Settings & env

- `config/settings.py`: add `CLERK_SECRET_KEY = env("CLERK_SECRET_KEY", default="")`. `CLERK_ISSUER_URL` already exists.
- `ubb-platform/.env.example`: add `CLERK_SECRET_KEY=` with a comment.
- `ubb-platform/.env`: add real secret locally (not committed).

### 5.6 Clerk Backend API client — `core/clerk_api.py` (new file)

Thin helper with one function:

```python
def get_clerk_user(user_id: str) -> dict:
    """Fetch canonical user data from Clerk Backend API.

    Raises ClerkAPIError on non-2xx, timeout, or missing CLERK_SECRET_KEY.
    Called exactly once per user, at provisioning time. Not cached.
    """
```

Uses `requests` with `Authorization: Bearer {CLERK_SECRET_KEY}` against `https://api.clerk.com/v1/users/{user_id}`.

Email comes from here, never from the client request body. This is the security reason for the endpoint: accepting email from the client means anyone with a valid JWT can write any email against their TenantUser.

---

## 6. UI implementation

### 6.1 New `useMe()` hook

File: `ubb-ui/src/features/auth/api/queries.ts` (new file, matches existing feature structure).

```ts
export const meQueryOptions = queryOptions({
  queryKey: ["me"],
  queryFn: () => platformApi.GET("/me").then(r => r.data),
  staleTime: Infinity,
});
export const useMe = () => useQuery(meQueryOptions);
```

Invalidated explicitly after onboarding mutations. No polling.

### 6.2 Wizard — `features/onboarding/`

Structural changes:

- **Delete** `stripe-key-step.tsx`, `customer-mapping-step.tsx`, `margin-config-step.tsx`, `review-step.tsx`, `mode-selector.tsx`, `match-results-table.tsx`, `permissions-table.tsx`, `activation-success.tsx`, and their related schema fields. Step 3's "Done" button redirects to the dashboard directly — no separate success screen. Git remembers; reintroduce with fresh eyes when revenue/billing ship.
- **Replace** `onboarding-wizard.tsx` with a three-step track-mode flow.
- **Replace** `api/api.ts` — new methods: `createTenant({ name })` → `POST /platform/tenant`, `completeOnboarding()` → `PATCH /platform/tenant { complete_onboarding: true }`.
- **Replace** `api/types.ts` — trim to track-mode types only.
- **Delete** mock-only code paths in `api/mock.ts` that correspond to removed modes. Keep `mock.ts` for the remaining endpoints.

Wizard steps:

1. **Name your workspace** — single text input (1–255 chars, trimmed). On submit, call `createTenant`, store returned `api_key` in wizard-local component state, invalidate `["me"]`, advance to Step 2.
2. **Create your first pricing card** — embed the existing pricing-card creation form as an inline component. Requires a small refactor: extract the form body from `ubb-ui/src/app/routes/_app/pricing-cards/new.tsx` into `features/pricing-cards/components/pricing-card-form.tsx` with `onSuccess` and `onSkip` props. The existing route becomes a thin wrapper. "Skip for now" link advances to Step 3 with no network call.
3. **Connect the SDK** — shows the API key from Step 1's response and a copy-pasteable code snippet. Two copy buttons. "Done" calls `completeOnboarding` (`PATCH /platform/tenant { complete_onboarding: true }`), invalidates `["me"]`, redirects to `/`.

### 6.3 Routing guards

- `ubb-ui/src/app/routes/_app/route.tsx`: `beforeLoad` using `ensureQueryData(meQueryOptions)`. Redirect to `/onboarding` if `tenantUser` is null or `onboardingCompleted` is false.
- `ubb-ui/src/app/routes/onboarding.tsx`: same hook; if already complete, redirect to `/`.

### 6.4 Getting-started checklist — `features/dashboard/components/getting-started.tsx` (new)

Collapsible, dismissible-per-item panel on the dashboard. Items for track mode:

- Create first pricing card — derived: `tenant.pricing_cards_count > 0`.
- Send first usage event — derived: `tenant.usage_events_count > 0`.
- Invite a teammate — stubbed, always unchecked, links nowhere yet (placeholder for when invites ship).

Counts are added to the `/platform/me` response payload to avoid N+1 queries on dashboard load.

Dismissal state is stored in `localStorage` for this phase. This is a deliberate shortcut — the long-term home is a per-user DB field. Migration plan:

- When invites land and `TenantUser` becomes multi-row, add `TenantUser.ui_preferences = models.JSONField(default=dict)`.
- Move `dismissed_checklist_items` into that field.
- Existing localStorage keys are ignored on first server-backed load.

### 6.5 `useAuthStore` cleanup

- Today's `activeTenantId` / `tenantMode` / `setTenant` are removed. Tenant identity is sourced from `useMe()` — one source of truth. Duplicating server state in a Zustand store is the standard React anti-pattern being removed here.
- If anything else is in the store (ephemeral UI state: open modals, active nav section, etc.), keep only those. If nothing else, delete `useAuthStore` entirely.

### 6.6 `MOCK_TENANT_ID` removal

`ubb-ui/src/features/onboarding/lib/constants.ts` `MOCK_TENANT_ID` is deleted. Mock-mode auth bootstraps via the mock implementation of `useMe()`.

---

## 7. Error handling & edge cases

### 7.1 Provisioning failures

| Failure | Behavior |
|---|---|
| Clerk API unreachable / returns non-2xx on email fetch | 503 to client, transaction rolled back, no partial state. UI message: "Couldn't verify your account, please retry." |
| `CLERK_SECRET_KEY` missing | 503 at endpoint entry with explicit log line. Same client UX. |
| DB error mid-transaction | Atomic rollback, 500 to client, retryable. |
| Concurrent `POST /platform/tenant` from same Clerk user | Second loses on unique constraint. Handler catches `IntegrityError`, returns existing tenant. |
| Repeat `POST /platform/tenant` after success | Returns existing tenant, `api_key: null`. Never re-reveals the key. |

### 7.2 Wizard state

- Step 1 form values: `react-hook-form` local state. Lost on page refresh (one field, acceptable).
- API key: wizard-local component state only. **Never persisted anywhere else.** Lost on refresh between Step 1 and Step 3.
- Recovery from lost key: "Your key was shown on the previous step. If you missed it, generate a new one from Settings." (Settings key management is a future spec; for this phase, the message links to a placeholder page.)
- "Skip" on Step 2: pure UI transition, no network.
- "Done" on Step 3: the one and only write of `onboarding_completed_at`.

### 7.3 Routing edge cases

| Case | Behavior |
|---|---|
| User visits `/onboarding` after completion | Redirect to `/`. |
| User visits `/` before onboarding, tenant exists, onboarding incomplete | Redirect to `/onboarding`. Wizard opens at Step 2 (since Step 1 has already succeeded — tenant exists). Step 3 shows a banner in place of the previously-displayed API key: "Your API key was shown earlier. If you didn't copy it, generate a new one from Settings." |
| User visits `/` before onboarding, no tenant | Redirect to `/onboarding`, Step 1. |
| Clerk JWT expired mid-wizard | `/me` returns 401, Clerk SDK refreshes. If refresh fails, back to sign-in. |
| No valid Clerk JWT on any `_app/*` route | Handled by existing Clerk `<SignedIn>` gate before our `beforeLoad` runs. |

### 7.4 Validation

- Tenant name: 1–255 chars after `.strip()`. Server rejects with 422.
- No uniqueness requirement on name (two "Acme Corp" tenants are fine).
- No XSS concern: React escapes output; server stores raw.

### 7.5 Double-submit guards

Mutations use TanStack Query's built-in `isPending` to disable submit buttons. No custom debouncing.

---

## 8. Testing strategy

TDD throughout: red → green → refactor.

### 8.1 Backend (`ubb-platform/`, pytest)

New test files:

- `apps/platform/tenants/tests/test_provisioning.py`:
  - `test_provisions_tenant_and_user_and_key` — happy path; all three rows exist, raw key returned once.
  - `test_is_idempotent_per_clerk_user` — second call returns existing tenant, no duplicate rows, `api_key` is `None`.
  - `test_rolls_back_on_clerk_api_failure` — Clerk API raises; no tenant, no user, no key in DB.
  - `test_handles_concurrent_provisioning` — simulated `IntegrityError` from unique constraint; handler returns existing tenant without raising.
  - `test_emits_tenant_provisioned_outbox_event` — exactly one `OutboxEvent` with correct type and payload.
- `core/tests/test_clerk_api.py` — mock `requests`; cover 200, 404, 500, timeout, missing secret.
- `api/v1/tests/test_platform_onboarding.py`:
  - `GET /platform/me`: unauthed (401), authed without TenantUser (`tenant_user: None`), authed with incomplete, authed with complete.
  - `POST /platform/tenant`: success, missing `CLERK_SECRET_KEY` returns 503, invalid tenant name (empty, >255) returns 422, replay returns existing tenant with `api_key: null`.
  - `PATCH /platform/tenant`: `{ complete_onboarding: true }` sets `onboarding_completed_at` to the current time; `{ name: "..." }` renames; rejects cross-tenant updates (403).

Extensions to existing files:
- `apps/platform/tenants/tests/test_models.py`: `onboarding_completed_at` defaults to `None`; migration creates the index.

### 8.2 Frontend (`ubb-ui/`, Vitest + React Testing Library)

New tests:

- `features/auth/api/queries.test.ts` — `useMe` maps server response shape correctly; handles 401 gracefully.
- `features/onboarding/components/onboarding-wizard.test.tsx` — rewritten to cover the three-step track flow: Step 1 submit → Step 2 renders with "Skip" → Step 3 renders with API key → Done fires PATCH.
- `features/onboarding/api/api.test.ts` — `createTenant` and `completeOnboarding` call correct endpoints (MSW handlers).
- Colocated test for the `_app/route.tsx` guard — different `me` fixtures produce correct redirect behavior.
- `features/dashboard/components/getting-started.test.tsx` — items show/hide based on counts; dismissal persists to localStorage.

### 8.3 Dev-data seeding

Update `apps/platform/tenants/management/commands/seed_dev_data.py`:
- Also create a `TenantUser` tied to a known Clerk test-user ID (env or arg).
- Set `tenant.onboarding_completed_at = timezone.now()` so the dev tenant skips the wizard.

### 8.4 Not tested in this spec

- End-to-end Playwright suite — repo doesn't have one; adding it is a separate initiative.
- Clerk's JWT issuance itself — we trust the Clerk SDK. Our JWT verification is already covered in `core/tests/test_clerk_auth.py`.

---

## 9. Follow-up work (tracked, not built here)

1. **Migrate to pattern A** — Clerk `user.created` webhook calling the same `provision_tenant_for_clerk_user`. Wizard Step 1 becomes a rename. Requires deployed webhook URL + signing secret + idempotent handler.
2. **API key rotation / regeneration UI** — Settings page with "View keys" / "Create new key" / "Revoke". Addresses the "user lost their key mid-wizard" case.
3. **Invites / multi-user tenants** — lift `TenantUser.clerk_user_id` unique constraint; add invite flow; tenant switcher in UI; move getting-started dismissals from localStorage to `TenantUser.ui_preferences`.
4. **Revenue and billing mode onboarding** — re-introduce the Stripe-key / customer-matching / margin-config steps, with real backend endpoints.
5. **Abandoned-wizard re-engagement email** — product decision + email infra.
