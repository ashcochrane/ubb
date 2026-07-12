# Stripe Connection Model for UBB Tenants — Research Brief

**Date:** 2026-06-09 · **Question:** how should UBB's tenants connect Stripe so UBB can orchestrate billing, while minimizing UBB's regulatory burden, keeping Stripe-branded invoices, and "improving as Stripe improves"? **Decision: Standard OAuth (the tenant connects their OWN Stripe).**

## Industry standard (verified via web research)
Every major UBB platform integrates with the **merchant's own existing Stripe account** — the merchant is the account-holder / merchant-of-record. **None onboard sub-merchants via Connect Express/Custom** (that's the *marketplace* model — Uber/DoorDash).

| Platform | How it connects |
|---|---|
| **Metronome** (Stripe-owned) | "Connect your Stripe account… permissions to write/read on your behalf to your Stripe account"; creates the invoice in *your* Stripe |
| **Orb** | "Connect to Stripe"; invoices synced to *your* Stripe Invoicing |
| **Lago** (self-hosted, closest analog) | Paste your Stripe API key (restricted keys supported); pushes into the merchant's own Stripe |
| **m3ter** | Webhook-wired; writes invoice items into *your* regular Stripe |
| **Chargebee** | OAuth link to *your existing* Stripe account |

## Regulatory/liability burden — Express vs Standard/OAuth vs direct key
Liability follows the **charge type**, not just the account type. UBB uses **direct charges on the connected account** (`stripe_account=` header → payment lands in the connected account's balance) → **the connected account is merchant-of-record and disputes debit *their* balance**, regardless of Standard vs Express.

| Dimension | Express (UBB provisions) | Standard / OAuth (merchant's own) | Direct restricted key |
|---|---|---|---|
| KYC responsibility | **Platform (UBB)** | Account-holder (tenant) | Tenant |
| Dispute/fraud liability | **Platform "responsible for disputes and fraud"** | Connected account's balance | Connected account's balance |
| Negative-balance backstop | **Platform ultimately liable** | Account-holder | Merchant |
| ToS / PayFac / PCI posture | Heaviest (payment-facilitator-like) | Light (connected app) | Lightest (ordinary integration) |
| Dashboard | Limited Express dashboard | **Full own Stripe dashboard** | Full own dashboard |
| Invoice/receipt branding | Tends to surface the platform | **Merchant's own Stripe branding** | Merchant's own branding |
| Secret storage | n/a | Revocable OAuth token (no long-lived secret) | **Stores a powerful tenant key** (encrypt + rotate) |

**Express is the wrong call for a small company minimizing burden** — it makes UBB the KYC collector, dispute/fraud owner, and negative-balance backstop (payment-facilitator territory), recreating exactly the regulated surface to avoid.

## Decision + technical confirmation
**Standard OAuth (the tenant connects their own Stripe), restricted-key paste as a possible later fallback.** Confirmed: UBB can create Subscriptions/Prices/Invoices on a **Standard** connected account via `stripe_account=` exactly as it does today — the connected-account mechanism is type-agnostic, so **switching from Express to Standard OAuth needs ZERO charge-path code changes; only the onboarding differs.** The one downside to accept: because the tenant owns the account, UBB can't guarantee its health — if the tenant restricts/revokes it, orchestration breaks for that tenant; UBB must surface a clear connection-health/`charges_enabled` state and handle `account.application.deauthorized`.

**Flow:** `POST /connect/start` (tenant key) → `connect.stripe.com/oauth/authorize?...&state=<nonce>` → tenant authorizes → Stripe redirects to `GET /connect/callback?code&state` → `stripe.OAuth.token` → persist the `acct_` on the tenant → `account.updated`/`deauthorized` webhooks maintain `charges_enabled`.

**Sources:** Stripe Docs (Metronome integration, Standard accounts, merchant-of-record, Connect charges, risk-management, OAuth-standard-accounts), Metronome/Orb/Lago/m3ter/Chargebee integration docs.
