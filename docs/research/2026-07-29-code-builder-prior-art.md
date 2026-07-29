# Prior Art — Developer Integration-Code Builders

**Date:** 2026-07-29
**Status:** research findings — frozen history
**Ticket:** [#144](https://github.com/ashcochrane/ubb/issues/144), part of map
[#137](https://github.com/ashcochrane/ubb/issues/137) (*Pricing & metering re-model, and the Code
Builder built on it*)
**Sources accessed:** 2026-07-29 throughout, unless a different date is stated inline
**Redacted:** 2026-09-22 — four occurrences of a Stripe test secret key, captured from the payload Stripe's documentation serves a logged-out visitor (`"is_merchant_key": false`), are replaced with `sk_test_<redacted>` so that GitHub push protection admits this file. No finding depends on the key's characters; nothing else is changed.

> This is external evidence gathered at a point in time — not a design, and not current truth about
> UBB. Read it for "what does everyone else do, and what did we conclude from that". Do not edit it
> as the design evolves; the design belongs in the plan or ADR that cites this.

---

## What this had to answer

We are designing an in-console **Code Builder**: a tenant configures their integration in the UBB
console and receives code showing exactly what to add to their own application. Targets are the
**Python SDK and raw HTTP/curl** (map #137, constraint 6).

Our integration shape is a **stateful lifecycle with four separate call sites**, which the developer
must place in four different parts of their own application:

1. **start work** — `POST /api/v1/billing/pre-check` with `start_task=true` → returns `task_id`
2. **report usage** — `POST /api/v1/metering/usage`, carrying that `task_id`, N times
3. **handle a stop signal** — *not a call*: `stop` / `stop_reason` / `stop_scope` ride the response
   of (2), plus webhooks for idle/sibling workers
4. **complete work** — `POST /api/v1/metering/tasks/{task_id}/close`

(Grounded in `docs/spend-control-integration.md` and `openapi/v1.json` at commit `27efac5`.)

Six questions, asked of every vendor:

| | Question |
|---|---|
| **Q1** | Does it ship an in-console code builder / configurator / quickstart generator? What does the developer *choose*, what does the tool *emit*? |
| **Q2** | How are platform-known values (keys, ids, configured resources) distinguished from developer-supplied ones — **and does that distinction survive copy-paste into a plain editor, where all UI styling is lost?** |
| **Q3** | How much explanation ships with the code — bare snippet, annotated snippet, or guided walkthrough? Which shows up where the integration is genuinely stateful? |
| **Q4** | Does anyone *generate* code for a multi-step lifecycle (open → report → close)? How is error and retry handling presented? |
| **Q5** | How is generated code kept correct as the API changes — OpenAPI, live project state, hand-maintained templates? |
| **Q6** | Is there a "verify your integration" step, and what does it *actually* do? |

## Method, and how to read the evidence

Investigated against **primary sources only** — the live products, their own first-party
documentation, and their public source repositories. No blog posts, no listicles, no third-party
tutorials.

Every claim below carries a source and a confidence rating. Because much of the interesting surface
is **behind a login we could not reach**, the evidence grade matters as much as the confidence:

| Grade | Meaning |
|---|---|
| **observed** | We fetched it and read the literal bytes (raw HTML, RSC payload, shipped JS bundle) |
| **source** | Read from the vendor's own public source repository |
| **documented** | The vendor states this in its own docs; we did not witness the behaviour |
| **inferred** | Our reasoning from the above. Called out explicitly every time |

> **Where a surface was login-gated, this document says so plainly rather than guessing.** The most
> commonly gated thing — a signed-in dashboard rendering *your* real keys into a snippet — is
> described from vendor documentation and, for Clerk and Supabase, from the actual shipped/open
> source that performs the substitution. That is one step removed from observation, and is flagged
> each time.

---

## Headline findings

1. **Code builders exist in our exact market — four of them — and every one emits a single call
   site.** Lago, Flexprice and Helicone are verifiable in **open source**; m3ter's is documented but
   gated. **We went in expecting "nobody does this" and that was wrong.** What is *actually* missing
   is not the builder — it is the **lifecycle**. §1.8

2. **Nothing, anywhere, in either half of this survey, generates multi-call-site lifecycle code.**
   Console code generation is mature for *provisioning and configuration* artifacts (AWS
   Console-to-Code, GCP "Equivalent code", Firebase config, LiveKit `.env.local`) and essentially
   absent for **the developer's own runtime call sites**. §1.8, §2.7

3. **Two open-source billing consoles independently converged on the same three-class placeholder
   scheme** — and it is the strongest design signal in the report. Lago and Flexprice both ship the
   literal token `__MUST_BE_DEFINED__`, paired with `__SCREAMING_SNAKE__` runtime slots, over
   interpolated tenant config. **Configured / not-yet-configured / runtime**, all three encoded in
   text. §1.8

4. **Stripe encodes provenance in a two-class bracket vocabulary, in the text itself** —
   `<<YOUR_SECRET_KEY>>` (yours; substituted with a working key) vs `{{CUSTOMER_ID}}` (pick one;
   stays literal and fails loudly). Backed by a context object carrying `"is_merchant_key":false`.
   **The only vendor to distinguish the two classes typographically.** §1.1

5. **The best answer to the copy-paste problem is architectural, not typographic.** Supabase's
   Connect sheet emits **two files** — a `.env` tab with real values, and application code with
   *zero* secrets and *zero* placeholders that reads config by env-var name. **Nothing needs
   substituting, so nothing can fail to survive the clipboard.** Twilio reaches the same place from
   the opposite direction (`os.environ[...]` everywhere). §1.5, §1.2

5a. **The generation model that fits us is "generate from the tenant's own configured state" — and it
   has two mature precedents.** Supabase parameterises hand-written templates with a schema
   introspected live from your database, making table/column drift **impossible by construction**;
   Segment's **Typewriter** compiles your Tracking Plan into a typed client and **fails your CI build
   when instrumentation and plan diverge**. Both are the same idea as our declared registries under
   ADR-0005. §1.5, §1.6

6. **Guidance dies at the clipboard — verified three times over.** Lago strips its own comments on
   copy (`ignoreComment: true`); Helicone copies the diff-free string; AWS marks replaceable values in
   **CSS only**. Three products, three mechanisms, one outcome: **only the tokens survive.** Anything
   load-bearing must be a token or a comment that is actually in the copied text. §1.8

7. **Placeholder conventions decay, and a convention with no legend is only half a solution.** Auth0
   has a real latent rule — `{yourClientId}` (platform fills) vs `YOUR_API_IDENTIFIER` (you fill) —
   documented **nowhere**, already broken by its own rewrite, and visibly leaking raw
   `${account.clientId}` markers on a live page today. Supabase ships **four incompatible
   conventions**. §1.4, §1.5

8. **The worst failure mode is not a bad placeholder — it is no placeholder.** Paddle ships a
   concrete `token: "live_7d279f61a3499fed…"` 28 times on one page with zero placeholder syntax;
   Amberflo's sample has **no API key field at all**. Copy-paste-clean and silently wrong. §1.8

9. **Retry, backoff and idempotency are absent from generated code essentially everywhere.** Both
   Stripe and Twilio push dedup **into a domain field** (`identifier`) rather than generated retry
   code. The best guidance in the cohort is Metronome's *prose*: *"Always retry a failed call to
   /ingest until you receive a 200"*, and on 4xx *"put the event aside in a dead letter queue."* §1.8

10. **Temporal independently arrived at UBB's stop-signal design.** Its async-activity sample carries
    the comment *"Heartbeat is how cancellation is delivered from the server"* — **the stop rides the
    report channel**, exactly as our `stop` rides the `record_usage` ack. Hand-written, one runnable
    file, not generated. §1.8

11. **Stripe has real step-to-step dataflow machinery — and does not use it for humans.**
    `${node.prerequisites.createProduct.createProduct:id}` binds step N's output into step M's input,
    but only in the `.md`/runnable layer. **The copyable human text still says `{{METER_ID}}` plus
    "look it up in the Dashboard."** §1.1

12. **A sibling spec had to be invented to express what we need.** OpenAPI cannot say "then";
    `x-codeSamples` attaches to exactly one Operation Object. The OpenAPI Initiative's **Arazzo
    Specification** exists to *"express sequences of calls and articulate the dependencies between
    them"*, citing *"code and SDK generation driven by functional use cases"*. §2.7

13. **The verify step worth copying is Auth0's "Try Connection"** — it runs the real flow *from the
    platform's side with the customer's app entirely out of the loop*, which **partitions the failure
    space** rather than merely reporting a result. §1.4

14. **Exactly one vendor ships "post an event, see what it costs": Lago's `POST /events/estimate_fees`**
    returns computed fees, taxes and totals **without persisting the event**. For a metering platform
    this is the highest-value verify surface that exists, and almost nobody has it. §1.8

15. **Nobody puts the verify surface beside the generated code.** The snippet and the proof it worked
    live on different screens — at Chargebee, Paddle, Moesif, m3ter, Auth0 and Supabase alike. The
    log tail, universally the one thing that could confirm "my first real event landed", is
    universally documented as an *ops* tool. §1.8, §1.4, §1.5

---

## 1. Vendor by vendor

Ordered so the two richest sources come first. **§1.8 is our own market** and is where the conclusion
changed.

### 1.1 Stripe

The richest single source in this research, and the closest thing to a real Code Builder.

| Surface | What it is |
|---|---|
| **Docs quickstarts driven by an `IntegrationBuilder` component** (`docs.stripe.com/payments/quickstart`) | Multi-axis configurator emitting a runnable multi-file scaffold |
| **API reference, 9 language tabs** (`docs.stripe.com/api/*`) | Single call + CLI equivalent + JSON response |
| **A dual rendering of every page** — append `.md` to any docs URL | Clean Markdown for LLM/agent consumption. **The two renderings substitute placeholders differently** |
| **Usage-based billing implementation guide** | Seven chained steps — the closest structural analogue to our shape |
| **Stripe Shell / Workbench** | Run CLI commands inside the docs site, sandbox-only |
| **Runnable snippets** | Login-gated; flags observed, UI not |

Raw HTML of the quickstart contains Markdoc component nodes named `IntegrationBuilder`,
`IntegrationBuilderDemo`, `AppearancePicker`, plus 181 `Step`, 6 `StepSection`, 40 `File`, 58
`Command`, 14 `TabGroup`/34 `Tab`, 14 `KeyToken`. *(high — observed)*

The API reference carries feature flags with these literal names:
`"docs_enable_runnable_codegen_snippets":true`, `"docs_disable_runnable_snippets":false`,
`"docs_disable_runnable_snippets_prerequisites":false`. **The flags were observed; the UI was not** —
no Run button renders in logged-out HTML. *(high for the flags; medium that a logged-in Run
affordance exists)*

Note in passing: the usage-based billing parent page now says **Stripe recommends Metronome for new
usage-based integrations.** *(high)*

#### Q1 — chooses / emits

- **Quickstart (`IntegrationBuilder`)** — choose server language (Node/Ruby/Python/PHP/Java/Go/.NET),
  client framework (React/vanilla/Next.js), and appearance. Emits **a multi-file scaffold across
  numbered steps**: `File` nodes, `Command` nodes (`npm start`, `python3 -m flask run`), and a `.env`.
  **Not a snippet — a runnable project.**
- **API reference** — choose resource + language tab (+ a scenario where the endpoint has variants).
  Emits one call, a **Stripe CLI equivalent** (carried as a `cliCommand` attribute), and a JSON
  response.
- **Implementation guide** — emits **two parallel tracks per step**: a Dashboard click-path *and* an
  API `curl`. No language tabs at all (0 Python blocks on the page).

#### Q2 — known vs supplied, and copy-paste survival

> **The strongest finding in the whole research. Stripe encodes provenance in the text itself, via a
> two-tier bracket vocabulary, resolved against an account-context object.**

**The context object.** Logged-out page state, literal:

```json
"merchant":{"apiVersion":"2026-06-24.dahlia","isLoggedIn":false,"isSandbox":false,
  "currency":"usd","defaultCurrency":"usd","country":"US"}
"keys":{"publishable":"pk_test_qblFNYngBkEdjEZ16jxxoWSM",
        "secret":"sk_test_<redacted>","is_merchant_key":false}
```

**`"is_merchant_key":false` is the crux** — the docs know these are *shared sample* keys, not yours.
Every `{{TOKEN}}` in the code is a binding into this object. *(high)*

**Two bracket syntaxes = two provenance classes** (sampled across 8 API-reference pages):

| Literal token | Class | Resolution |
|---|---|---|
| `<<YOUR_SECRET_KEY>>`, `<<YOUR_PUBLISHABLE_KEY>>` | **your credential** | substituted with a real key |
| `{{CUSTOMER_ID}}` `{{PRICE_ID}}` `{{METER_ID}}` `{{CHARGE_ID}}` | **resource you must pick** | stays literal |
| `{{CURRENCY}}`, `{{APPEARANCE}}` | account/config-derived | from context object |

**Copy-paste survival — and the two renderings diverge.**

*HTML (what a human copies)* — the key is substituted with a **real, working shared test key**.
Display is truncated but the copy payload is not; the DOM carries two sibling spans plus an explicit
`"__md_code_plaintext":"sk_test_<redacted>"`. The full Python tab payload is literally:

```python
import stripe
stripe.api_key = "sk_test_<redacted>"

meter_event = stripe.billing.MeterEvent.create(
  event_name="ai_search_api",
  payload={"value": "25", "stripe_customer_id": "{{CUSTOMER_ID}}"},
  identifier="identifier_123",
)
```

**So the distinction does NOT live in CSS.** The credential becomes a value that *actually works*
(nothing to lose — it is a shared sandbox key), and the resource stays an obviously-invalid
`{{CUSTOMER_ID}}` that **fails loudly**. Both survive copy-paste. *(high)*

*`.md` (agent rendering)* — same code, but `stripe.api_key = '<<YOUR_SECRET_KEY>>'`. **The
placeholder is restored for machine readers.** *(high)*

**Meaning is also carried by inline comments that survive copy-paste** — this ships *inside* the code
block:

```python
# This is a public sample test API key.
# Don't submit any personally identifiable information in requests made with this key.
# Sign in to see your own test API key embedded in code samples.
# Don't put any keys in code. See https://docs.stripe.com/keys-best-practices.
```

**Separate config block for framework flavours** — the Next.js path emits a `.env` instead of
inlining:

```bash
# https://dashboard.stripe.com/apikeys
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=<<YOUR_PUBLISHABLE_KEY>>
STRIPE_SECRET_KEY=<<YOUR_SECRET_KEY>>
# Set this environment variable to support webhooks — https://stripe.com/docs/webhooks#verify-events
# STRIPE_WEBHOOK_SECRET=whsec_12345
```

> **A defect worth copying carefully.** `{{CURRENCY}}` leaks **unsubstituted into the `.md`** (20+
> occurrences), so an agent reading the Markdown gets `currency: "{{CURRENCY}}"` — a token that looks
> like a placeholder but is actually account-derived and silently invalid. **Substituting for humans
> but not for agents is a real trap.** *(high)*

**Not verified:** the logged-in rendering. Docs state *"Sign in to see your own test API key embedded
in code samples"* — **documented, not observed.**

#### Q3 — explanation density

Three distinct tiers, and **density tracks statefulness**. *(high)*

- **API reference** — bare snippet. No prose between blocks, no comments beyond the key block.
- **Implementation guide (7-step)** — prose per step, dual Dashboard/API tracks, but curl-only and no
  error handling.
- **Quickstart (`IntegrationBuilder`)** — 181 `Step` nodes, prose between blocks, run commands,
  file-by-file scaffold. **This is the only tier where inline explanatory comments appear**
  (`amount: item.amount, # Amount in cents`).
- **An agent-only tier exists.** A `PlaintextOnly` node renders *only* in the `.md`, literally:
  *"Coding agents should install the Stripe CLI (`npm i -g @stripe/cli`) and run the command `stripe
  sandbox create --help` to provision an anonymous Stripe sandbox with working API keys. No account
  registration required."* **Stripe writes different instructions for humans and agents on the same
  page.** *(high)*

#### Q4 — multi-step lifecycle, error and retry

> **Stripe does generate multi-step lifecycle setup, with machine-readable dataflow between steps.
> This is the only instance of it found anywhere in this research.**

API-reference pages auto-emit a `## Prerequisites` block. Literal, from `/api/subscriptions/create.md`:

```
Before you can run the following code snippet, you need to call these APIs
with the provided parameters to set up the prerequisite API object(s).

1. Create a payment method
POST /v1/payment_methods {"type":"card","card":{"token":"tok_visa"}}
2. Create a customer and attach the payment method
POST /v1/customers {"name":"Jenny Rosen","email":"jennyrosen@example.com",
  "payment_method":"${node.prerequisites.createPaymentMethod.createPaymentMethod:id}",
  ...}
3. Create a product
POST /v1/products {"name":"Gold Plan"}
4. Create a price
POST /v1/prices {"product":"${node.prerequisites.createProduct.createProduct:id}",...}
```

`${node.prerequisites.<step>.<step>:id}` is a **declarative binding of step N's output field into
step M's input** — a dependency *graph*, not a linear script. It is emitted **only where dependencies
exist** (`/api/prices/create.md` has none, because its example uses inline `product_data`). This is
the machinery behind the `..._runnable_snippets_prerequisites` flag. *(high)*

> **But two layers coexist, and the human one is the weaker.** The Prerequisites graph is for the
> *machine* (the login-gated runnable feature). The human snippet on the same page still says
> `-d customer={{CUSTOMER_ID}} -d "items[0][price]={{PRICE_ID}}"`. **The copy-pasteable text does NOT
> auto-thread IDs.** In the 7-step implementation guide, chaining is `{{METER_ID}}` plus prose: *"You
> can locate your meter ID on the meter details page"*, *"go to the product details page and click
> the overflow menu (⋯) under Pricing. Select Copy price ID."* *(high)*

**Error and retry:**

- API reference: **none**. Implementation guide: **none**.
- Quickstart: **yes, idiomatic and per-language** — 28 occurrences, typed:
  `except stripe.error.CardError as e`, `rescue Stripe::CardError => e`,
  `catch (StripeException e)` with `switch (e.StripeError.ErrorType)`.
- **Idempotency keys: zero mentions in the quickstart.** *(high)* Dedup is pushed **into the domain
  object** instead — Meter Events take an `identifier`, and *"Stripe enforces uniqueness within a
  rolling period of at least 24 hours… primarily addresses issues arising from accidental retries."*
- **No generated code branches on a stop/limit condition. Nothing analogous to our step 3.** *(high)*

#### Q5 — keeping generated code correct

**SDKs: generated, stated in-source.** `stripe-python/stripe/billing/_meter_event.py` line 2 is
literally `# File generated from our OpenAPI spec`. *(high)*

**Docs snippets: no first-party claim found that they are generated from the OpenAPI spec.** The
structural evidence points to a **separate docs content model** — Markdoc components with typed
attributes (`KeyToken{type:"secret",value:…}`, `InlineCodeKey{apiKey,__md_code_plaintext}`,
`Fence{flavor:"python"}`) rendered per output target. **Negative finding, stated plainly.** *(high
that no such claim was found; medium on the mechanism)*

Docs are **API-version-aware**: the context object carries `"apiVersion":"2026-06-24.dahlia"`, and the
reference says *"The Stripe API differs for every account as we release new versions and tailor
functionality."* *(high)*

#### Q6 — verify your integration

- **`stripe listen`** — literally `stripe listen --forward-to localhost:3000/api/webhooks` and
  `STRIPE_WEBHOOK_SECRET=$(stripe listen --print-secret) npm run dev`. **Note the secret is piped from
  the CLI into the env, never pasted.** *(high)*
- **`stripe trigger <event>`** — with an important caveat in Stripe's own words: *"Events are
  triggered by issuing HTTP requests against the Stripe API. Because of this, triggering events causes
  side effects: all necessary API objects will be created in the process"*, and *"triggering
  `payment_intent.succeeded` also triggers `payment_intent.created`."* **A real object-graph exercise,
  not an echo.** *(high)*
- **Stripe Shell** — CLI commands inside the docs site, sandbox-only. *(high, documented)*
- **`stripe sandbox create`** — anonymous sandbox with working keys, **no account registration**.
- **Domain-level verification in the usage-based guide** — a dedicated *"Send a test meter event"*
  step (Dashboard: *Add usage > Manually input usage*, or API), then *"view usage details for your
  meter on the Meters page"*, then **"Create a preview invoice"**. *(high)* **This is the closest
  thing anyone ships to "post an event and see how it was rated."**

#### Gaps

- **Logged-in rendering of anything:** real-key substitution, the Run button, prerequisite
  auto-creation, the token-picker for `{{CUSTOMER_ID}}` (the `<a role="button" class="sn-token-provider">`
  element was observed; its behaviour was not).
- Workbench tab structure, test clocks, `stripe samples create`, stripe-samples CI — **not verified**;
  `workbench.md` is a nav stub and sub-pages were not reached.
- Whether Stripe's Meters Dashboard emits code.

---

### 1.2 Twilio

#### Surfaces found

- **API reference — MDX with a two-dimensional picker.** 8 language fences (`js python csharp java go
  php ruby` + `bash` carrying both curl and `twilio-cli`). Twilio also serves **`.md` alternates**
  (`<link rel="alternate" type="text/markdown">`). *(high)*
- **A scenario picker driven by the OpenAPI `examples` map.** The spec's example keys
  (`createVerification`, `createVerificationWhatsapp`, `createVerificationEmail`, `createVerificationSna`,
  …) surface as human labels: *"Start a Verification with SMS / with WhatsApp / with Voice / With
  Silent Network Auth / With Automatic SMS Fallback"*. **Pick a use case × pick a language → different
  code. This is Twilio's closest thing to a Code Builder, and it lives in the API reference.** *(high)*
- **Guided quickstarts** — clone-and-configure, not generate.
- **CodeExchange** (`twilio.com/code-exchange`) — every listing exposes **three parallel paths**:
  *"Quick Deploy this App"*, *"Download and Self-Host"* → *"View on GitHub"*, *"Test with the Twilio
  CLI"*. *(high)*
- **Function templates + Serverless Toolkit** — first-party statement: *"Under the hood, every
  CodeExchange Quick Deploy app is powered by a Function Template."* *(high)*

#### Q1 — chooses / emits

**CodeExchange Quick Deploy is a genuine configurator with a generated form.** On
`simple-sms-forwarding`: *"Log in to Twilio"* → *"Get a Twilio phone number"* → a **`Forwarding
Numbers`** field (*"A list of numbers in E.164 format you want to forward incoming messages to,
separated by commas"*) → *"Click the button below to deploy your app"*. It emits **a deployed, running
app in the user's own Functions Service**, then an in-browser editor.

The CLI path emits a scaffold — `twilio serverless:init example --template=forward-message` produces
a project tree including `.env`, `.twilioserverlessrc`, `functions/`, `assets/`.

#### Q2 — known vs supplied, and copy-paste survival

> **Twilio's philosophy is the exact inverse of Stripe's: never inject a credential — use env-var
> indirection.**

Literal and unaltered, from `/docs/verify/api/verification.md`:

```python
# Download the helper library from https://www.twilio.com/docs/python/install
import os
from twilio.rest import Client

# Find your Account SID and Auth Token at twilio.com/console
# and set the environment variables. See http://twil.io/secure
account_sid = os.environ["TWILIO_ACCOUNT_SID"]
auth_token = os.environ["TWILIO_AUTH_TOKEN"]
client = Client(account_sid, auth_token)

verification = client.verify.v2.services(
    "VAaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
).verifications.create(to="+15017122661", channel="sms")

print(verification.sid)
```

What survives copy-paste, and how:

- **Credentials** → `os.environ[...]`. Survives perfectly, and **is also the correct production
  pattern**. Nothing to substitute, nothing to leak.
- **Resource IDs** → **shape-preserving dummies**: `VAaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`,
  `ACaaaa…`, `RMaaaa…` — all exactly 34 chars with the correct 2-letter prefix. ⚠️ **Caution: `a` is a
  valid hex digit, so these *pass* the documented regex `^VA[0-9a-fA-F]{32}$`** and would clear
  client-side validation, failing only server-side. *(high, measured)*
- **Runtime values** → plausible examples, not placeholders: `to="+15017122661"`.
- **No display truncation, no hidden spans, no personalization.** What you see is exactly what you
  copy. No evidence Twilio injects your real Account SID. *(medium-high)*

> **The significant weakness — and it maps directly onto our problem.** In the messaging quickstart:
>
> ```python
> message = client.messages.create(
>     body="Join Earth's mightiest heroes. Like Kevin Bacon.",
>     from_="+15017122661",
>     to="+15558675310",
> )
> ```
>
> `from_` is **Twilio-owned** (the platform knows it); `to` is **developer-supplied**. Two
> structurally identical E.164 strings, **indistinguishable in the copied text**. The distinction
> exists only in numbered prose *outside* the code block: *"Replace the value for `from` with the
> phone number that Twilio gave you"*. **Same-typed values with different provenance are the failure
> case for a plausible-example convention.** *(high)*

**Twilio's best idea — an annotated `.env` that is a machine-readable config schema.** Literal
`forward-call/.env`:

```bash
# description: Calls made to your Twilio number will get forwarded to this e164-formatted phone number
# format: phone_number
# required: true
# link: https://www.twilio.com/docs/glossary/what-e164
MY_PHONE_NUMBER=+12223334444

# description: The path to the webhook
# configurable: false
TWILIO_VOICE_WEBHOOK_URL=/forward-call
```

The grammar is a **versioned spec** (`configure-env`): `required`, `format`, `description`, `link`,
`default`, `configurable`, `contentKey`; with
`format ∈ text | phone_number | email | url | sid | integer | number | secret | list(<X>) | map(<X>,<Y>) | file(json)`.
It compiles to `env-variables.manifest.json` (header: `"THIS FILE IS AUTOGENERATED. DO NOT MANIPULATE
OR COMMIT"`), which renders the CodeExchange web form — the manifest's `FORWARDING_NUMBERS`
description is **byte-identical to the form label observed on the live page**. `configurable: false`
is the escape hatch for structural values. **One artifact serves the local `.env`, the CLI prompt,
and the web form.** *(high)*

#### Q3 — explanation density

- **API reference:** bare. Two comment lines, the call, one `print()`. No prose between blocks.
- **Guided quickstart:** numbered steps, prose, screenshots, `[!CAUTION]`/`[!NOTE]` callouts, per-OS
  env-var setup blocks.
- **Notably, density does NOT increase for the stateful products.** The Verify and Video Rooms
  references — the two most lifecycle-shaped surfaces — get **exactly the same bare treatment as
  single-call SMS.** *(high)*

#### Q4 — multi-step lifecycle, error and retry

> **Twilio does not generate lifecycle code. A strong negative, stated plainly.**

Video Rooms is the closest analogue (create → in-progress → complete). Every snippet is **fully
standalone and re-declares the client from env vars.** Create:

```python
room = client.video.v1.rooms.create(unique_name="DailyStandup")
```

Complete — a separate, unconnected block on the same page:

```python
room = client.video.v1.rooms("RMXXXXXXXXXXXXXXXXXXXXXXXXXXXXX").update(
    status="completed"
)
```

**The room SID produced by step 1 appears in step 3 as a hardcoded dummy.** No threading, no variable
reuse, nothing equivalent to Stripe's Prerequisites graph. *(high)*

Across the whole Verify reference the samples do exactly one thing: `print(verification.sid)` (7×) or
`print(verification.status)` (5×). **Zero branching on state; zero `try`/`except` in the Video Rooms
reference; no idempotency keys, no retry guidance.** The state machine
(`pending | approved | max_attempts_reached | expired`) is documented **in prose and enums only, never
in generated code**. *(high)*

> **A revealing defect.** That `RMXXXXXXXXXXXXXXXXXXXXXXXXXXXXX` is **31 characters** — a malformed
> SID (real ones are 34) — and it propagates identically across *all* language tabs including the CLI
> tab. Meanwhile the generated `RMaaaa…` on the same page is correctly 34. **Two conventions coexist
> on one page: generated samples and legacy hand-written ones.** *(high, measured)*

#### Q5 — keeping generated code correct

**SDKs: generated, stated in-source.** `twilio-python/.../verification.py` opens with an ASCII banner
reading `twilio-oai-generator` then *"NOTE: This class is auto generated by OpenAPI Generator… Do not
edit the class manually."* *(high)*

**Spec:** `twilio/twilio-oai` README — *"Because this document is used across Twilio's whole API
development experience, these documents are automatically kept up to date and used to validate Twilio
API requests."* *(high)*

**Docs snippets: Twilio DOES claim generation and testing — unlike Stripe.** First-party, from their
engineering blog on the docs rebuild: *"automatically generating API reference pages from
specifications"*; *"tested code samples that developers can copy, paste, and run"*; and crucially
*"we have started developing a new code sample generation tool and, throughout this process, have
conducted an extensive audit, retested, and modernized our existing code samples."* Scale: *"nearly
20,000 code samples across nine coding languages"* over *"more than 5,000 pages"*. *(high)*

> **"Have started developing" is the tell** — the migration is incomplete, which is exactly what the
> 34-char-vs-31-char coexistence on a single page demonstrates. *(high)*

#### Q6 — verify your integration

- **Test credentials + magic numbers** — a separate Test Account SID/Auth Token: *"Twilio doesn't
  charge your account, update the state of your account, or connect to real phone numbers."*
  `+15005550006` = valid; `+15005550001` = invalid (21421); `+15005550009` = can't receive SMS
  (21614). **Constraints matter:** only 4 resource families supported (everything else `403`),
  **status callbacks do not fire**, and you cannot `twilio login` with them. *(high)*
- **Twilio Virtual Phone** — a Twilio-hosted inbox at **`+18777804236`**; the quickstart has you send
  to it and watch it arrive. *(high)*
- **Twilio Debugger** — row click opens *Log properties* with *"raw event data in JSON format, an
  error description, and, if applicable, the request inspector"* — the full HTTP request+response of
  the webhook call. 30-day window, US1 region only. *(high, documented; not observed)*
- **Dev Phone** — `twilio dev-phone` provisions real resources and serves a browser softphone. ⚠️
  *"Using the Dev Phone overwrites a phone number's webhooks."*
- **Guided quickstart verification is manual end-to-end**: run the app, receive a real SMS, type the
  code. No linter, no automated checklist. *(high)*
- **Twilio's docs pages have no embedded "Try it"/"Run" widget** — a clear negative vs Stripe.
  *(high)* An in-Console API Explorer is described in a 2020 changelog but
  `twilio.com/docs/api-explorer.md` **404s**; **could not confirm it still ships** *(low)*.

#### Gaps

- Anything inside the Console (no login): onboarding snippets, Debugger UI, whether any SID is ever
  auto-injected.
- CodeExchange catalog facets (JS-rendered).
- Conversations docs (all `.md` URLs tried 404'd); Video Rooms served as the session-shaped analogue.

---

### 1.3 Clerk

Clerk's docs renderer is closed source (private `clerk/clerk`); the MDX is open at
[`github.com/clerk/clerk-docs`](https://github.com/clerk/clerk-docs). Evidence below mixes
**observed** (raw HTML / RSC payload / shipped JS we fetched ourselves) and **documented**.

#### Q1 — chooses / emits

**There is no visual "pick options → get code" builder anywhere in Clerk.** *(high)* Clerk's answer
is a **personalized static doc** plus a **CLI**.

- **Docs quickstart.** Choose a framework via the SDK selector; the whole page re-renders. Two
  mechanisms, both in
  [`contributing/CONTRIBUTING.md`](https://github.com/clerk/clerk-docs/blob/main/contributing/CONTRIBUTING.md):
  `<If sdk="nextjs">` conditionals ("conditional rendering… based on the **active SDK**… **This
  component cannot be used within code blocks**") and *doc variants* ("the `quickstart.react.mdx`
  page is a variant of the `quickstart.mdx` page… keep the route the same"). *(high)*
- **The `clerk` CLI is now the quickstart spine.** `clerk.com/docs/quickstarts/nextjs` is entirely
  CLI-driven. Documented: `clerk init` "auto-detects your framework, installs the appropriate Clerk
  SDK, and applies framework-specific setup such as auth pages, middleware, and providers. If you're
  authenticated with `clerk auth login`, it also links your project to a Clerk application and
  **pulls your environment variables automatically**." Agent modes exist: `--mode agent`,
  `--input-json`, `clerk doctor --json`. Open source:
  [`github.com/clerk/cli`](https://github.com/clerk/cli). *(high)*
- **Negative finding, directly relevant to us: there is no Python / Flask / FastAPI quickstart.**
  *(high)* Go and Ruby exist. `CONTRIBUTING.md` explains that Python docs live in the SDK repo README,
  *outside* the docs system — so they get **none** of the key interpolation or SDK switching. Our
  Code Builder targets Python.

#### Q2 — known vs supplied, and copy-paste survival

**Clerk's advertised claim is true, and the distinction survives copy-paste as plain text.** Verified
at three layers.

**Source** *(documented)* — `CONTRIBUTING.md`: "You can use the following shortcodes within a code
block to **inject information from the user's current Clerk instance**: `{{pub_key}}`… `{{secret}}`…
`{{fapi_url}}`". The partial `docs/_partials/quickstarts/set-clerk-api-keys.mdx` is literally two
branches, `<SignedIn>` / `<SignedOut>`.

**Wire** *(observed — anonymous fetch of `clerk.com/docs/nextjs/getting-started/quickstart`)*. The
RSC payload carries the **unresolved** template as the copy-button prop:

```json
["$","$La5",null,{"text":"NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY={{pub_key}}\nCLERK_SECRET_KEY={{secret}}"}]
```

**The resolver** *(recovered from the shipped minified bundle
`/_next/static/chunks/0qsk225f8ytdh.js`)* — the load-bearing evidence:

```js
e = e.replace(/(?:{{|__)(.*?)(?:}}|__)/g, (e,t) => ({
  pub_key:  n?.user?.activeApp?.publishableKey ?? "YOUR_PUBLISHABLE_KEY",
  secret:   n?.user?.activeApp?.secretKey      ?? "YOUR_SECRET_KEY",
  fapi_url: n?.user?.activeApp?.frontendApiUrl ?? "YOUR_FRONTEND_API_URL",
  jwks_url: n?.user?.activeApp?.jwksUrl        ?? "YOUR_JWKS_URL"
})[t] ?? e)
```

Five consequences, all directly applicable to us:

1. **Copy-paste carries the resolved value.** Substitution runs on the string handed to
   `CopyButton`. Signed in → your real key hits the clipboard. Signed out → the literal
   `YOUR_PUBLISHABLE_KEY` hits the clipboard. **Not CSS- or tooltip-only.** *(high — read off the
   resolver; we could not run the page signed in, so the signed-in clipboard was not observed)*
2. **The "fill this in yourself" marker is a naming convention, not metadata.** SCREAMING_SNAKE, no
   delimiters. Nothing in the copied text distinguishes platform-supplied from you-supply beyond
   that convention.
3. The regex accepts **two delimiters** — `{{pub_key}}` *and* `__pub_key__` — useful where `{{ }}`
   collides with host syntax.
4. A **fourth token, `jwks_url`, exists in shipped code but is undocumented** in the contributor guide.
5. Resolution keys on `DocsContext.user.activeApp` — interpolation is **per-app**, not per-account.

**Security note worth carrying over:** secret masking is presentational only — `text-transparent`
plus a `::before` overlay of `•` from `data-obscured`. The real secret is in the DOM, and **the copy
button resolves `{{secret}}` regardless of the obscure toggle.** *(observed)*

Auth branching is CSS and **both branches ship**: `<div data-auth="" data-signed-in="" class="hidden
in-[.signed-in]:contents">` — 62 `data-signed-in` and 62 `data-signed-out` occurrences in one
anonymous response. The **code block is not duplicated** — one client component, two resolutions.
*(observed)*

#### Q3 — explanation density

**Full guided walkthrough; prose-heavy; snippets mostly uncommented.** *(high)*

- `<Steps>`-structured with a numbered right-rail ToC (`data-step="1".."7"` observed).
- Snippets carry **presentation metadata rather than comments**:
  ` ```tsx {{ filename: 'app/layout.tsx', mark: [2, [29, 44]], fold: [[6, 19]] }} ` — filename
  banner, highlighted lines, collapsed regions.
- **Inline comments are reserved for the non-obvious, and used as pointers to other docs:**
  `// See https://clerk.com/docs/guides/development/custom-flows/error-handling`.
- **A distinct agent register exists inline:** `<If is="llm">` (72 uses) swaps human instructions for
  machine ones.
- **Content negotiation** *(observed)*: same URL, `Accept: text/html` → **1,128,464 bytes** of human
  walkthrough; `Accept: text/markdown` (or `.md` suffix) → **6,731 bytes** beginning "# Add Clerk
  Authentication to Next.js / Set up Clerk authentication in this Next.js project with the Clerk
  CLI." **An agent scraping the docs URL gets a CLI recipe, not the snippets.**

#### Q4 — multi-step lifecycle, error and retry

**The strongest lifecycle example of the identity vendors — but deliberately hidden by default.**
*(high)*

The default path (`<SignIn />`, `<ClerkProvider>`) hides the lifecycle entirely. The multi-step story
lives in **custom flows**, opt-in behind a callout. From
[`custom-flows/authentication/email-password`](https://clerk.com/docs/guides/development/custom-flows/authentication/email-password):

> 1. Initiate the sign-up process… with the `signUp.password()` method.
> 1. Send a one-time code… with `signUp.verifications.sendEmailCode()`.
> 1. Collect the user's one-time code and verify it with `signUp.verifications.verifyEmailCode()`.
> 1. If the email address verification is successful, the `signUp.status` will be `complete`, and you
>    can finish the sign-up flow with `signUp.finalize()`…

`signUp` / `signIn` are **stateful handles with a `.status` discriminant** (`'complete'`,
`'needs_first_factor'`, `'needs_second_factor'`, `'needs_client_trust'`), and `finalize()` is the
explicit close. `session.currentTask` is a documented "not actually done yet" state *after* close.

**Errors are a first-class dedicated surface**, consistent across generated code:

```tsx
const { error } = await signUp.password({ emailAddress, password })
if (error) {
  // See https://clerk.com/docs/guides/development/custom-flows/error-handling
  // for more info on error handling
  console.error(JSON.stringify(error, null, 2))
  return
}
```

Two channels, with guidance on which to use: "Prefer using the global `errors` object returned by the
hooks to render UI, and the `error` property returned by individual methods to programmatically
handle errors."

**Retry and backoff are genuinely ABSENT.** *(high)* No generic retry, no backoff, no idempotency-key
guidance anywhere in the flow docs. The only retry-shaped material is *specific error recovery*:
`user_locked` returns 403 with `"meta": { "lockout_expires_in_seconds": 1800 }` and a worked example
converting it to an absolute retry time; `form_password_compromised` returns 422 and the snippet
**auto-pivots the flow** to `signIn.emailCode.sendCode()`. In-flight state (`fetchStatus`) is used for
exactly one thing — `disabled={fetchStatus === 'fetching'}`, double-submit prevention, not retry.

**The lesson.** Clerk proves a handle lifecycle *can* be taught in hand-written snippets by (a)
hiding it by default, (b) leading with a **numbered prose contract before any code**, (c) making
`status` the branch point, and (d) factoring error handling into a separate doc that snippets link to
*from inside a comment*.

#### Q5 — keeping generated code correct

**Overwhelmingly hand-maintained MDX with weak automated correctness. No OpenAPI-driven or
live-state-driven snippet generation for integration code.** *(high)*

First-party admissions:

- `CONTRIBUTING.md`: "**Neither check verifies factual claims** about the external APIs and SDKs the
  docs describe (endpoints, versions, method signatures…). Verify those against their source
  repositories."
- `AGENTS.md`: "SDK code examples must match the canonical partials… **The build never executes code
  blocks**, so copy the pattern from there, not from memory."

What *is* automated: a **Typedoc pipeline** (auto-PRs from `clerk/javascript` on release — covers
**API reference signatures, not quickstart snippets**); **Prettier formats code inside code blocks**
("a deliberate tool to help prevent syntax errors from finding their way into code examples" —
catches syntax, never semantics). There is **no OpenAPI spec in the docs repo**.

> **The single most useful finding here for us.** `scripts/check-quickstarts.mjs` diffs
> `docs/getting-started/quickstart*` and, on change, prints "⚠️ Please update the corresponding
> quickstarts in the Dashboard" — then **`process.exit(0)`**. A `lint.yml` job posts that as a **PR
> comment**. So Clerk's **in-console quickstarts are a second, manually-synchronized copy of the
> docs, guarded only by a non-blocking bot comment.** If we build a console Code Builder alongside
> docs, this is the exact failure mode to design out. *(high — source)*

#### Q6 — verify your integration

Three surfaces. The CLI verifies *wiring*; proving auth *works* is left to a manual human step. *(high)*

1. **`clerk doctor`** — "Runs a series of diagnostic checks… read-only and never modifies any state
   (unless `--fix`)." Nine checks: auth token present, token valid (`GET /oauth/userinfo`), project
   linked, application accessible (`GET /v1/platform/applications/{appId}`), instance IDs match, env
   vars present in `.env.local`/`.env`, CLI config parses, shell completion, MCP handshake. **Only
   two live API calls. It does not run your app or attempt an auth round-trip.** JSON results carry
   `name`, `status`, `message`, `remedy`, `fix`; "Agents cannot use `--fix` directly… agents should
   read the `remedy` field… and orchestrate fixes themselves."
2. **The real functional check is manual prose.** `_partials/quickstarts/create-first-user-step.mdx`
   in full: "## Create your first user / 1. Visit your app's homepage at http://localhost:3000. / 1.
   Select "Sign up" on the page and authenticate to create your first user."
3. **Keyless mode.** `clerk init` without an account starts you on **temporary development keys** —
   verification-by-working-app precedes account setup.
4. **Webhooks:** `clerk webhooks listen` "opens a relay tunnel that forwards Clerk webhook deliveries
   to your local server"; `clerk webhooks verify` "checks a delivery's signature offline".

#### Gaps

- **Login-gated, not reached:** the Dashboard API keys / **Quick Copy** page (referenced in nearly
  every quickstart, never shown); the Dashboard's own quickstart pages (existence proven by
  `check-quickstarts.mjs`, contents unseen); the JWT template editor.
- **Closed source:** the docs renderer and SDK selector. Key injection was recovered from the shipped
  minified bundle, not from source.
- **Not executed signed in** — "signed-in copy yields your real key" is read off the resolver, one
  step removed from observation.

---

### 1.4 Auth0

**Logged out throughout.** Every claim about the signed-in Dashboard is *documented behaviour we
read*, never *behaviour we observed*.

Auth0 runs **two generations of quickstart concurrently**, and they behave differently — the single
most important structural fact about it.

| Surface | Generation | Emits |
|---|---|---|
| `/docs/quickstart/{webapp,spa,native,backend}/*` + `/interactive` | **Legacy** | Long-form tutorial, `{yourX}` placeholders, "Log In & Download Sample" |
| `/quickstart/webapp/{fastify,nextjs,python}`, `/spa/react` | **Rewritten (Mintlify)** | 3-tab chooser: Quick Setup / CLI / Dashboard |
| Dashboard → Application → Quick Start tab | Dashboard | Quickstart scoped to that app (**login-gated**) |
| `auth0 qs setup` / `auth0 qs download` | CLI | Creates tenant resources **and writes a real `.env`** |
| Actions editor + template gallery | Dashboard | Runnable JS scaffold + test runner |
| Deploy CLI keyword replacement | CLI | Config — but the cleanest injection *syntax* Auth0 has |

#### Q1 — chooses / emits

1. **Legacy "interactive selector"** (`/quickstart/webapp/django/interactive`): "Use the interactive
   selector to create a new Auth0 application or select an existing application…" And crucially:
   **"Any settings you configure using this quickstart will automatically update for your Application
   in the Dashboard."** *(high, documented)* — **the doc page is a read-write control surface**;
   edits flow *back* into tenant config.
2. **"Log In & Download Sample"** — verified verbatim on `dev.auth0.com/docs/quickstart/webapp/django`:
   *"Get a sample configured with your account settings…"*, and **"If you download the sample from
   the top of this page, these details are filled out for you."** *(high)*
3. **Rewritten quickstarts — 3-tab chooser** (`/quickstart/webapp/fastify`): "You have three options
   to set up your Auth0 app: use the Quick Setup tool (recommended), run a CLI command, or configure
   manually via the Dashboard". Quick Setup body in full: **"Create an Auth0 App and copy the
   pre-filled `.env` file with the right configuration values."** The artifact emitted is **one file,
   a pre-filled `.env`.** *(high)*
4. **`auth0 qs setup`** — "Auto-detects your project, creates an Auth0 application and/or API, and
   generates a config file." Flags: `--type`, `--framework`, `--build-tool`, `--port`, `--identifier`,
   `--scopes`, `--offline-access`. **This is the strongest single piece of prior art found anywhere
   in this investigation** — it *inverts* the model: rather than the console emitting code for you to
   paste, the **CLI reads your local project, infers the framework, provisions the remote resource to
   match, and writes the local config file.** *(high)*
5. **Actions editor** — choose a template → "You should now see a read-only preview of the code
   within the template. To proceed, select **Use this template**." Notably **no tenant values
   injected**; config arrives via `event.secrets.*` at runtime ("Once a Secret has been created, its
   value will never be revealed"). The *opposite* choice to the quickstarts, deliberately.
6. **Negative finding:** the public Management API reference pages have **no live "Try it out"
   widget**. Live execution is a *Dashboard* tab.

#### Q2 — known vs supplied, and copy-paste survival

> **Auth0's legacy docs are templated with `${account.*}` and substituted at render time — and the
> substitution is visibly BROKEN in production, leaking raw template markers.** Both leaks verified
> by us today. *(high)*

On `auth0.com/docs/quickstart/backend/python/02-using` the live page contains, literally (8
occurrences):

```
%24%7Baccount.clientId%7D&client_secret={yourClientSecret}&audience=YOUR_API_IDENTIFIER
```

`%24%7Baccount.clientId%7D` is URL-encoded **`${account.clientId}`**. The templating pass ran over
unencoded source; the sample was then URL-encoded; the encoded form no longer matched the
substitution regex, so the raw variable shipped. The same page carries `/{yourDomain}/oauth/token`
**14 times** — the host wrongly relocated into the *path*.

On `auth0.com/docs/api/management/v2` we found **`@@TENANT@@` 8 times** in curl examples — a
*different* marker, and the same delimiter the Deploy CLI documents:

> "Using the `@` symbols causes the tool to perform a `JSON.stringify` on your value before replacing
> it. So if your value is a string, the tool will add quotes… Using the `#` symbol causes the tool to
> perform a literal replacement; it will not add quotes or braces."

**That two-sigil design — `@@KEY@@` (serialize) vs `##KEY##` (literal) — is the one genuinely
well-engineered idea in the corpus, and it precisely solves the bug that mangles the quickstart
samples. It was never back-ported to the docs.**

**Placeholder inventory — there is no single convention.**

| Syntax | Where | Substituted when logged in? |
|---|---|---|
| `{yourDomain}` `{yourClientId}` `{yourClientSecret}` `{yourTenant}` | Legacy quickstarts | **Yes** *(documented)* |
| `YOUR_API_IDENTIFIER`, `YOUR_DOMAIN` | react/interactive | No |
| `YOUR_AUTH0_DOMAIN` `YOUR_CLIENT_ID` `YOUR_CLIENT_SECRET` | `/quickstart/webapp/python` (rewritten) | **No — and domain/clientId ARE tenant-known** |
| `{YOUR_DOMAIN}` + `<token>` | Management API reference | No |
| `@@TENANT@@`, `${account.clientId}` | Leaked markers | — |
| `${generateRandomString(32)}` | fastify/nextjs `.env` | **Client-side generated, not tenant data** |

**The latent convention, and where it breaks.** In the *legacy* corpus there is a real correlation:
**curly-brace lowerCamel `{yourDomain}` ⇒ Auth0 fills it; SCREAMING_SNAKE `YOUR_API_IDENTIFIER` ⇒ you
supply it.** The distinction is carried in casing and bracket style — i.e. **in the text**. But it
**does not survive the rewrite**: `/quickstart/webapp/python` uses `YOUR_AUTH0_DOMAIN` for a value
Auth0 absolutely knows. The convention exists, is **documented nowhere**, and has already decayed.
*(high on the observations; medium that it was intentional)*

**Does it survive copy-paste? Yes — and this is Auth0's real lesson.** Every placeholder is **plain
text inside the code block**. Nothing is encoded in CSS, tooltips, `<span>` decoration, or hover
state. Paste `AUTH0_CLIENT_ID={yourClientId}` into `vi` and the brace is still there — it **fails
loudly and greppably** rather than silently shipping an empty string.

Two caveats for our design:

1. **Text-encoding without a legend is only half a solution.** Logged out, `{yourClientId}` (platform
   fills) and `YOUR_API_IDENTIFIER` (you fill) sit in the *same code block* with nothing telling the
   reader that the casing means anything.
2. **A third value category is silently mixed in.** `AUTH0_SECRET=${generateRandomString(32)}` is
   neither platform-known nor developer-supplied — it is *generated locally and never leaves the
   machine*, and gets identical visual treatment. **We will have this category too** (idempotency
   keys, `request_id`). Auth0 offers no answer.

#### Q3 — explanation density

**Full guided walkthrough — 17 steps** on legacy Django, from "Configure Auth0" through "Run your
application". Pattern per step: prose → code block → occasional consequence warning. Prose is
*conceptual*, code blocks are near-bare — roughly **45 words of prose for 3 lines of code**.
**Explanation lives beside the code, not inside it as comments — so the explanation is exactly what
is lost on copy-paste.** *(high)*

Config steps carry explicit failure consequences ("If this field is not set, users will be unable to
log in… and will get an error").

**Checkpoints exist only in the rewritten generation** (absent from legacy Django — verified). The
React page's compiled payload contains a `<Check>` callout: **"Checkpoint"** + "You should now have a
fully functional Auth0 login page running on your `localhost`". **Checkpoints are prose assertions,
not executable checks.** *(high)*

#### Q4 — multi-step lifecycle, error and retry

**Yes, a multi-step flow is generated. No, it is not good prior art for "open a handle → report
against it → close it."** Stating this plainly because it is tempting to over-read.

Generated Django code spans `login` (`authorize_redirect`), `callback` (`authorize_access_token`,
`request.session["user"] = token`), `logout` (`session.clear()` + redirect).

**Why the analogy is weaker than it looks:** in a handle lifecycle *the developer holds a correlating
identifier and threads it through subsequent calls* — and that identifier is precisely what a Code
Builder must teach. Here **no identifier is ever surfaced to the developer.** Correlation is carried
by the OAuth `state` parameter (generated and validated *inside* `authorize_redirect` /
`authorize_access_token`) and a session cookie. The three functions are independent HTTP endpoints
sharing state only through framework machinery. **The load-bearing difficulty — "here is the ID you
got at open; here is where it goes at report; here is where it goes at close" — is exactly what
Auth0's SDKs hide, and therefore exactly what its quickstarts never teach.**

**Verdict: weak-to-moderate prior art.** Useful for the *shape*: a lifecycle spread across separate
code locations, each with its own prose section **and its own dashboard-side config prerequisite**
(Callback URL / Logout URL steps) — each lifecycle stage has a matching tenant-side setting the
quickstart makes you configure.

**Error and retry: evidence is THIN.** Across every quickstart read: **zero `try`/`except`, zero
retry loops, zero backoff in emitted code.** The Django callback calls `authorize_access_token` bare —
a failed exchange raises straight into Django's 500. Error handling appears **only as prose, and only
in the rewritten generation**: `/quickstart/webapp/python` says "Implement exponential backoff for
retries" with **no accompanying code**.

The rewritten quickstarts instead invest in **symptom-indexed troubleshooting** — "If you see a
`JWEDecryptionFailed: decryption operation failed` error, this is caused by either an invalid
`AUTH0_SECRET` or an old session cookie encrypted with a different secret." **That maps an exact
searchable error string to a specific misconfiguration, and is a transferable idea for us**
(duplicate idempotency key, unknown event type, closed task).

#### Q5 — keeping generated code correct

**Quickstart prose and sample repos are maintained SEPARATELY, by hand. There is no
snippet-from-repo mechanism.** Firm negative finding. *(high)*

Proof — the same conceptual file differs between the two places. Docs (`/quickstart/webapp/nextjs`)
emit `AUTH0_DOMAIN={yourDomain}` … `AUTH0_SECRET=${generateRandomString(32)}`; the sample repo README
(`auth0-samples/auth0-nextjs-samples`, `Sample-01`) emits `AUTH0_DOMAIN='YOUR_AUTH0_DOMAIN.auth0.com'`
plus `AUTH0_AUDIENCE`/`AUTH0_SCOPE` which the docs omit. **Different placeholder syntax, different
quoting, different variable set. If the docs included the repo file they would be identical.**

**Samples under CI: inconsistently, and the good ones are very good.**
`auth0-nextjs-samples/.circleci/config.yml` runs `npm ci` → `npm run build` → `npm test` → install
Chrome → `npm run test:integration` → store Cypress videos — **a real browser E2E login test**, the
correctness mechanism that actually matters. But coverage is uneven: `auth0-samples/auth0-python-web-app`'s
only workflow is **`semgrep.yml`**, a security scanner, not a build. *(high on the four repos
sampled; low org-wide — the org spans ~106 repos)*

**OpenAPI: real.** Verified on `/docs/api/management/v2`: "The Auth0 Management API documentation
follows the [Auth0 Management API OpenAPI v3.1 schema]… Please note that OpenAPI v3.1 schema support
is currently in Beta."

**Are SDK snippets generated from it? Strong circumstantial yes, no first-party statement.** From
`/docs/api/management/v2/users/get-users`: `await client.users.list({ page: 1, perPage: 1,
includeTotals: true, sort: "sort", connection: "connection", fields: "fields", q: "q", … })` —
**every parameter using its own name as its dummy value**, every optional param enumerated:
the unmistakable fingerprint of a spec-driven generator. *(medium-high on the inference; low that it
is documented)*

> **The contrast is the finding.** The *API reference* is spec-generated and stays correct
> mechanically, but its snippets are useless as teaching material. The *quickstarts* are hand-written
> and pedagogically excellent, **but drift — and the drift is visible from the outside, on a live
> production page, today.**

#### Q6 — verify your integration

Ordered by how much each actually proves.

1. **Checkpoint** — proves nothing mechanically. Prose assertion; no execution, no probe.
2. **"Try" / "Try Connection" on a Connection — genuinely strong, and the best idea in the set.**
   Verified literal text: **"Auth0 simulates the authentication flow as if it were an application,
   displaying the User Profile resulting from a successful authentication."** Success renders an
   **"It Works!"** page showing the actual claim shape you will receive. The diagnostic value is the
   **bisection** — first-party troubleshooting guidance states that if the TRY button fails, the
   fault is in the connection or provider, **not your application**. **A verify step whose purpose is
   to partition the failure space, cutting the developer's code out of the loop entirely.** *(high)*
3. **API Explorer tab (Dashboard)** — auto-generated token with a Copy icon, expiry via **Token
   Expiration (Seconds)** (default "86400 seconds"), then **Update & Regenerate Token**. Warnings:
   "only for test purposes"; "These tokens **cannot be revoked**". Value-injection *and* verification
   in one: a **live working credential for your tenant**.
4. **Actions test runner — sandboxed, mock payload.** **Test** → editable **Payload** ("a sample
   payload based on the flow…") → **Run**; output shows "the steps that the Action took, console
   output, any errors that occurred, and useful statistics". Runs against **mock data, not real
   tenant traffic**. Auth0 is explicit that its own runner is insufficient: "For end-to-end
   verification, you must deploy the Action and attach it to a flow, then verify through actual login
   attempts or review tenant logs." **Useful honesty to copy.**
5. **Logs — the real end-to-end verifier.** Actions Logs stream "all logs in real-time… includes all
   `console.log` output and exceptions", with "no need to refresh the page". Tenant Logs support
   search (`connection:*pass*`), type filters (**Failed Login**), date ranges; `auth0 logs tail`
   streams in the terminal. **Notable gap:** logs are documented as an *ops* tool and the quickstarts
   do **not** route you there at the Checkpoint.

#### Gaps

- **Login-gated, not observed:** the interactive selector rendering real values (four first-party
  descriptions read, zero observed); **whether injected values are visually distinguished from
  developer-supplied ones**; **whether `client_secret` is literally written into the downloaded
  zip** — the question we would most want answered before copying the pattern; the Dashboard Quick
  Start tab; live "Try it out".
- **Genuinely undocumented (searched, not found):** any Auth0 page explaining its own placeholder
  convention — `{yourDomain}` vs `YOUR_API_IDENTIFIER` has **no legend anywhere**; `${account.*}` and
  `@@TENANT@@` documented nowhere, discovered only through leakage; any statement on
  quickstart↔sample sync.

---

### 1.5 Supabase

**The strongest prior art for Q2 and Q5, and we were able to read the actual generator source.**
Everything marked *(source)* is verbatim from
[`github.com/supabase/supabase`](https://github.com/supabase/supabase) at `master`. **The Dashboard
UI itself is login-gated and was not observed** — the open source is the next-best, and arguably
better, evidence.

| Surface | Generation model |
|---|---|
| **Dashboard auto-generated API docs** — per-table, per-column | **From live DB schema via PostgREST OpenAPI** |
| **Connect sheet** — framework × variant × library | Hand-maintained per-framework templates + injected keys |
| Docs-site `ProjectConfigVariables` widget | Live org/project/branch selector, real values, copy button |
| `supabase gen types typescript` | From live schema |
| Edge Functions editor + templates + **Test** runner | Templates + live invoke |

> **Correction to a common assumption:** the Dashboard API-docs page offers **JavaScript and
> Bash/cURL only** — not Dart/Swift/Python. `LangSelector.tsx` *(source)* renders exactly two
> `ToggleGroupItem`s, `js` and `bash`. `Snippets.ts` *does* contain `python` and `dart` variants but
> **only for `init()`**, unreachable from the dashboard — dead code. *(high)*

#### Q1 — chooses / emits

**1. Auto-generated API docs (the headline surface).** Choose a **table or RPC from your own schema**
(sidebar), a **language** (JS / Bash), and **which API key to display**. Emits a full per-table CRUD
reference — Read all rows, Read specific columns, Read referenced tables, With pagination, With
filtering, Insert a row, Insert many rows, Upsert, Update, Delete, plus Realtime subscribe variants —
**with your real table name, your real column names, and your real project URL interpolated.** *(high)*

**2. Connect sheet — a genuine multi-axis code builder.** `resolveContentPath` *(source)*:

```ts
/**
 * Resolves a content path template by replacing {{key}} placeholders with state values.
 * Examples:
 *   - '{{framework}}/{{frameworkVariant}}/{{library}}' with state {framework: 'nextjs', ...}
 *     → 'nextjs/app/supabasejs'
 */
```

Top-level modes *(source, `CONNECTION_TYPES`)*: `direct` · `frameworks` · `mobiles` · `orms` · `mcp`.
21 framework content directories including **`flask`** (supabase-py), plus per-language
direct-connection emitters (Golang, Node.js, PHP, **Python**, **SQLAlchemy**, JDBC, .NET), each with
`fileTitle: '.env'`. Steps are composable: `install` · `env` · `skills-install` · `mcp` ·
`direct-connection` · framework content.

#### Q2 — known vs supplied, and copy-paste survival

**Supabase demonstrates FOUR different conventions across its own surfaces — and the best one is
architectural, not typographic.**

> **(a) The best pattern found anywhere in this research — separation of files.**
> `content/flask/supabasepy/content.tsx` *(source, verbatim)* emits **two named files** via
> `MultipleCodeBlock`:
>
> ```bash
> # .env
> SUPABASE_URL=${projectKeys.apiUrl ?? 'your-project-url'}
> SUPABASE_KEY=${projectKeys.publishableKey ?? projectKeys.anonKey ?? 'your-anon-key'}
> ```
> ```python
> # app.py
> supabase: Client = create_client(
>     os.environ.get("SUPABASE_URL"),
>     os.environ.get("SUPABASE_KEY")
> )
> ```
>
> **The tenant-specific values are confined to a separate `.env` tab where they are injected REAL.
> The application code contains ZERO secrets and ZERO placeholders — it references config by env-var
> NAME.** Copy-paste survival is achieved by **separation of artifacts, not by placeholder syntax**:
> the `.env` file *is* the config block, and the code is correct as pasted. *(high — source)*

**(b) The weakest pattern — a bare ALL-CAPS token inside a quoted string.** `ResourceContent.tsx`
*(source)*, one line: `const keyToShow = !!showApiKey ? showApiKey : 'SUPABASE_KEY'`. So the
**default** curl output on the API-docs page is literally:

```bash
curl 'https://<your-ref>.supabase.co/rest/v1/orders?select=*' \
-H "apikey: SUPABASE_KEY" \
-H "Authorization: Bearer SUPABASE_KEY"
```

**`SUPABASE_KEY` is a bare ALL-CAPS token — no angle brackets, no `$`, sitting inside a quoted HTTP
header.** It survives copy-paste *as text*, but is **syntactically indistinguishable from a real
value**; you must simply *know* that ALL-CAPS means substitute-me.

> **The asymmetry is the sharpest single finding for us.** In the same `init()` snippet *(source)*:
>
> ```js
> const supabaseUrl = 'https://<real-ref>.supabase.co'   // REAL, interpolated
> const supabaseKey = process.env.SUPABASE_KEY            // env-var read — CORRECT as pasted
> ```
>
> **The JS/Python snippets are copy-paste-runnable (env-var read). The curl snippet for the same key
> is copy-paste-BROKEN (literal token in a header).** The *non-secret* value (project URL) is always
> interpolated real; the *secret* is routed through an env-var reference in the client languages but
> inlined as a bare token in curl. **We ship exactly this pair of targets — Python SDK and curl.**

**(c) The docs site — angle-bracketed, verb-in-the-token, and NOT interpolated.**
`/docs/guides/getting-started/quickstarts/nextjs` (raw-HTML grep confirms only these two tokens):

```
NEXT_PUBLIC_SUPABASE_URL=<SUBSTITUTE_SUPABASE_URL>
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<SUBSTITUTE_SUPABASE_PUBLISHABLE_KEY>
```

Angle brackets + ALL_CAPS + **the verb "SUBSTITUTE" inside the token itself** — the most
self-describing placeholder found across the whole investigation.

**Critically, the "helper" does NOT interpolate into the code block.** `ProjectConfigVariables.tsx`
*(source)* renders a **separate read-only monospace `<Input>` beside the snippet**, with a copy
button:

```ts
stateSummary === 'loggedIn.selectedProject.dataSuccess' ? variableValue
  : stateSummary === 'loggedIn.selectedProject.projectPaused' ? 'PROJECT PAUSED'
  : `YOUR ${prettyFormatVariable[variable].toUpperCase()}`
```

Logged out → the field reads literally `YOUR PROJECT URL` and the copy button is
`disabled={!variableValue}`. **So Supabase's docs site deliberately keeps real credentials OUT of the
code block and puts them in an adjacent copy-field — the opposite of Clerk's in-snippet
interpolation.** *(high — source)*

**(d) A fourth convention** appears in Edge Functions docs: `https://[YOUR_PROJECT_ID].supabase.co/…`
(square brackets) and `apikey: '<KEY>'`. **Four incompatible conventions across one vendor is itself
a finding.**

**Structure vs data.** Schema-derived identifiers are interpolated **real** — `${resourceId}` (your
table), `${columnName}` (your column, one snippet emitted *per column*: `columnName: x.id`
*(source)*). But **data values remain generic English prose**: `'someValue'`, `'someone@email.com'`,
`'+13334445555'`, `'some-password'` — neither ALL-CAPS nor bracketed, a weak text-encoding of "you
supply this."

**Secret keys are deliberately never emitted in full.** `LangSelector.tsx` *(source)*: publishable and
legacy keys inject `key.api_key` (the real value), but for secret keys `const value = key.prefix +
'...'` — a **truncated, deliberately non-functional** key, gated on `PermissionAction.SECRETS_READ`.

#### Q3 — explanation density

**Annotated-by-adjacency: prose section and code panel side by side, snippets nearly comment-free.**
Every `DocSection` *(source)* pairs a `content` prose block with a `snippets` panel. The one place
inline comments appear is `readFilters` *(source)* — `// Filters`, `// Arrays`, `// Logical
operators` as *section dividers inside a cheatsheet*, not explanations.

**Two distinctive mechanisms worth stealing:**

1. **Doc prose is stored in the tenant's own schema, and is editable from the docs page.**
   `Description.tsx` *(source)* renders each column's description from the OpenAPI `description`
   (which PostgREST populates from Postgres COMMENTs) in an **editable textarea**, and on save issues
   `comment on column "public"."<table>"."<column>" is '<value>';`. **The generated docs are
   bidirectional: the explanation lives in the database.** *(high — source)*
2. **"Copy prompt" — the whole builder serialized for an AI agent.** `CopyPromptAdmonition.tsx`
   *(source)*, tooltip: **"Copy these steps for your coding agent"**. `buildConnectPrompt` walks
   `[data-connect-step]` elements and emits numbered steps with description, prose, and fenced code
   per file tab. Snippet extraction **prefers `data-connect-copy-value` over `textContent`** — i.e.
   **the copy payload is a declared value, not scraped display text.** Directly applicable to a
   four-call-site builder.

#### Q4 — multi-step lifecycle, error and retry

**Partial hit — the closest true "open a handle" generator found anywhere, but with no close step.**

The Realtime `subscribe*` snippets *(source)* emit a **named, schema-derived handle**:

```js
const ordersListener = supabase.channel('custom-all-channel')
  .on('postgres_changes', { event: '*', schema: 'public', table: 'orders' }, (payload) => {
      console.log('Change received!', payload)
    })
  .subscribe()
```

The variable name comes from `resourceMeta.camelCase` — derived from **your real table name**. So: a
handle is opened, bound to a resource, assigned to a variable, and events arrive against it. **But
there is NO `unsubscribe()` / `removeChannel()` snippet anywhere in `Snippets.ts`.** The lifecycle is
generated open-and-receive, never open-report-close.

**Error handling: surfaced as a value, almost never handled. Retry: entirely absent.** Every JS
snippet destructures `{ data, error }`, but across the whole 787-line file **exactly one** acts on it
— `rpcSingle` *(source)*: `if (error) console.error(error)`. **Zero retry, zero backoff, zero
idempotency guidance.** The curl snippets have no error handling at all.

**Evidence of hand-maintained template drift:** `authRecover`'s JS emits
`supabase.auth.resetPasswordForEmail(email)` — referencing an `email` variable never defined in the
snippet, while the sibling curl uses the literal `"someone@email.com"`.

#### Q5 — keeping generated code correct

**Three distinct models running side by side. The first is the important one.**

> **1. Dashboard API docs — generated from LIVE PROJECT STATE via OpenAPI.** `ResourceContent.tsx`
> *(source)*:
>
> ```ts
> const { data: jsonSchema } = useProjectJsonSchemaQuery({ projectRef: ref })
> const { paths, definitions } = jsonSchema || {}
> const resourceDefinition = definitions?.[resourceId]
> ```
>
> `project-json-schema-query.ts` *(source)* fetches `GET /platform/projects/{ref}/api/rest` typed with
> `swagger: string`, `paths`, `definitions` — **a Swagger 2.0 document produced by PostgREST from live
> database introspection, fetched per project at page load.**
>
> Characterised precisely: **the snippet TEMPLATES are hand-written TypeScript template literals; the
> SCHEMA they are parameterised by is fetched live from the running project.** Table/column drift is
> **impossible by construction** (rename a column, the docs change on next load), while *API-shape*
> drift is possible and unguarded. Supabase's own in-product statement *(source,
> `GeneratingTypes.tsx`)*: "Supabase APIs are generated from your database, which means that we can
> use database introspection to generate type-safe API definitions." *(high)*

**2. Types — live schema, kept fresh by scheduled CI.** `npx supabase gen types typescript
--project-id "$PROJECT_REF"`. First-party guidance: "One way to keep your type definitions in sync
with your database is to set up a GitHub action that runs on a schedule" — which "will commit new
type changes to your repo every night".

**3. Reference docs — a hybrid pipeline.** `apps/docs/spec/Makefile` *(source)* runs `download →
transform → generate → format`, where `download` curls **live specs** (`api.supabase.com/api/v1-json`,
Storage's `api.json`, TypeDoc JSON per client library). **But the client-library reference pages are
hand-maintained YAML** — `supabase_py_v2.yml` is **9,260 lines** with hand-written examples, each
carrying both a `code` block and the literal `response` JSON.

**4. Connect sheet — purely hand-maintained templates.** The Flask template hardcodes
`.table('todos')`, a generic example table with no relation to your schema, and **the framework
templates themselves are untested** (only the utils have tests).

#### Q6 — verify your integration

- **Edge Functions: a genuine test runner.** Deploy "Via Editor" → **"Click the 'Test' button"** →
  configure HTTP method, headers, query params, body, authorization → **"Send Request"**. **The only
  real send-a-request-and-see-the-response verification in Supabase.** *(high, documented; UI not
  observed)*
- **Logs Explorer** — sources include API, Postgres, Auth, Storage, Realtime, Edge Functions.
  Failing-request query documented: `toInt32OrZero(log_attributes['response.status_code']) >= 400`.
  **But it is framed as post-hoc "log tracing and debugging" (1,000 rows/query), not a live tail, and
  there is no documented "verify your integration" workflow pointing at it.** Same disconnect as Auth0.
- **The API-docs page itself has no verify step** — no "run this" button anywhere in
  `ResourceContent.tsx` / `Snippets.ts`. It emits code and stops.
- **No `supabase status` / `supabase test` / `supabase verify`** documented on the CLI getting-started
  page. Negative finding.

#### Gaps

- **The Dashboard UI is login-gated and NOT observed.** Everything rests on the open-source Studio at
  `master` plus first-party prose.
- `master` may run ahead of production; the `/project/<ref>/api` →
  `/project/<ref>/integrations/data_api/docs` redirect *(source)* suggests active churn in exactly
  this area.
- **Unresolved and worth checking before we copy the pattern:** whether the "Copy prompt" output
  includes real keys. It prefers `data-connect-copy-value`, which for the `.env` step would carry
  real values.

---

### 1.6 Segment

> **Evidence caveat, stated up front.** `segment.com/docs` returns **HTTP 403 to direct fetching**
> (bot protection). The claims below come from **search extracts of segment.com-domain pages** and
> from the **first-party GitHub README** for Typewriter, which was fetchable. Confidence is graded
> accordingly — **no Segment docs page was read directly**, and no dashboard was entered.

#### Q1 — chooses / emits

Two distinct surfaces, and the second is the interesting one.

1. **The `analytics.js` write-key snippet.** The developer chooses a **Source** (a named integration
   in their workspace); the workspace emits the standard `analytics.js` loader snippet for pasting
   into `<head>`. Documented path: *"Navigate to Connections > Sources > JavaScript in the Segment
   app, copy the snippet from the JavaScript Source overview page, and paste it into the `<head>` tag
   of your site."* *(medium-high)*
2. **Typewriter — generate a typed client from the tenant's own Tracking Plan.** *(high — first-party
   README)* This is the strongest structural parallel to a Code Builder in the whole survey after
   Supabase. Input: **a Segment Tracking Plan from your centralized workspace**, via
   `npx typewriter init` → a `typewriter.yml`. Output: **strongly-typed analytics clients** for
   `analytics.js`, `analytics-node`, `analytics-swift`, `analytics-kotlin`. First-party claims:
   *"Generates strongly-typed Segment analytics clients that provide compile-time errors, along with
   intellisense for event/property names, types and descriptions"*; *"Built-in support to sync your
   typewriter clients with your centralized Segment Tracking Plans."*

#### Q2 — known vs supplied, and copy-paste survival

**Segment runs the two-rendering split explicitly: docs show a placeholder, the console shows your
real value.** *(medium-high)*

- **Docs rendering** — the literal placeholder is `YOUR_WRITE_KEY`, with instructions to *"Replace
  YOUR_WRITE_KEY with the actual write key, which you can find in Segment under your project
  settings."*
- **Console rendering** — the JavaScript Source overview page in the workspace shows the snippet with
  **your actual write key already pre-filled**; copying from there requires no substitution.

**Copy-paste survival is good, by the same mechanism as everyone who gets it right:** `YOUR_WRITE_KEY`
is **SCREAMING_SNAKE plain text inside the code block**. It survives the clipboard and fails loudly.
There is exactly **one** value to substitute in the whole snippet, which is why Segment never needed a
richer vocabulary — **a luxury we do not have**, since our four call sites carry a credential, a
`task_id`, tenant-configured registry values, and per-call runtime values.

**Typewriter sidesteps the question entirely** — event and property names are not placeholders at all;
they become **generated function and type names** taken from the Tracking Plan. There is nothing to
substitute because the configured vocabulary is compiled into the API surface. *(high)*

#### Q3 — explanation density

Thin at the snippet tier — the `analytics.js` block is a minified loader with no explanatory comments.
The surrounding docs are a numbered walkthrough. **Typewriter inverts the usual trade-off:** rather
than shipping explanation *beside* the code, it ships it *in the type system* — "intellisense for
event/property names, types and descriptions" means the Tracking Plan's prose descriptions arrive in
the developer's editor as hover text. **That is explanation that survives copy-paste by not being
text at all.** *(high on the mechanism; the docs' prose density was not directly observed)*

#### Q4 — multi-step lifecycle, error and retry

**Not applicable in the lifecycle sense, and worth saying plainly.** Segment's core verbs
(`identify` / `track` / `page` / `group`) are **independent single calls with no handle and no close**
— there is no session to open. Segment is in this survey for its *generation model*, not its shape.

**Retry appears as configuration, not as generated code** — `maxRetries: 3` in the server-side
libraries. Consistent with the industry-wide pattern in §2.5: retry lives in the hand-written
transport layer, never in the emitted sample. *(high)*

#### Q5 — keeping generated code correct

> **Typewriter is the clearest instance in this research of the model that actually fits us:
> generate from the tenant's own configured state, not from the API spec.**

The Tracking Plan is *the tenant's declared vocabulary of events and properties* — structurally the
same thing as our declared `task_types`, `event_types` and dimensions under ADR-0005. Typewriter
compiles that vocabulary into a typed client, and offers *"Built-in support to sync your typewriter
clients with your centralized Segment Tracking Plans."*

It also closes the loop back into CI: *"Validate your instrumentation matches your spec before
deploying to production, so you can fail your CI builds without a manual analytics QA process."*
**Generated-from-config plus a CI gate that fails when instrumentation and config diverge** is a
complete answer to the drift problem that Clerk's non-blocking bot comment fails to solve. *(high)*

#### Q6 — verify your integration

**The Source Debugger — a live tail, and one of the better verify surfaces found.** *(medium-high)*

Documented behaviour: it *"helps you confirm that API calls made from your website, mobile app, or
servers arrive at your Segment source"*, displaying *"a live stream of events arriving at your source
in real time"* — sampled, up to 500 events, each with event name, timestamp and a data summary. A
**Pretty view** *"shows a simplified version of the API call that you made… helps you verify that your
event structure looks correct at a glance"*, and the stream is searchable by event name, user ID, or
any property.

**What it proves and what it does not:** it proves *arrival and shape*. It does **not** show
downstream processing — Segment's own framing is that it lets you *"troubleshoot issues without
waiting for data to process through your pipeline."* For us the equivalent boundary matters: arrival
is the easy half; **rating is the half a metering integrator actually needs.**

#### Gaps

- **No segment.com docs page was read directly** (403). All Segment doc claims are from
  segment.com-domain search extracts.
- **No workspace was entered** — "the console pre-fills your real write key" is documented, not
  observed.
- Typewriter's emitted code was not inspected; only its README claims.
- The Event Tester / "test connections" surface could not be fetched; only the Debugger is
  characterised above.

---

### 1.7 Algolia

Algolia's docs-facing generation pipeline is largely covered in **§2.1 and §2.6**, because it is the
public counter-example to the `x-codeSamples`-is-unused finding. This section covers what is specific
to Algolia as a product.

#### Q1 — chooses / emits

**Negative finding: the public quickstart is a manual copy-the-keys flow, not a code builder.**
*(high — observed)* `algolia.com/doc/guides/getting-started/quick-start/` instructs the developer to
navigate to the dashboard's API Keys page, **copy the credentials themselves**, and paste them into a
local file. The page describes **no dashboard onboarding flow that auto-generates code**, and no
account-specific snippets appear in it.

Where Algolia *does* generate is **the docs themselves** — 11 languages of per-operation snippets, and
a separate corpus of compilable multi-step *guides* (§2.1).

#### Q2 — known vs supplied, and copy-paste survival

**Algolia uses the separate-artifact pattern, in its purest and starkest form.** The quickstart emits
a `.env.local` with **empty right-hand sides**:

```
VITE_ALGOLIA_APPLICATION_ID=
ALGOLIA_WRITE_API_KEY=
VITE_ALGOLIA_SEARCH_API_KEY=
```

*(high — observed)*

This is worth noting precisely because it is the **degenerate case** of the pattern Supabase and Auth0
use well. The good version of separate-artifact (§1.5) interpolates *real values* into the `.env` and
leaves the application code clean. Algolia gets the separation right and then **fills in nothing** —
so the developer receives an artifact that is unambiguous about *what* is needed and silent about
*where to get it*, beyond prose instructions. **An empty value is not a placeholder**: it does not
name itself, it cannot be grepped for, and a partially-filled file is indistinguishable from a
complete one. Contrast Lago's `__MUST_BE_DEFINED__`, which occupies the same slot and says so.

#### Q3 — explanation density

Two tiers, and the split is unusually clean. **Reference snippets are bare** — one operation, no
prose. **The `guides` corpus is the opposite**: hand-written per-language scaffolds with loops,
`try`/`except` and **explicit TODO stubs** where the developer's own code belongs (§2.1). Algolia is
one of the few vendors that maintains a *deliberately* separate, richer corpus for the multi-step case
rather than letting the generated tier be the only tier.

#### Q4 — multi-step lifecycle, error and retry

**No open/report/close lifecycle** — Algolia's operations are index mutations, not sessions.

The relevant asymmetry is between the two corpora, and it is the single most quotable evidence in this
report for the ceiling of spec-driven generation: **the generated snippet corpus contains 0 `except`
and 0 `retry` across 357 KB**, while the hand-written `guides` corpus contains loops, `try`/`except`
and TODO stubs (§2.1). *(high)* **Same vendor, same API, same languages — the difference is entirely
whether a human wrote it.**

Algolia's genuinely lifecycle-shaped concern is **asynchronous task completion** (`taskID` +
`waitForTask`), since indexing is eventually consistent. Whether the generated snippets exercise it
was **not verified** — see Gaps.

#### Q5 — keeping generated code correct

**Generated from OpenAPI, first-party and unambiguous:** *"The Algolia API clients are generated from
OpenAPI specs, leveraging the open-source openapi-generator tool."* *(high)*

The docs-snippet half of the pipeline is characterised in §2.1: **OpenAPI + per-operation test
fixtures → one snippet per `operationId` per language**, emitted into `docs/snippets/`,
`*-snippets.json`, and `x-codeSamples`. Algolia is therefore the **notable public exception** to the
finding that Stripe, Twilio and GitHub all carry **zero** `x-codeSamples` (§2.2) — and the reason it
can afford the extension is that its samples come from a **compiled, end-to-end-tested corpus** rather
than being hand-written per operation.

> **The transferable idea:** Algolia's snippets are correct because they are **test fixtures that also
> happen to render as documentation**. That is a stronger correctness guarantee than any other vendor
> in this survey achieves, and it is available to anyone whose examples are executable.

*(The repo README confirms the OpenAPI→client generation and references the Common Test Suite, but does
not itself spell out the snippet-generation methodology — that detail comes from the repo structure as
recorded in §2.1. Graded medium-high on the snippet half, high on the client half.)*

#### Q6 — verify your integration

Weak, and honestly so. The quickstart's verification is a **terminal-output assertion** — *"You should
see the message `Successfully indexed products.` in your terminal"* — followed by an invitation to
*"explore the `quickstart-products` index in the Algolia dashboard."* **No automated check, no API-log
step, no health endpoint is surfaced in the quickstart.** *(high — observed)* Algolia does ship
**Search API Logs** in the dashboard, but as with Auth0 and Supabase, that surface is not wired into
the onboarding path.

#### Gaps

- **The dashboard was not entered.** Whether Algolia's onboarding (as opposed to the public
  quickstart) emits index-specific code with your real App ID is **unverified**.
- **`waitForTask` / `taskID` polling in generated snippets** — not verified either way.
- The `api-clients-automation` README confirms client generation but not snippet generation; the
  snippet-pipeline detail in §2.1 rests on repo structure rather than a README statement.
- The InstantSearch widget configurator and `create-instantsearch-app` were **not investigated**.

---

### 1.8 Usage-based billing and metering vendors

**This is our own market, and the section that most changed the conclusion.**

| Vendor | Console code builder? | What it emits | Evidence grade |
|---|---|---|---|
| **Lago** | **YES** — live, form-driven | Single `curl` POST, regenerated per keystroke; config interpolated, secrets never | **source** — `lago-front`, `BillableMetricCodeSnippet.tsx`, `snippetBuilder.ts` |
| **Flexprice** | **YES** — two surfaces | Per-feature ingest `curl` with meter config interpolated; plus a 9-language spec-driven drawer | **source** — `flexprice-front`, `FeatureDetails.tsx` |
| **Helicone** | **YES** — onboarding wizard | Provider × method → snippet with **live API key baked in** | **source** — `helicone`, `openAISnippets.tsx` |
| **m3ter** | **YES** — "Submit measurements" panel, 4 tabs | Copyable snippets on the Meter Details page | documented; **interpolation login-gated, unverified** |
| **Chargebee** | **YES — but Checkout/Portal only** | `<head>` script + button code, site name interpolated. **The metered path has none** | documented |
| **Langfuse** | **PARTIAL** — credentials only | `.env` block with real keys; lifecycle links out | **source** — `useLangfuseEnvCode.ts` |
| Metronome | No | Dashboard configures; docs are hand-written curl | documented |
| Orb | No | Pure UI walkthrough, "no code samples" | documented |
| OpenMeter | **Inverted** — docs→console | Deep-link pre-fills the console form *from* a doc example | observed |
| Stigg / Schematic | No | Copy key from Settings. Schematic ships **MCP + agent skills** instead | documented |
| Amberflo | No | — and samples omit the API key **entirely** | observed |
| Moesif | No — portal shows a *field* to copy | `YOUR_MOESIF_APPLICATION_ID`, static | observed |
| Paddle | No | **No placeholder token at all** | observed |
| Recurly | No | `process.env.RECURLY_PRIVATE_KEY` | observed |
| Zuora / Togai | No (Togai is a Zuora property since 2024) | Three inconsistent conventions | documented |

> **Two headlines.**
>
> **(1) The "nobody in usage-based billing ships a code builder" hypothesis is FALSE — four vendors in
> this exact market do.** Lago, Flexprice and Helicone are all verifiable in open source; m3ter's
> panel is documented but gated. Chargebee has one and pointedly **does not apply it to metering**.
>
> **(2) Every single one generates exactly one call site.** Not one platform, in either half of this
> survey, generates a multi-step lifecycle. **That gap is the finding.**

#### The convergence worth building on

Two independent open-source billing consoles landed on **the identical sentinel token** for
not-yet-configured values:

```
Lago       (SnippetVariables.MUST_BE_DEFINED)  →  '__MUST_BE_DEFINED__'
Flexprice  (FeatureDetails.tsx)                →  '__MUST_BE_DEFINED__'
```

Both pair it with `__SCREAMING_SNAKE__` runtime slots — Lago `__EXTERNAL_CUSTOMER_ID__` /
`__UNIQUE_ID__` / `__YOUR_API_KEY__`; Flexprice `__CUSTOMER_ID__` / `__VALUE__`. Both interpolate
**tenant configuration** (meter code, property keys, aggregation field) while leaving **runtime
values** as tokens.

**Independent convergence on a three-class scheme is the strongest design signal in this report:**

1. **Configured** → interpolated literal
2. **Not yet configured** → `__MUST_BE_DEFINED__`, visible inline, so an **incomplete form shows up
   in the code**
3. **Runtime** → `__SCREAMING__` token

Lago goes one better with a placeholder **derived from your own config** — set `field_name: tokens`
and the snippet emits `"tokens": "__TOKENS_VALUE__"`:

```typescript
[fieldName || '__PROPERTY_TO_AGGREGATE__']: fieldName
  ? `__${fieldName.toUpperCase()}_VALUE__`
  : '__DEFINE_A_PROPERTY_TO_AGGREGATE__',
```

Flexprice's ingest builder, verbatim from `FeatureDetails.tsx`:

```
curl --request POST \
--url https://api.cloud.flexprice.io/v1/events \
--header 'x-api-key: <your_api_key>' \
--data '{
	"event_id": "${staticEventId}",
	"event_name": "${data?.meter?.event_name || '__MUST_BE_DEFINED__'}",
	"external_customer_id": "__CUSTOMER_ID__",
	"properties": { "${filter.key}" : "${filter.values[0] || 'FILTER_VALUE'}" },
	"timestamp": "${staticDate}"
}'
```

**Two flaws to avoid:** it mixes `__SCREAMING__` and `<angle>` in one snippet; and it pre-fills
`event_id` with a fresh uuid — **that is the idempotency key, and the snippet never says so.**

#### The dominant failure mode is not a bad placeholder — it is *no* placeholder

Three vendors ship copy-paste-clean, **silently wrong** code:

- **Paddle** — this exact string appears **28 times** on one page, with **zero** `YOUR_…`, `{…}` or
  `<…>` anywhere on it:
  ```js
  Paddle.Initialize({ token: "live_7d279f61a3499fed520f7cd8c08" });
  ```
- **Chargebee's drop-in doc** — `data-cb-site="acme-test"`, a concrete example, served over **`http://`**.
- **Amberflo** — worst in the sweep. The generated reference sample carries **no API key and no
  placeholder for one**, with `"customerId": ""`. `X-API-KEY` appears only in spec metadata, marked
  `"kind":"optional"`; `meterApiName` is absent entirely.

> **A trap that catches automated research, worth recording.** Moesif's docs contain a **real**
> Application Id under `<!-- Start of Moesif Embed Code -->`. That is Moesif instrumenting **its own
> docs site** — not interpolation into your sample. The same applies to a live Amplitude key on
> Recurly's ReadMe-hosted docs. **Neither is evidence of personalization.**

#### Metronome, Orb, OpenMeter — brief

- **Metronome** *(high)*: dashboard is config-only — *"If your engineering team is setting up
  Metronome programmatically, see the API Quickstart."* Two textual classes: `$METRONOME_API_TOKEN`
  for secrets, `<your-customer-id>` for ids. **Best retry prose in the cohort:** *"Always retry a
  failed call to /ingest until you receive a 200"*; and on 4xx, *"Do not automatically retry… put the
  event aside in a dead letter queue."* 34-day dedup on `transaction_id`. Fault injection exists but
  is **human-mediated** — "Contact your Metronome representative."
- **Orb** *(high)*: Stainless SDKs across 8 languages. Ingest returns `{"validation_failed": []}`.
  Strong verify surfaces: metric debugging tab, event trace view, self-serve production-readiness
  checklist.
- **OpenMeter** *(high)*: the **inverse** of a builder — a "Create Meter in Cloud" button deep-links
  config *into* the console (`?meter={"slug":"api_requests_total","aggregation":"COUNT",…}`). OSS repo
  is Go-only, so the Cloud console is **unverifiable**.

#### The multi-step lifecycle hunt — the crux, and a clean negative

**Nothing, anywhere, generates the four-call-site shape.**

| Platform | Generates? | What is actually interpolated |
|---|---|---|
| AWS Step Functions Workflow Studio | Definition only | ASL JSON/YAML; worker code is a hand-written tutorial |
| AWS Console-to-Code | IaC only | CDK/CloudFormation — **Step Functions unsupported** |
| GCP "Equivalent code" | Provisioning only | gcloud / REST / Terraform, from the form |
| Firebase console | Config only | real `firebaseConfig` object |
| Temporal, Inngest | No | nothing |
| Trigger.dev | Credentials only | `TRIGGER_SECRET_KEY="${environment.apiKey}"`; task code is a static const |
| Langfuse | Credentials only | keys + `baseUrl` |
| LiveKit | Credentials, via **CLI** | `lk app create` writes a real `.env.local` |
| Plaid | No | dashboard emits a *config name string* |
| Twilio, Daily, Agora, W&B, MLflow, LangSmith | No | — |

**Console code generation is mature for provisioning and configuration artifacts, and essentially
absent for the developer's own runtime call sites.** Google states the rationale plainly —
*"Generating code can help you learn syntax and prevent errors"* — then applies it only to
gcloud/REST/Terraform.

#### Closest analogues to our shape

> **1. Temporal's `hello_async_activity_completion.py` — our exact four-call-site shape, hand-written,
> in one runnable file.** `get_async_activity_handle(task_token)` → `await handle.heartbeat()` ×N →
> `CancelledError` → `await handle.complete(...)`.
>
> **The load-bearing line is a comment in Temporal's own sample:** *"Heartbeat is how cancellation is
> delivered from the server."*
>
> **The stop signal rides the report channel — call sites (2) and (3) can be one call.** This is
> exactly UBB's design (`stop` rides the `record_usage` ack), independently arrived at, and it is the
> single most useful structural confirmation in this research.

2. **Helicone's `manualLogging`** — the only *generated* multi-step snippet found anywhere, and it is
   three lines with the developer's own work marked by a comment:
   `logger.registerRequest(reqBody);` → `// Call OpenAI using JS SDK / fetch` → `logger.sendLog(res);`.
   **No abort path.**
3. **Langfuse's `getLangfuseEnvCode(baseUrl, keys?)`** — one rendering function, two branches:
   interpolate keys when known, `sk-lf-…` when not, `baseUrl` in both. **Prevents docs and console
   snippets drifting apart** — the exact failure Clerk's non-blocking bot comment fails to prevent.
4. **LiveKit's `.env.example` → `.env.local`** — the CLI overwrites only keys it knows, "preserving
   any inline comments and the surrounding whitespace." One template serves manual and generated paths.

#### The stop signal — the least-charted call site in the entire survey

**No vendor emits a stop-signal branch in generated code.** What exists, in prose or hand-written
samples:

- **Stigg — closest to our shape.** `reportUsage` returns the balance **on the report call**:
  `{"measurementId": "…", "credit": {"currentUsage": 3500, "usageLimit": 10000}}`, documented as
  *"strict, real-time credit enforcement."* Fallback is explicitly **fail-open** —
  `entitlementsFallback: { 'feature-templates': { hasAccess: true, usageLimit: 10 } }` with an
  `res.isFallback` flag — but provisioning is fail-closed: *"Ensure customers are not allowed to
  allocate new resources until an acknowledgement about the processed measurement is received."*
- **OpenMeter — cleanest gate sample.**
  `const { hasAccess, balance, usage, overage } = value; if (!hasAccess) { return reply.status(402)… }`
- **Togai — the only in-band check found anywhere.** An endpoint literally named *"Ingest event if a
  user is entitled to a feature"* — report and authorize in one call.
- **Orb — documents the pattern in prose with *no sample code*, and argues against the synchronous
  check.** *"Sending messages is performance critical, so it's not possible to incur the latency of
  checking the customer's current balance before each message send"* — instead maintain your own
  `messages_blocked_until` field, re-queried on a balance-depleted webhook. **You build the state
  machine from scratch.**
- **Elsewhere it is declarative, not a call site:** ASL `Catch`, Inngest `cancelOn`, Trigger.dev
  `tasks.onCancel({ signal })`, MLflow's `KILLED` terminal status.
- **Plaid alone admits its abort hook is unreliable:** *"onExit will not be called when Link is
  destroyed in some other way than closing Link, such as the user hitting the browser back button."*

#### Q2 for this cohort — ranked by robustness, all observed literally

| Convention | Example | Survives paste |
|---|---|---|
| Bare undefined identifier | `withActivityArn(ACTIVITY_ARN)` | **Yes — won't compile.** Strongest |
| Double-underscore caps | `__MUST_BE_DEFINED__`, `__CUSTOMER_ID__` (Lago, Flexprice) | **Yes** — greppable, breaks loudly |
| Double-brace caps | `{{OPENAI_API_KEY}}`, `{{CUSTOMER_ID}}` (Helicone, Stripe) | **Yes** |
| Angle brackets + comment | `<your-project-ref>, // e.g., "proj_abc123"` (Trigger.dev) | **Yes.** Best DX |
| Shell env var | `$METRONOME_API_TOKEN` | **Yes**, runnable after one `export` |
| Plausible fake value | `acme-test`, `"sample-customer-123"` | Yes but **runs and fails silently** |
| Nothing at all | `token: "live_7d279f61a3499fed…"` (Paddle) | **Actively harmful** |
| **CSS class / colour only** | `class="replaceable"` (AWS); green diff lines (Helicone) | **NO — destroyed** |

> **The verified failure mode: guidance dies at the clipboard.** Lago strips its own `#` comments on
> copy — `copyToClipboard(code, { ignoreComment: true })`. Helicone copies the diff-free string —
> `navigator.clipboard.writeText(props.code)`. AWS marks replaceables in CSS. **Three products, three
> mechanisms, one outcome: only the tokens survive.** *(high — source)*

#### Q3 for this cohort

Bare-to-thin everywhere. Lago ships a title comment plus one footer line — **and strips both on
copy**. Nothing in the survey ships an annotated walkthrough *inside* generated code. Where
integrations are genuinely stateful, presentation splits two ways: **one complete runnable file with
comment-marked seams** (Temporal — the better model) or **one snippet per doc page** (Plaid, Inngest,
AWS).

> **Note how the "which lines to add" affordance collapses exactly when the integration becomes
> multi-call-site.** Helicone's diff line-numbers are hand-maintained (`typescript: [4, 6]`,
> `curl: [0, 2]`) — and the two lifecycle-shaped snippets have **empty arrays**: `asyncLogging: []`,
> `manualLogging: []`. **You cannot express "add these lines" for code that spans a codebase.** *(high
> — source)*

#### Q5 for this cohort

Confirmed from marker files in each SDK repo:

| Generator | Vendors |
|---|---|
| **Stainless** (`.stats.yml`, `api.md`) | Orb, Metronome, m3ter |
| **Fern** (`.fern`, `.fernignore`) | Schematic |
| **Speakeasy** (`.speakeasy/workflow.yaml`) | Flexprice |
| **OpenAPI Generator** (`.openapi-generator-ignore`) | Togai |
| **In-house / hand-written** | Chargebee, Recurly, Paddle, Moesif, Amberflo, Lago |

**But the code *builders* use none of this.** Lago's is hardcoded TS with **no assertion on output** —
the page test `jest.mock`s the snippet component and asserts only that the panel exists. Flexprice's
spec-driven drawer **emits a curl with no `x-api-key` header at all**, and syntactically invalid PHP
(`"Content-Type: "application/json"`). **If you synthesize N languages, snapshot-test all N.**

The emerging answer to *account-specific* correctness is **MCP + agent skills, not a builder**:
Schematic's `schematic-mcp` (*"AI assistants can query your actual Schematic data to generate accurate
integration code"*), Lago's `lago-agent-toolkit` (40 tools), Metronome's `@metronome/mcp`, plus
`npx skills add chargebee/ai`.

#### Q6 for this cohort — ranked

- **Rated preview — the high bar, met exactly once.** **Lago's `POST /events/estimate_fees`** takes
  `{"event": {"external_subscription_id": "…", "code": "__BILLABLE_METRIC_CODE__", "properties": {…}}}`
  and **returns computed fees with taxes and totals without persisting the event.** The only "POST an
  event, see the price" endpoint found anywhere. *(high)*
- **Test-submit beside the snippet — the benchmark.** m3ter's Submit-measurements panel does a live
  submit and shows `{ "result" : "accepted"}` in a Log, backed by an Activity panel with 24h counts.
  Its documented caveat is a trap worth copying *away* from: *"the API response refers to the
  pre-enrichment stage"* — **duplicates are accepted, then deduplicated and notified later.**
- **Parse-and-match echo.** Lago's Devtools drawer shows each payload, the matched
  `billableMetricName`, and two warnings verbatim: *"This event code doesn't match an existing
  billable metric"* / *"The property sent doesn't match the one used to aggregate your billable
  metric."*
- **Aggregation preview.** Orb's metric debugging tab; a continuously-maintained draft invoice.
- **Waiting-for-first-event.** Langfuse polls `hasTracingConfigured` every 5s behind *"Waiting for
  first trace."*
- **State forcing.** Only Plaid ships endpoints to push your integration into failure on demand
  (`/sandbox/item/reset_login`, `/sandbox/item/fire_webhook`).

> **Nobody puts the verify surface beside the generated code.** Chargebee has an API Explorer, Paddle
> a sandbox, Moesif a Live Event Log, m3ter the closest thing — **but the snippet and the proof it
> worked live on different screens.**

#### Gaps

- **No dashboard was entered.** Where the answer mattered, first-party source was read instead:
  `getlago/lago-front`, `flexprice/flexprice-front`, `Helicone/helicone`, `langfuse/langfuse`,
  `triggerdotdev/trigger.dev`, `livekit/livekit-cli`, `temporalio/samples-python`. Those findings are
  definitive, not inferential.
- **m3ter's interpolation is the one open question worth chasing ourselves** — the panel demonstrably
  exists and is meter-scoped, but the docs never state whether orgId / meter code / token are
  pre-filled.
- **Moesif's onboarding wizard** and **Recurly's ReadMe key-sync** — both have the capability; whether
  either uses it is login-gated.
- **OpenMeter Cloud console** — OSS repo is Go backend only. Unverified.
- **Chargebee's "Grab Script" output** — docs show a GIF, not text. Separately, the "API docs show
  your own site when logged in" claim **does not hold on the current docs** *(medium-high;* `{site}`
  ×11 in raw HTML, no personalization strings*)*.
- **Confidence caveat:** the fetcher renders to Markdown, so JS-driven API playgrounds would not
  appear. Treat "no interactive playground" for Metronome/Orb as **low confidence**; quoted static
  text is high confidence.

---

## 2. The generation architecture everyone shares — and its ceiling

This section is the most important structural result of the research, and it is independent of any
one vendor.

**Five major platforms converge on one architecture:** *spec → per-endpoint example fixture →
per-language single-call emitter.* And they all hit the same ceiling.

### 2.1 The mechanisms, and what each cannot express

| Mechanism | Input | Output | **Cannot express** |
|---|---|---|---|
| **Algolia CTS → snippets** | OpenAPI + per-operation test fixtures | 1 snippet per `operationId` per language (11), into `docs/snippets/`, `*-snippets.json`, and `x-codeSamples` | Any second call; **0 `except` / 0 `retry` in 357 KB** *(high)* |
| **Algolia CTS `guides` → mustache** | Hand-written per-language scaffold + fragment table with `$var:` bindings | Compilable multi-step programs with loops, `try`/`except`, TODO stubs | Anything not hand-authored; cross-tier handoffs drop to prose *(high)* |
| **Stripe** | `stripe/openapi` public spec (itself the artifact of a *closed* generator) | 9 language tabs × 2 API flavors on `docs.stripe.com/api/*`; SDKs marked `# File generated from our OpenAPI spec` | Init + exactly one call, across all 24 samples on the Customers page *(high)* |
| **Twilio** | `twilio/twilio-oai` + standard OpenAPI **named `examples`** | 9 languages × 12 code groups per API-reference page; SDKs via the **public** `twilio-oai-generator` | One call. The `examples` keys are *alternatives*, not steps *(high)* |
| **GitHub** | `github/rest-api-description` + named `examples` | curl / `gh` CLI / Octokit.js tabs, emitted by `github/docs` `src/rest` | Structurally single-request — visible in the emitter's `return` *(high)* |
| **`x-codeSamples`** | `{lang, label, source}` on an **Operation Object** | A code panel beside one operation | **Nowhere to attach a sample spanning two operations** *(high)* |
| **Kong `httpsnippet`** | "a JSON object that represents an HTTP request in the HAR Request Object format" | "executable code that sends the input HTTP request" — 19 targets | `new HTTPSnippet(source: HarRequest \| HarEntry)` → `.convert(...)`: **one request in, one snippet out** *(high)* |
| **`postman-code-generators`** | "a Postman SDK Request Object" | "a code snippet of chosen language" — ~32 language/variant pairs | Same: one Request → one snippet *(high)* |
| **OpenAPI Generator** | OpenAPI document | A client SDK, one method per operation | The document has **no notion of call ordering or inter-operation data flow** *(high)* |
| **OAI Arazzo Specification** | OpenAPI/AsyncAPI + a workflow document | Machine-readable **sequences** with dependencies | — (built to fill exactly this gap) |

### 2.2 `x-codeSamples` is not how the big three do it

**The `x-codeSamples` count is ZERO in Stripe's, Twilio's, and GitHub's specs.** *(high)* Counted
programmatically across `stripe/openapi` (public, SDK, and `/latest/`), `twilio_api_v2010.json`, and
`api.github.com.json` — a string search for `codeSample` / `x-code` / `snippet` returns 0 in all
three. The industry's best-known docs-sample extension is **not** how the three biggest API doc sites
work. Algolia is the notable public counter-example that *does* use it, filled from a compiled,
end-to-end-tested corpus.

What the specs carry instead is **SDK-shape metadata** — the missing link that lets a generator emit
`stripe.Customer.create(...)` rather than raw HTTP:

```json
"x-stripeResource": {"class_name": "Customer", ...}
"x-stripeOperations": [
  {"method_name": "create", "method_on": "service", "method_type": "create",
   "operation": "post", "path": "/v1/customers"},
  {"method_name": "update", "method_on": "service", "method_type": "update",
   "operation": "post", "path": "/v1/customers/{customer}"}
]
```

Counts — Stripe SDK spec: `x-stripeMostCommon` 4291, `x-expandableFields` 1824, `x-stripeOperations`
130. Twilio: `x-twilio` 190 (carrying `className`, `mountName`, `pathType`, plus a PII policy
`{"pii": {"handling": "sensitive", "deleteSla": 30}}`). GitHub: `x-github` 1487, documented as
*"Provides extra information used to generate Octokit SDKs."* *(high)*

### 2.3 GitHub's pipeline is public end to end — and worth studying

- `github/docs/src/rest/README.md`: *"Our REST pipeline creates autogenerated REST API documentation
  for docs.github.com/rest from the OpenAPI stored in the open-source repository
  `github/rest-api-description`."*
- **Stage 1**, `src/rest/scripts/utils/create-rest-examples.ts` — merges request↔response by matching
  example key. **The type is the whole argument:**

  ```ts
  export interface MergedExample {
    request: { contentType?, description, acceptHeader, bodyParameters?, parameters? }
    response?: { statusCode, contentType?, description, example?, schema? }
  }
  ```

  **One request. One response. No slot for a second call.**
- **Stage 2**, `src/rest/components/get-rest-code-samples.ts` — three emitters, each ending in a
  single string concatenation:

  ```ts
  return `${comment}${authString}await octokit.request('${operation.verb.toUpperCase()} ${operation.requestPath}${queryParameters}', ${stringify(parameters, null, 2)})`
  ```
- **Stage 3** — `content/rest/issues/issues.md` is frontmatter plus
  `<!-- Content after this section is automatically generated -->`, with
  `versions: # DO NOT MANUALLY EDIT. CHANGES WILL BE OVERWRITTEN BY A 🤖`.

> **Two findings from GitHub's pipeline bear directly on our Q2 and Q4.**
>
> **1. Placeholder generation is automated, with the rationale stated in the code comment** — the
> cleanest statement of the known-vs-supplied problem found anywhere:
>
> ```ts
> // If there are no examples, create an example from the uppercase parameter
> // name, so that it is more visible that the value is fake data in the route path.
> parameterExamples.default[parameter.name] = parameter.name.toUpperCase()
> ```
>
> That is why `docs.github.com` renders `curl -L -X POST
> https://api.github.com/repos/OWNER/REPO/issues`. **Uppercasing the parameter name is a rule, not a
> per-sample decision** — and it works for exactly the reason every other text convention works: it
> is text.
>
> **2. Error handling is architecturally excluded, on purpose:**
>
> ```ts
> // We don't want to create examples for error codes
> // Error codes are displayed in the status table in the docs
> if (parseInt(statusCode, 10) >= 400) continue
> ```
>
> 4xx/5xx are routed to a status table, deliberately out of the sample. *(high)*

### 2.4 Twilio proves the spec→sample link forensically

The API-reference page's example dropdown options **are** the OpenAPI example keys:

```html
<option value="create" selected>create</option>
<option value="createWithMessagingService">createWithMessagingService</option>
<option value="createScheduledMessageSms">…</option>
```

matching `requestBody.content['application/x-www-form-urlencoded'].examples` in
`twilio_api_v2010.json`. *(high)* **Note the shape of the affordance: seven *ways to make the same one
call*, selected by a dropdown. The format has no way to say "then."**

Stripe's equivalent inference is strong but not confessional: all 9 language tabs for an endpoint
carry **identical literal values** (`sk_test_<redacted>`, `Jenny Rosen`, `limit=3`,
`metadata[order_id]=6735`), and prior-object ids are template tokens:
`stripe.Customer.retrieve("{{CUSTOMER_ID}}")`. *(medium-high that they are generated; high that it is
one parameter fixture rendered through per-language emitters)*

### 2.5 Retry and transport live in hand-written code, never in the emitted sample

`stripe-python/CONTRIBUTING.md`: *"To identify files with purely generated code, look for the comment
`File generated from our OpenAPI spec.`"* Their agent file adds: *"The HTTP client layer
(`_http_client.py`, `_stripe_client.py`, `_api_requestor.py`, `_client_options.py`) is **NOT**
generated."* *(high)*

Twilio's **Go** samples carry `if err != nil { fmt.Println(err.Error()); os.Exit(1) }` — but this is
absent from Node/Python/Ruby/PHP/Java, so it is **language furniture emitted by a template, not a
scenario decision**. *(high)* Segment's equivalent is `maxRetries: 3` — a config number. Algolia's Go
snippets have `panic(err)` only.

### 2.6 Everyone falls back to a separate, hand-written, multi-step corpus

*(This is the finding that most directly predicts what we will have to do.)*

- **Stripe** — [`github.com/stripe-samples`](https://github.com/stripe-samples), **30 public repos**.
  `accept-a-payment/prebuilt-checkout-page/server/` carries 8 hand-maintained per-language
  implementations. The Node one contains everything the generated samples cannot: **two chained calls
  threading `taxCalculation.amount_total` into `paymentIntents.create`, a branch, a `try/catch`, and
  an async `/webhook` arm with `constructEvent` signature verification.**
- **Twilio** — separately-maintained narrative snippets, using *different literal values* from the
  spec-driven pane. **Two sample systems on one page.**
- **GitHub** — `content/rest/guides/` pointing at runnable code in `github/platform-samples`. **The
  tell:** the discovering-resources guide's very first code line is `Octokit.auto_paginate = true` —
  pagination, the exact multi-request pattern the generated emitter cannot express, is the first
  thing the hand-written guide must teach.
- **Segment** — serverless setup / flush samples. **Algolia** — mustache guides.

### 2.7 The decisive structural evidence: Arazzo had to be invented

The OpenAPI Initiative's **Arazzo Specification** (v1.1.0,
[github.com/OAI/Arazzo-Specification](https://github.com/OAI/Arazzo-Specification)):

> *"The Arazzo Specification defines a standard, programming language-agnostic mechanism to **express
> sequences of calls and articulate the dependencies between them** to achieve a particular
> outcome…"*

with stated use cases including *"**code and SDK generation driven by functional use cases**"*, and an
object model that is **exactly the vocabulary a four-call-site lifecycle needs and OpenAPI lacks**:
Workflow Object, Step Object (including *"Step Dependencies and Execution Order"*, *"Defining Success
for Asynchronous Steps"*, *"Use Case: Async Coordination"*), Success Action, Failure Action,
Criterion, and Runtime Expressions for threading step N's output into step N+1's input.

**That a sibling specification had to be created to say these things is the proof that OpenAPI +
`x-codeSamples` + httpsnippet cannot.** *(high)*

> **Stated plainly, because it matters and no vendor says it out loud:** *no vendor anywhere states
> "our generated samples cannot express multi-call flows."* The claim is **structural** — read off
> data models, emitter return statements, output corpora, and Arazzo's existence — **never
> confessional**. We should not imply a quote exists.

---

## 3. The six questions, answered

**Q1 — who ships one, and what does it emit?**
More vendors than expected, and the emitted artifact varies more than the input does. Three shapes:
**(a) a snippet** — one call, language-tabbed (Stripe/Twilio API reference, Lago, Flexprice,
Helicone, Supabase API docs); **(b) a config file** — a pre-filled `.env`, which is the *only* thing
Auth0's Quick Setup, LiveKit, Langfuse and Trigger.dev emit; **(c) a project** — a runnable multi-file
scaffold (Stripe's `IntegrationBuilder`, Auth0's "Download Sample", Twilio's `serverless:init`,
CodeExchange Quick Deploy). What the developer *chooses* is nearly always **language × framework ×
scenario**, and — critically for us — at Lago, Flexprice and Supabase, **a resource they already
configured** (a billable metric, a feature, a table).

**Q2 — known vs supplied, and copy-paste survival.**
Four strategies, ranked by how well they survive the clipboard:

| Strategy | Vendors | Verdict |
|---|---|---|
| **Separate the artifact** — real values in `.env`, code reads by name | Supabase Connect, Twilio, Auth0 Quick Setup | **Best.** Nothing to substitute; also the correct production pattern |
| **Text-encoded token classes** | Stripe (`<<X>>` vs `{{X}}`), Lago/Flexprice (`__MUST_BE_DEFINED__` vs `__CUSTOMER_ID__`), GitHub (`OWNER`/`REPO`) | **Strong**, and the only way to say "not configured yet" |
| **Interpolate real values inline** | Clerk (`{{pub_key}}` → clipboard), Stripe's shared test key | **Works, but** the result is indistinguishable from hand-typed config |
| **Plausible fake value, or nothing** | Twilio `from_`/`to`, Chargebee `acme-test`, Paddle, Amberflo | **Fails silently.** The dominant failure mode |
| **CSS / colour / tooltip only** | AWS `class="replaceable"`, Helicone diff highlighting | **Destroyed by copy-paste.** Never do this |

The distinction survives copy-paste **only when it is in the text**. Every vendor that got this right
did so with a naming or bracket convention; every vendor that put it in styling lost it. And a
convention **needs a legend** — Auth0 proves that an undocumented rule decays across a docs rewrite.

**Q3 — how much explanation ships with the code?**
Three tiers, and **density tracks statefulness at Stripe but nowhere else.** Reference snippets are
bare everywhere. Guided quickstarts carry prose *beside* the code — which means **the explanation is
exactly what is lost on copy-paste**. Inline comments appear only in project-scaffold tiers, and even
then Lago strips its own on copy. Where the integration is genuinely stateful, the two presentations
that work are **one complete runnable file with comment-marked seams** (Temporal) or **a numbered
prose contract before any code** (Clerk custom flows). Notably, Twilio's density does *not* increase
for its most lifecycle-shaped products — Verify and Video Rooms get the same bare treatment as
single-call SMS.

**Q4 — multi-step lifecycle, error and retry.**
**Thin to absent, exactly as the ticket predicted.** No vendor generates open → report → close with a
threaded handle. The nearest four: Stripe's Prerequisites graph (real dataflow binding, machine-only,
setup-not-lifecycle); Supabase Realtime (named schema-derived handle, **no unsubscribe emitted**);
Clerk custom flows (`status` discriminant + explicit `finalize()`, hand-written); Helicone's
`manualLogging` (three lines, no abort path). Error handling appears **only in guided quickstarts,
never in reference snippets**. Idempotency is pushed into a **domain field** (Stripe `identifier`,
Metronome `transaction_id`) rather than generated retry code. **The stop signal is the single
least-charted call site in the entire survey — no vendor emits one.**

**Q5 — how is generated code kept correct?**
Three models, and they solve different problems. **(a) Spec-driven** — mechanically correct, and
pedagogically useless: Auth0's spec-generated reference emits `sort: "sort", q: "q"`. **(b) Live
tenant state** — Supabase parameterises hand-written templates with a Swagger doc introspected from
your running database, making table/column drift **impossible by construction** while leaving API-shape
drift unguarded. **(c) Hand-maintained** — everything pedagogically good, and everything that drifts.
Auth0's docs and sample repos have visibly diverged in production *today*; Clerk's console quickstarts
are a **hand-synced second copy guarded only by a non-blocking bot comment**. The one clean answer to
docs-vs-console drift found anywhere is Langfuse's `getLangfuseEnvCode(baseUrl, keys?)` — **one
rendering function, two branches, both surfaces**.

**Q6 — verify your integration.**
Ranked by what they actually prove:
1. **Rated preview** — Lago's `estimate_fees`: post an event, get the computed fee, nothing persisted.
2. **Platform-side round trip** — Auth0's "Try Connection": runs the real flow with **your app out of
   the loop**, so a failure *bisects the problem*.
3. **Send-and-see beside the config** — m3ter's submit panel, Supabase's Edge Function Test.
4. **Parse-and-match echo** — Lago's Devtools: "This event code doesn't match an existing billable
   metric."
5. **Local relay** — `stripe listen`, `clerk webhooks listen`.
6. **Synthetic events with side effects** — `stripe trigger` (creates real objects).
7. **Waiting-for-first-event polling** — Langfuse's `hasTracingConfigured`.
8. **Wiring checks** — `clerk doctor` (never attempts a round trip).
9. **Prose assertions** — Auth0's "Checkpoint". Proves nothing mechanically.

---

## 4. What transfers to UBB's four call sites — and what does not

Our shape, restated concretely (`docs/spend-control-integration.md`, `openapi/v1.json` @ `27efac5`):

| # | Call site | Surface | Lives in the developer's… |
|---|---|---|---|
| 1 | **start work** | `POST /billing/pre-check` `{start_task: true}` → `task_id`, `allowed`, `reason` | job/workflow entry point |
| 2 | **report usage** | `POST /metering/usage` carrying `task_id` + `idempotency_key`, N times | inner loop, per provider call |
| 3 | **handle a stop** | **not a call** — `stop`/`stop_reason`/`stop_scope` ride (2)'s ack; webhooks catch idle workers | a branch at a safe cancellation boundary |
| 4 | **complete work** | `POST /metering/tasks/{task_id}/close` | `finally` / completion handler |

### What transfers

**1. The three-class value model, and it is already validated by our market.** Lago and Flexprice
independently converged on **configured / not-yet-configured / runtime**, all encoded in text. It maps
onto us exactly, and the middle class matters most because of map #137 constraint 5 — *tenant defines
everything, registries start empty*:

- **Configured** (interpolate literally): base URL, `task_type` and `event_type` from the tenant's
  declared registries, `provider`, declared dimension keys, the plan's metric names.
- **Not yet configured** → `__MUST_BE_DEFINED__`. **An empty registry should be visible in the emitted
  code**, not silently absent. This is the single most transferable idea in the report.
- **Runtime** → `__EXTERNAL_CUSTOMER_ID__`, `__UNITS__`, `__IDEMPOTENCY_KEY__`.

**2. Stripe's two-class bracket vocabulary, for the credential/resource split.** We have both classes
and currently mark them inconsistently. Our console today emits
`Authorization: Bearer ubb_live_xxxxxxxxxxxxxxxxxxxxxxxx` in one place
(`apps/ui/src/features/developers/components/api-basics-card.tsx`, commented "never a real key") and
`Authorization: Bearer ubb_test_YOUR_SANDBOX_KEY` in another
(`apps/ui/src/features/developers/lib/test-event.ts`), while injecting the base URL for real via
`apiOrigin()`. **We already make the known-vs-supplied distinction, inconsistently, in exactly the
place this research is about.** Pick one vocabulary and publish the legend.

**3. Supabase's separate-artifact pattern, for the Python target specifically.** Emit a `.env` tab
with the real base URL (and, if we choose to, a real sandbox key) plus a `main.py` that reads
`os.environ[...]` and contains **no credential and no placeholder**. Twilio reaches the same place
independently. Note Supabase's own asymmetry as the warning: their **Python snippet is
copy-paste-runnable and their curl for the same key is copy-paste-broken** — and **curl is one of our
two targets**, so this is a live trap, not a hypothetical one.

**4. Temporal's structural confirmation that (2) and (3) are one call.** *"Heartbeat is how
cancellation is delivered from the server"* is our design, arrived at independently by a mature
workflow engine. It justifies emitting call sites 2 and 3 as **one code block with a branch**, not two
— and Stigg (`reportUsage` returns the balance) and Togai ("ingest event if a user is entitled")
corroborate from inside the billing market.

**5. One rendering function, two branches — Langfuse's answer to drift.** `getLangfuseEnvCode(baseUrl,
keys?)` serves docs and console from one function. Clerk's non-blocking bot comment is the
counterexample of what happens otherwise. If our Code Builder and our docs both show integration code,
**they must be the same function**.

**5a. Generate from the tenant's declared vocabulary, and gate it in CI — Segment's Typewriter.** A
Tracking Plan is structurally the same object as our declared `task_types`, `event_types` and
dimensions (ADR-0005): *the tenant's own declared vocabulary*. Typewriter compiles it into a typed
client whose function names, types and **hover documentation** come from the plan — explanation that
survives copy-paste **by not being text at all** — and then closes the loop: *"Validate your
instrumentation matches your spec before deploying to production, so you can fail your CI builds
without a manual analytics QA process."* Generated-from-config **plus** a CI gate that fires when
instrumentation and config diverge is the most complete answer to drift found anywhere.

**5b. Make the examples executable — Algolia's snippets are test fixtures that also render as docs.**
Same vendor, same API, same languages: **0 `except` and 0 `retry` across 357 KB of generated snippets**
versus loops, `try`/`except` and TODO stubs in the hand-written guides. The generated tier is correct
*because* it is compiled and run; the rich tier is rich *because* a human wrote it. **We will need both
tiers too, and should not pretend one can do the other's job.**

**6. Twilio's annotated `.env` as a config *schema*.** `# format: phone_number`, `# required: true`,
`# configurable: false` compiling to a manifest that drives the web form, the CLI prompt *and* the
local file is the cleanest known-config model found. Our declared dimensions and task-type registries
(ADR-0005) are already this shape.

**7. Lago's `estimate_fees` is the verify surface we should want.** Post an event, get the computed
fee back, persist nothing. We are a *pricing* platform — "did it arrive?" is table stakes; **"what did
it cost, and which rate matched?"** is the question a metering integrator actually has. Our
`RecordUsageResponse` already carries `pricing_provenance` and `uncosted_metrics` — most of the
ingredients exist.

**8. Symptom-indexed troubleshooting** (Auth0's rewritten quickstarts) — map exact error strings to
exact causes. Our natural entries: duplicate `idempotency_key`, unknown `customer_id`, undeclared
dimension → 422, closed task, `allowed:false` with each `reason`.

**9. Both agent-facing patterns.** Stripe writes **different instructions for humans and agents on the
same page** (`PlaintextOnly`), Clerk serves a CLI recipe under `Accept: text/markdown`, and Supabase
ships "Copy these steps for your coding agent". Given map #137's Python + curl targets and the reality
that much integration code is now written by agents, **a "copy for your coding agent" output is
cheap and well-precedented.**

### What does not transfer

**1. Spec-driven snippet generation cannot produce our output. This is the load-bearing negative.**
§2 establishes that the entire industry's generation architecture is *spec → per-endpoint fixture →
single-call emitter*, and that it cannot express a second call, control flow, or error handling —
proven structurally by GitHub's `MergedExample` type (one request, one response, no slot for a second
call), by `httpsnippet`'s `HarRequest → snippet` signature, and by Arazzo having to be invented. **Our
Code Builder is four linked call sites with a branch. `openapi/v1.json` cannot generate it.** Worse for
us specifically: the Code Builder would emit against `ubb-sdk`'s **hand-written** ergonomic layer
(`ubb/metering.py`, `ubb/billing.py`, `ubb/retry.py` — ~1,470 lines), not the 361 generated files in
`ubb/_core/`. **The spec keeps `_core` correct and cannot keep the Code Builder correct.** Plan for
hand-maintained templates under **snapshot tests**, and note Flexprice's warning: their spec-driven
drawer emits curl with no auth header and syntactically invalid PHP — **if you synthesize N languages,
test all N**.

**2. "Personalize the snippet with the signed-in tenant's real values" transfers only partially, and
the ceiling is lower than it looks.** Clerk and Stripe both do it, but both are injecting *one
credential* into *one call*. Our four call sites are separated by **the developer's own business
logic**, which we cannot generate, and the identifier that matters — `task_id` — **does not exist at
generation time**. It is created at runtime by call site 1. No amount of console knowledge can
interpolate it. The most we can do is name the variable and show it flowing; Auth0's auth flow is the
cautionary case, where the SDK hides the correlating identifier and therefore **the quickstart never
teaches the one hard thing**.

**3. Line-level "add these lines" affordances do not survive our shape.** Helicone's hand-maintained
diff line-numbers are populated for single-call snippets and **empty for exactly its two
lifecycle-shaped ones** (`asyncLogging: []`, `manualLogging: []`). You cannot express "insert at line
4" for code that spans four locations in someone else's codebase. **Our unit of emission must be a
named seam** ("at the top of your job handler", "in your per-provider-call loop"), not a line range.

**4. The single-artifact copy button.** Every builder found emits one blob with one copy button.
Four call sites in different files need **four separately-copyable blocks, each labelled with where it
goes** — closer to Supabase's `MultipleCodeBlock` file tabs than to any snippet panel.

**5. Auth0's "download a pre-configured sample" is the wrong shape for us.** It works because the
sample *is* the app. Our tenants are instrumenting an application that already exists; a runnable
scaffold is not the artifact they need.

**6. Retry code.** The industry consensus is that retry lives in the hand-written transport layer, not
in emitted samples (`stripe-python`'s `_http_client.py` is explicitly not generated). **We already have
`ubb/retry.py`.** Emitting retry logic would duplicate the SDK. What we should emit instead is the
**one-rule contract in a comment** — non-200 means not recorded, so retry the whole request; the
idempotency key makes replay safe — which is Metronome's prose guidance, moved into the code where it
survives copy-paste.

### Open questions this research cannot settle

1. **Do we interpolate a real API key?** Stripe injects a *shared sandbox* key that works
   (`is_merchant_key:false`); Clerk injects *your real* key and its masking is presentational only;
   Twilio and Supabase-in-code refuse and use `os.environ`. Our console currently refuses. This is a
   security decision, not a research finding.
2. **Where does the stop-branch live in emitted code?** Our runtime recipes differ per framework
   (Inngest `cancelOn`, Temporal `workflow.cancel()`, LangGraph node boundary, Celery `revoke`). Do we
   emit one generic branch, or a framework picker? No vendor offers a precedent — **this would be
   genuinely novel.**
3. **Does the builder emit the webhook handler at all** (the fifth surface, which catches idle/sibling
   workers)? Including it makes the output honest and much longer.
4. **Is `POST /billing/pre-check` the right shape to teach?** Call site 1 lives in the *billing*
   namespace while 2 and 4 are *metering*, and there is no `POST /metering/tasks`. Emitted code will
   make that seam visible in a way prose currently does not.
5. **m3ter's interpolation behaviour** — the one external fact worth chasing directly, since it is the
   closest analogue that is login-gated.
