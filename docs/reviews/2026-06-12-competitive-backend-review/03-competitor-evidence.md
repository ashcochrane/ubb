# Competitor evidence base — sourced facts only

**Date:** 2026-06-12
**Review:** Competitive backend review (`docs/reviews/2026-06-12-competitive-backend-review/`)
**Status of this document:** Evidence registry. Not analysis.

## Preamble — why this file exists

Every competitor claim made anywhere else in this review must trace back to a fact in this file, and every fact in this file traces to a URL that was actually fetched (or, where noted, search-indexed) on the access date shown. **Anything not in this file must not be asserted as competitor fact elsewhere in the review.** Where we tried to verify something and could not, it is listed explicitly in the consolidated "Could not verify — do not assert" section at the end; those items may be discussed only as *unverified* and must never be stated as fact.

Confidence levels:

- **high** — taken directly from a first-party page (vendor docs, vendor security page, vendor status page, official repo) fetched on the access date.
- **medium** — partner-published case study, vendor marketing blog, or search-indexed content where the page itself could not be fetched directly. Treat as attributed claim, not established fact.

All facts below were accessed **2026-06-12** unless otherwise noted.

## Table of contents

1. [Metronome](#1-metronome)
2. [Orb](#2-orb)
3. [Lago](#3-lago)
4. [OpenMeter (short)](#4-openmeter-short)
5. [Amberflo (short)](#5-amberflo-short)
6. [Stripe native UBB (short)](#6-stripe-native-ubb-short)
7. [Could not verify — do not assert](#7-could-not-verify--do-not-assert)

---

## 1. Metronome

| Axis | Fact | Source | Accessed | Confidence |
|---|---|---|---|---|
| Event ingestion API | The /ingest endpoint accepts 1-100 events per request ("maxItems: 100"). transaction_id is required (1-128 chars) and "serves as your idempotency key, ensuring events are processed exactly once" with a "34-day deduplication window". Timestamps must be RFC 3339. | https://docs.metronome.com/api-reference/usage/ingest-events | 2026-06-12 | high |
| Event ingestion API | Backfill window: "Historical events can be backdated up to 34 days and will immediately impact live customer spend." | https://docs.metronome.com/api-reference/usage/ingest-events | 2026-06-12 | high |
| Event ingestion API | "Once a usage event is accepted with a given transaction ID, subsequent events within the next 34 days with the same ID are treated as duplicates and ignored." "Timestamps more than 24 hours in the future are rejected by the API." On HTTP 429 the documented guidance is exponential backoff and retry until 200; no numeric rate limit is published on this page. | https://docs.metronome.com/connect-metronome/send-usage-events/ | 2026-06-12 | high |
| Event ingestion API | Four idempotency mechanisms: transaction_id for /ingest (34-day retention); ingest alias for customer writes (retained "Until released"); uniqueness_key for contracts/alerts/commits/credits ("Until released", reuse returns HTTP 409 "This uniqueness key has already been used."); and an Idempotency-Key header on POST requests cached ">= 24 hours" — same key + identical params replays the original result, same key + different params returns HTTP 409, and "Idempotency applies even if a request returns an HTTP 500 error". | https://docs.metronome.com/developer-resources/use-api/idempotency/ | 2026-06-12 | high |
| Event ingestion API | Invoice-level grace period for late events: "After the billing period ends, Metronome enforces a grace period before finalizing the invoice... The grace period is 24 hours by default" (customizable via your Metronome representative). Finalized invoices are immutable but can be voided and regenerated via UI or the /invoices/regenerate API, recalculating "using up-to-date usage and pricing terms". | https://docs.metronome.com/guides/get-started/core-concepts/how-invoicing-works | 2026-06-12 | high |
| Scale claims | First-party claim in the ingest API reference: "Metronome supports 100,000 events per second without requiring pre-aggregation or rollups." | https://docs.metronome.com/api-reference/usage/ingest-events | 2026-06-12 | high |
| Scale claims | Confluent customer case study (partner-published, not Metronome first-party) claims Metronome is "streaming billions of events per day" and processes "over 10,000 invoices per second" / "tens of thousands of invoices processed per second with no downtime". | https://www.confluent.io/customers/metronome/ | 2026-06-12 | medium |
| Deployment model | Cloud SaaS with at least two hosted environments per client: "Clients commonly connect Stripe to Metronome production and sandbox environments." No self-host or BYOC option appears anywhere in the docs or security pages fetched. | https://docs.metronome.com/integrations/invoice-integrations/stripe | 2026-06-12 | high |
| Compliance & trust | Security page displays SOC 1 Type 2 and SOC 2 Type 2 certifications; "Metronome encrypts your data in transit and at rest. We use modern cryptographic algorithms like AES256-GCM"; conducts "extensive security-design reviews and regular penetration tests"; zero-trust architecture with SSO and least privilege. Note: the SOC 2/ISO 27001/PCI DSS sentence on this page refers to Metronome's cloud providers, not Metronome itself (only SOC 1/SOC 2 are shown as Metronome's own). | https://metronome.com/company/security | 2026-06-12 | high |
| Compliance & trust | Public status page exists (status.metronome.com) listing components: API (2 components), Usage Pipeline, Alerts, Dashboard, Data Export, Embeddable Dashboards. Status "fully operational" at access time; the page does NOT publish uptime percentages. | https://status.metronome.com | 2026-06-12 | high |
| Sandbox/test environments | A "Metronome Sandbox" environment exists alongside production; when Stripe is connected in Sandbox, "Metronome automatically connects to your Stripe test mode so you can test your integration end-to-end with invoice creation and payment collection." | https://docs.metronome.com/integrations/invoice-integrations/stripe | 2026-06-12 | high |
| SDK languages | Official SDKs in 4 languages: Python ("pip install --pre metronome-sdk"), Node.js ("npm install @metronome/sdk"), Ruby ("gem install metronome-sdk"), Go (github.com/Metronome-Industries/metronome-go). Features: strong typing, pagination support, and "Automatic retry support by default retries each request upon failure up to three times." No Java SDK listed. | https://docs.metronome.com/api-reference/sdks | 2026-06-12 | high |
| API auth model | Bearer tokens created in the app (Connections > API tokens & webhooks); "You cannot view the full token again" after creation; "Metronome API tokens will retain the same permissions as the user that created them", and tokens CAN be scoped by "Access level (e.g., read-only)", "Environment (e.g., sandbox only)", and "Endpoint (e.g., only getCustomers)" — but scope adjustments require contacting your Metronome representative (not self-serve). SDKs read METRONOME_BEARER_TOKEN. | https://docs.metronome.com/api-reference/authentication | 2026-06-12 | high |
| Invoicing/Stripe relationship | Stripe COMPLETED its acquisition of Metronome on January 14, 2026 (the agreement was announced Dec 2, 2025 per trade press; the announcement date is not stated on this page). Patrick Collison: "We're looking forward to integrating these capabilities with the Stripe Billing platform." No financial terms disclosed in the announcement. Collison's quote also states Metronome's metering engine powers OpenAI, Anthropic, and NVIDIA. | https://stripe.com/newsroom/news/stripe-completes-metronome-acquisition | 2026-06-12 | high |
| Invoicing/Stripe relationship | Native Stripe invoicing integration predating the acquisition: Metronome automatically creates Stripe invoices when Metronome invoices finalize; supports "charge_automatically" and "send_invoice" collection modes; supports multiple Stripe accounts within a single Metronome environment for "complex enterprises". | https://docs.metronome.com/integrations/invoice-integrations/stripe | 2026-06-12 | high |

---

## 2. Orb

| Axis | Fact | Source | Accessed | Confidence |
|---|---|---|---|---|
| Event ingestion API | "By default, Orb limits the request size to 500 events per batch." Per-event idempotency via idempotency_key: "duplicates are never processed within the account grace period." Test mode ingest is "limited to 2000 events per minute and 10 requests per second"; production guidance: "Please give our team a heads up if you plan to continuously send over 10,000 events per minute." A separate high-volume offering "performs rollups and scales to orders of magnitude more events while still providing the same idempotency and real-time guarantees." | https://docs.withorb.com/events-and-metrics/event-ingestion | 2026-06-12 | high |
| Event ingestion API | Event grace period: events can be reported "up to 12 hours after the timestamp" with a configurable account-wide grace period; pending invoices remain subject to change for 12 hours after billing period end. Backfills: timeframe-based with optional full replacement (originals "marked as archived", still queryable but excluded from billing); single-event amendment via PUT by event ID can change anything "excluding its timestamp and associated customer ID"; events can be deprecated; "Amendments and backfills are always audit-safe" and Orb "never overwrites or permanently deletes ingested usage data". Caveat: backfilling before current billing periods is not recommended for credit-ledger customers since issued invoices won't reflect deduction changes. | https://docs.withorb.com/guides/events-and-metrics/reporting-errors | 2026-06-12 | high |
| Event ingestion API | Event schema constraints: idempotency_key, customer identifier, and ISO 8601 timestamp are required first-class fields; properties allow only primitives ("arrays and objects are not permitted. Numeric values must be between -9223372036854775808 and 9223372036854775807"); "idempotency key deduplication is guaranteed only during the grace period window." | https://docs.withorb.com/quickstart/ingest | 2026-06-12 | high |
| Event ingestion API | General API idempotency (non-ingest): Idempotency-Key header "strongly encouraged for all POST/PATCH requests"; "Users will be able to safely retry requests that include an Idempotency-Key within 48 hours. Keys will expire after 48 hours." Replayed responses carry "Idempotent-Replayed: true"; concurrent retry or key reuse with a different payload returns 409; 409s are not cached for idempotency. | https://docs.withorb.com/api-reference/idempotency | 2026-06-12 | high |
| Scale claims | Pricing page publishes "250,000+ events/second" ingestion and "Continuously send billions of events/day with hosted streaming aggregation", plus "Our ingestion infrastructure comes with idempotency guarantees to ensure your data is complete and correct." The standard ingestion API is separately described in docs as "designed to scale to tens of millions of events per day." | https://www.withorb.com/pricing; standard-API quote from https://docs.withorb.com/events-and-metrics/event-ingestion | 2026-06-12 | high |
| Scale claims | Imply (Druid) partner case study quotes Orb as "able to scale and handle event volume that doubles or triples every few months" and "able to support customers with hundreds of thousands to millions of events per second" — partner-published, not Orb first-party. | https://imply.io/customer/orb/ | 2026-06-12 | medium |
| Deployment model | SaaS-only per the security page: "Orb hosts its application servers under a software as a service model, deploying changes continually"; "Orb uses Amazon Web Services as its cloud infrastructure provider, and uses a virtual private cloud (VPC) for resource isolation." No self-host or BYOC option is mentioned anywhere on the page. | https://www.withorb.com/security | 2026-06-12 | high |
| Compliance & trust | "As part of Orb's SOC-2 Type II compliance program, Orb submits to a third party SOC-2 audit annually" (report on request); independent third-party penetration testing; all production data encrypted at rest (S3, volumes, datastores) and TLS in transit; a "full data processing addendum" is available on request via security@withorb.com; Orb maintains a subprocessor list. | https://www.withorb.com/security | 2026-06-12 | high |
| Compliance & trust | SafeBase trust center (security.withorb.com) lists certifications SOC 2 Type 2 and SOC 1 Type 2, with downloadable Pentest Report, SOC 1 Report, and SOC 2 Report. GDPR/CCPA/ISO 27001 are NOT listed there. | https://security.withorb.com/ | 2026-06-12 | high |
| Compliance & trust | Public status page (status.withorb.com) publishes 90-day uptime per component: API 99.96%, Reads 99.97%, Writes 99.94%, Analytics 99.97%, Ingest 99.99%, Real-time alerting 100.0%, Webhooks 99.96%, Invoicing 100.0%. Recent incident: "Delayed webhooks" June 7, 2026, resolved ~1.5h after onset. | https://status.withorb.com | 2026-06-12 | high |
| Compliance & trust | Enterprise pricing tier advertises "Enterprise-grade SLAs for accuracy, uptime, and support—built for mission-critical billing", with SLA specifics "In MSA" (i.e., contractual, not publicly numeric). | https://www.withorb.com/pricing | 2026-06-12 | high |
| Sandbox/test environments | Orb has a distinct Test Mode: API keys for testing are generated while "in Test Mode" via "Orb webapp > Organization Settings > Create new API key"; test mode has deliberately lower ingest limits "to ensure test mode workloads do not affect live mode availability or performance." | https://docs.withorb.com/quickstart/ingest | 2026-06-12 | high |
| SDK languages | Official SDKs in 6 languages: "Python, TypeScript, Go, Java, Kotlin, and Ruby" (packages: orb-billing on pip/npm/gem, github.com/orbcorp/orb-go, Maven for Java/Kotlin). "Each SDK includes built-in support for idempotency, pagination, retries, and more." OpenAPI spec published at https://api.withorb.com/spec.json for generating clients in other languages. | https://docs.withorb.com/essentials/sdk | 2026-06-12 | high |
| API auth model | API auth is "Authorization: Bearer \<TOKEN\>" against base URL https://api.withorb.com/v1/; keys are created self-serve in the webapp (Organization Settings), with test-mode keys created while in Test Mode. No fine-grained key scopes (read-only, per-endpoint) are documented in the pages fetched. | https://docs.withorb.com/api-reference | 2026-06-12 | high |
| Invoicing/Stripe relationship | Orb is independent of Stripe but offers full invoice sync to Stripe Invoicing: zero-net-terms invoices get collection_behavior "charge_automatically", non-zero net terms get "send_invoice"; "Orb's auto-collection setting does not control how Stripe collects payment"; all Orb items must be mapped to Stripe products or "invoices will fail to issue"; Orb sets Stripe auto_advance=true and writes cross-reference metadata (orb_invoice_id, subscription/customer IDs). | https://docs.withorb.com/integrations-and-exports/stripe | 2026-06-12 | high |

---

## 3. Lago

| Axis | Fact | Source | Accessed | Confidence |
|---|---|---|---|---|
| Self-host architecture (license) | Lago is distributed under the AGPLv3 license; the repo (~9.8k stars) is structured as three primary components: /api (Rails backend), /front (UI), and /events-processor (event-handling workers), orchestrated via Docker Compose. | https://github.com/getlago/lago | 2026-06-12 | high |
| Self-host architecture (default stack) | The default docker-compose.yml (images pinned at v1.48.1) defines: db = getlago/postgres-partman:15.0-alpine (Postgres with partman), redis:7-alpine, migrate/api/api-worker/api-clock (all getlago/api), front, and pdf = getlago/lago-gotenberg:7.8.2. NO ClickHouse and NO Kafka are in the default compose. Commented-out optional dedicated workers exist for events, PDFs, billing, clock, webhooks, analytics, and an AI agent. | https://github.com/getlago/lago/blob/main/docker-compose.yml | 2026-06-12 | high |
| Self-host architecture (docs view) | Lago's self-hosted Docker docs describe seven main containers: front, api, api_worker (async worker), api_clock (clock worker), db (PostgreSQL), redis ("used as a queuing system for asynchronous tasks"), and pdf ("PDF generation powered by Gotenberg"). The bundled db service "is intended for local trials"; production should bring managed Postgres/Redis. | https://getlago.com/docs/guide/lago-self-hosted/docker | 2026-06-12 | high |
| Self-host architecture (ClickHouse at scale) | ClickHouse + Kafka are Lago's at-scale events engine, not the baseline: "we kept Postgres" for transactional data; "Our ClickHouse instance ingests raw billable events"; "raw_events_queue is where events are initially streamed to via Apache Kafka". The wiki frames OLTP+OLAP as something to adopt "when the moment arrives", i.e. for high event volume, not preemptively. | https://github.com/getlago/lago/wiki/Using-Clickhouse-to-scale-an-events-engine | 2026-06-12 | high |
| Ingestion API (batch) | POST /events/batch accepts "up to 100 events" per request; if any event in the batch fails structural validation the entire batch is rejected; events are processed asynchronously (lago_customer_id is null in the response). Errors: 400/401/403/422. | https://getlago.com/docs/api-reference/events/batch; whole-batch rejection stated at https://getlago.com/docs/guide/events/ingesting-usage ("If any event within the batch does not meet the structural requirements, the entire batch will be rejected.") | 2026-06-12 | high |
| Ingestion API (idempotency) | Idempotency is keyed on transaction_id: "Same transaction_id + external_subscription_id arrives twice → only the first is billed", enforced across delivery channels (REST, Kafka, S3). Caveat from the API reference: on the "new Clickhouse-based event pipeline", uniqueness is transaction_id + timestamp, and an identical pair OVERWRITES the previous event rather than being rejected. | https://getlago.com/docs/guide/events/ingesting-usage | 2026-06-12 | high |
| Ingestion API (rate limits) | Default rate limit on POST /events and POST /events/batch is 500 requests/sec per organization; 429 responses include x-ratelimit-remaining and x-ratelimit-reset headers. "Kafka, Kinesis, and S3 connectors are not subject to REST API rate limits." | https://getlago.com/docs/guide/events/ingesting-usage | 2026-06-12 | high |
| Ingestion API (late events / grace) | Events are assigned to billing periods by their timestamp, not arrival time; late events land in the correct historical period, but if the invoice is already finalized they roll into the next billing cycle. The invoice "grace period" feature keeps invoices in draft for N days so usage events "with a valid timestamp within the billing period" can still be added before finalization — and this grace period is explicitly a premium-only feature. | https://getlago.com/docs/guide/invoicing/invoicing-settings/grace-period | 2026-06-12 | high |
| Premium vs OSS split | Lago's pricing FAQ: "Lago offers a forever-free open source solution offering access to fundamental billing features" plus paid plans with premium features; deployment FAQ distinguishes "Self-hosting the open-source product — Free" from "Self-hosting the premium product" and Lago Cloud (US or EU hosting, application process); premium access goes through sales. | https://getlago.com/docs/faq/pricing | 2026-06-12 | high |
| Premium vs OSS split (paywalled features) | Verified premium-gated items from individual docs pages and the pricing page: invoice grace period / draft-invoice review is premium-only; Okta SSO is a "PREMIUM ADD-ON … available on demand only" (Google SSO is standard); the pricing page lists Business/Enterprise tiers with paid add-ons for tax integrations, automatic dunning, CRM/CPQ/accounting integrations, and "Lago AI" on-demand; Business tier lists data pipeline integration, lifetime usage calculation, and invoice preview endpoint. | https://www.getlago.com/pricing | 2026-06-12 | high |
| Compliance/trust | "Lago has achieved SOC 2 Type 2 compliance for its fully hosted version"; the self-hosted version is described as "compliant by default, as you own the data and the infrastructure"; full report by request via hello@getlago.com. The security page adds regular third-party penetration tests, SSO/RBAC/audit logs, "99.9% historical uptime" with enterprise SLAs, and a trust center at security.getlago.com. | https://getlago.com/docs/guide/security/soc (SOC 2 claims); https://www.getlago.com/security (pentests, SSO/RBAC/audit logs, 99.9% uptime, trust center link) | 2026-06-12 | high |
| SDKs | Official client libraries listed in the API reference intro: Python, Ruby, Javascript, Go (plus raw curl). API base URLs: https://api.getlago.com (US), https://api.eu.getlago.com (EU), self-hosted configurable per SDK; bearer-token auth. | https://getlago.com/docs/api-reference/intro | 2026-06-12 | high |
| Sandbox/test mode | Lago has NO dedicated test mode or sandbox. The docs recommend workarounds: separate staging/production accounts, or mixing Lago Cloud and Lago Open Source — "the above workarounds will require you to replicate the same setup in both environments." Roadmap statement: "In the future, you will be able to get access to a test environment and a production environment with the same Lago account." | https://getlago.com/docs/guide/integration-testing | 2026-06-12 | high |

---

## 4. OpenMeter (short)

| Axis | Fact | Source | Accessed | Confidence |
|---|---|---|---|---|
| Positioning + stack | README one-liner: "The open-source metering and billing platform for AI, agentic and DevTool monetization." License: Apache 2.0. Stack: PostgreSQL (Ent ORM) for billing/subscriptions, ClickHouse for real-time usage aggregation, Kafka for event streaming. | https://github.com/openmeterio/openmeter | 2026-06-12 | high |
| Ingestion + entitlements | Ingestion accepts events in CloudEvents format (specversion/type/id/time/source/subject/data). Entitlements are first-class: "enforce usage quotas per feature with real-time balance tracking, boolean feature flags, and grace periods." | https://github.com/openmeterio/openmeter | 2026-06-12 | high |

---

## 5. Amberflo (short)

| Axis | Fact | Source | Accessed | Confidence |
|---|---|---|---|---|
| Positioning | Homepage headline: "AI Monetization Infrastructure. Metering, Cost Attribution, and Billing." Product set now spans metering (tokens/API calls/events at high cardinality), cost tracking with Cost Guards and Budgets, billing/monetization (credits, usage tiers, outcome-based pricing), an AI gateway claiming 1,500+ LLM models, and revenue recognition. | https://www.amberflo.io/ | 2026-06-12 | high |
| Ingestion (idempotency/dedup) | Amberflo claims an "idempotent metering service with data deduplication" since day 1, with configurable dedupe where "any dimension can be used as the filter for deduplication" (e.g. a document-id so no document is billed twice); SDKs batch and flush events in the background. (Vendor blog claim; the deeper docs page on duplicate handling was unreachable.) | https://www.amberflo.io/blog/leverage-configurable-event-deduplication-logic-in-amberflo | 2026-06-12 | medium |

---

## 6. Stripe native UBB (short)

| Axis | Fact | Source | Accessed | Confidence |
|---|---|---|---|---|
| Current docs posture | Stripe's usage-based billing landing page now frames TWO approaches and recommends Metronome for new integrations, describing "basic usage-based billing, built on the Billing Meters API" as "a lower-level primitive that remains fully supported for existing integrations"; Metronome is described as handling real-time metering, tiered/dimensional/composite pricing, prepaid credits, enterprise contracts, and automated invoicing. | https://docs.stripe.com/billing/subscriptions/usage-based | 2026-06-12 | high |
| Meters: rate limits + idempotency + grace | v1 /v1/billing/meter_events: 1,000 calls/sec per Stripe account in live mode (sandbox calls count toward the sandbox global rate limit of 25 req/s per https://docs.stripe.com/rate-limits; one concurrent call per customer per meter). v2 high-throughput meter event stream: up to 10,000 events/sec standard, 200,000/sec via sales — live mode ONLY. Idempotency via the `identifier` field (auto-generated if omitted), with uniqueness enforced "within a rolling period of at least 24 hours" (https://docs.stripe.com/api/billing/meter-event/create). Timestamps: within the past 35 calendar days, max 5 minutes in the future. Dimension cardinality caps: 10,000 unique combinations per meter per hour and 100 per customer per meter (error meter_event_dimension_count_too_high). | https://docs.stripe.com/billing/subscriptions/usage-based/recording-usage-api | 2026-06-12 | high |
| Credits/grants | Credit Grants support prepayment and promotional billing credits with states pending/granted/depleted/expired/voided; credits apply ONLY to subscription items on metered prices reported through Meters (not licensed prices, one-off invoices, or legacy usage records); expiry only if expires_at is set; multi-grant application order = priority number, then earliest expires_at, then promotional category first, then earliest effective_at, then earliest created. | https://docs.stripe.com/billing/subscriptions/usage-based/billing-credits | 2026-06-12 | high |
| Rate cards | Stripe rate cards are in private preview: one rate card holds many rates (each rate = billable item + meter + pricing model); rate cards are versioned so new customers can get new rates while existing customers keep older ones; they use /v2 API endpoints (e.g. rate card subscriptions) and "You can't use test mode with /v2 APIs like Rate Cards"; guidance says use rate cards only for pure usage-based pricing without discounts or trials. (Sourced via search-indexed content of this docs URL — the page itself returned 404 to direct fetch, hence medium confidence.) | https://docs.stripe.com/billing/subscriptions/usage-based/rate-cards?dashboard-or-api=api | 2026-06-12 | medium |
| Token billing for AI | Stripe "Billing for LLM tokens" is in private preview (access via token-billing-team@stripe.com): the Stripe AI Gateway proxies LLM requests ("Routes the request to the appropriate provider (OpenAI, Anthropic, or Google)… Records token usage for billing automatically"); tokens are metered per customer segmented by model and token type (input, output, cached); "Set your markup percentage in the Dashboard and Stripe configures all the underlying billing resources for you, including prices, meters, and rate configuration"; Stripe syncs provider token prices and can auto-apply new model prices to all customers. | https://docs.stripe.com/billing/token-billing | 2026-06-12 | high |
| Advanced UBB framing | The "Advanced usage-based billing" docs describe: dimension-based charging with "dozens to hundreds of prices per meter", "real-time credit burndown and automate credit issuance", credit burndown with automatic top-ups, and flat-fee-plus-overage models — and the page directs implementation to Metronome rather than documenting it natively. | https://docs.stripe.com/billing/subscriptions/usage-based/advanced/compare?locale=en-GB | 2026-06-12 | high |

---

## 7. Could not verify — do not assert

The following items were searched for on 2026-06-12 and could **not** be verified from any first-party page actually fetched. They must not be asserted as fact anywhere in this review. If one of these is load-bearing for an argument, the argument must be reframed as conditional or dropped.

### Metronome

- Any published NUMERIC API rate limits (requests/sec or events/sec hard caps) — docs only document 429 + exponential-backoff behavior; the 100k events/sec figure is a capacity claim, not a rate limit.
- GDPR compliance status or DPA availability — not stated on metronome.com/company/security, and trust.metronome.com content did not render in fetch; the ISO 27001/PCI DSS mentions on the security page refer to Metronome's CLOUD PROVIDERS, not Metronome itself.
- Any public uptime percentage or public SLA number — status.metronome.com shows no uptime %; "exceeds SLAs" appears only in a Confluent case study without numbers.
- Self-hosted / BYOC / single-tenant deployment option — no first-party page describing deployment options was found; the claim that Metronome lacks on-prem and lacks HIPAA/FedRAMP appears only in third-party comparison blogs.
- The widely-cited "~$1 billion" acquisition price — reported by Upstarts Media and repeated in trade press, but explicitly NOT disclosed in Stripe's or Metronome's own announcements.
- "30 billion events per month / 100K invoices per minute" figures — surfaced only in a search summary citing a third-party Medium article (June 2024); the "How We Use Metronome at Metronome" blog post itself contains no scale numbers.

### Orb

- GDPR or CCPA compliance claims and ISO 27001 — not listed on withorb.com/security nor on the SafeBase trust center; only SOC 1 Type 2, SOC 2 Type 2, and pentest report are listed (DPA available on request is sourced, but no GDPR certification claim).
- The SOC 2 trust-services-criteria scope (Security/Availability/Confidentiality) — appeared in a search snippet of an Orb blog post but was not present on the pages actually fetched.
- A default DURATION for the configurable account-wide ingestion grace period beyond the documented "up to 12 hours after the timestamp" reporting window — no single universal default value found on fetched pages.
- Production (live-mode) hard numeric ingest rate limit — only test-mode limits (2,000 events/min, 10 req/s) and a 10,000 events/min advisory threshold are documented.
- Any maximum backfill window/duration (e.g. max days per backfill operation) — the backfill API reference page could not be fetched (404 on tried URLs) and the guide states no limit.
- Self-hosted or BYOC deployment option — nothing official found; security page describes SaaS-on-AWS only (absence documented, but no explicit "we do not offer self-hosting" statement).

### Lago

- A single canonical public table of ALL premium-vs-OSS features. The pricing FAQ and pricing page defer to sales; premium gating is only discoverable per-docs-page (grace period and Okta SSO confirmed; dunning/multi-entity/RBAC/revenue-analytics as premium appeared only in search snippets, not on pages fetchable directly).
- Any free-plan caps (events/month, customers, invoices) — commonly claimed in third-party comparisons, but no caps appear on the pricing or FAQ pages fetched.
- GDPR or ISO 27001 certification — the security page and SOC doc mention only SOC 2 Type 2 (cloud version) and third-party pen tests; no GDPR/ISO certification statement found.
- Event payload size limits — not documented on any ingestion page fetched.
- Whether the ClickHouse/Kafka event pipeline is available in OSS self-host vs cloud/premium-only — the default OSS docker-compose has no ClickHouse/Kafka and the docs never state the gating; the API reference only says "if the Lago organization is configured to use the new Clickhouse-based event pipeline".
- Official Java/PHP/C#/Rust SDKs — the API reference intro lists only Python, Ruby, Javascript, Go.
- A numeric grace-period window for late event ingestion (e.g. "X hours after period end") — Lago's model is timestamp-based assignment plus the premium draft-invoice grace period in days; no fixed late-event ingestion window is documented.

### Stripe

- Exact component model and setup flow for rate cards (billable items, rate card subscriptions API shapes) — all rate-card docs URLs returned 404 to direct fetch; details above come from search-indexed snippets of docs.stripe.com only.
- Any corporate acquisition/ownership relationship with Metronome *as stated in the docs pages* — docs.stripe.com recommends Metronome for new usage-based integrations, but the docs pages fetched state no corporate relationship. (The acquisition itself IS separately sourced from the Stripe newsroom announcement in the Metronome section above; do not cite the docs pages for it.)

### OpenMeter

- Batch ingestion size limits and idempotency/dedup window — the GitHub README does not specify them; OpenMeter cloud docs were not fetched.

### Amberflo

- Default dedupe key combination and dedupe time window — the referenced docs page (docs.amberflo.io/docs/duplicate-handling) returned 404; only the vendor blog's configurable-dimension claim was sourceable.
- SOC 2 / compliance certifications and self-hosting options — not sourced from any page fetched.

### Cross-vendor

- Public per-endpoint rate-limit tables — neither Metronome nor Orb publishes one on pages reachable on 2026-06-12.
