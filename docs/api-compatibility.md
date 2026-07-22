# UBB API — the v1 compatibility promise

> **This is the public compatibility contract for the UBB `/v1/` API.** It states, in
> plain terms, what may change without warning, what may never change silently, and how
> much notice you get when something must go. It binds from the **launch tag** — the
> `openapi/v1.json` revision tagged at self-serve launch (ADR-003 §5). The internal
> rationale lives in [ADR-003](adr/0003-versioning-and-deprecation.md); this page is the
> version we make to you.

You are putting UBB between your agents and your Stripe account. You need to know the
ground won't move under an integration you can't redeploy on our schedule. Here is the
deal.

## 1. The API only gains things — additive changes ship with no notice

Day to day, `/v1/` grows and never shrinks. Any of these can appear at any time, and a
well-built client must not break when they do:

- **new endpoints;**
- **new optional request parameters and fields** (always with a safe default — omitting
  them keeps the old behaviour);
- **new response fields;**
- **new webhook event types;**
- **new values in existing status-like (enum) fields** — see §2.

None of these require a version bump, an email, or any action from you.

## 2. Treat the unknown gracefully — this is your side of the deal

Because the API grows without notice, your client must tolerate what it hasn't seen:

- **Unknown response fields:** ignore them. Never reject a payload for carrying a field
  you don't recognise.
- **Unknown enum values:** every status-like field is **open-world**. A `status`,
  `type`, or `reason` you don't recognise means "some newer value" — handle it as an
  "other"/default branch, never as a crash or a hard failure. There is no field we
  promise is a complete, closed list.

Our own generated SDK is built this way (string-backed enums with fallback members, never
strict deserialization). If you hand-roll a client, mirror it. Code that fails closed on
an unknown value is code we will eventually break — by design, not by accident.

## 3. What we always send, we mark as guaranteed

Any response field we in fact always send is marked `required` in the spec, so a
generated client can rely on it being present with no null-checks. Each such marking is a
promise: making it optional or dropping it later is a **breaking change** and goes through
§4 — never a silent surprise. This is what makes a typed client against our spec worth
having.

## 4. Nothing you depend on disappears silently — deprecate, then remove

Removing or renaming anything, adding a newly-**required** request field, tightening
validation, or changing the meaning or type of an existing field is a **breaking change**.
We are allowed to make them — but only through this process, never quietly:

1. **`deprecated: true` in the spec** on the affected operation — visible in the docs and
   in the generated SDK the day we announce.
2. **A dated changelog entry and an email announcement.**
3. **A `Sunset` HTTP header** ([RFC 8594](https://www.rfc-editor.org/rfc/rfc8594)) on
   **every response** from the deprecated endpoint, carrying the exact shutoff date — the
   one channel your monitoring can watch without reading our changelog. Where useful it is
   accompanied by a `Link; rel="sunset"` to this page.
4. **At least 90 days' notice** between the announcement and the shutoff. Ninety days is a
   **floor we may raise but will never lower.**

`/v1/` is the surface **indefinitely**. There is no planned `/v2/`; a `/v2/` path is
reserved for a wholesale redesign we expect never to build. We do not pin per-account API
versions — the compatibility rules above are the same for everyone.

## 5. Audit records are kept for at least a year

The tenant audit trail (who changed what on your account) is retained for a minimum of
**one year** — a floor, not a promise to delete at one year. See
[ADR-004](adr/0004-tenant-audit-trail.md).

## 6. The spec is the contract; the SDK carries its own version

`openapi/v1.json` in our repository is the **single source of truth** for the surface, and
the launch-tagged revision is the binding v1 contract ([ADR-002](adr/0002-openapi-spec-as-truth.md),
ADR-003 §5). Our CI mechanically forbids an un-declared breaking change from shipping.

The **SDK keeps its own version line** with honest semver: API additions arrive as SDK
minor releases, SDK-only fixes as patches, and an SDK major only when the SDK's own
surface breaks (which §1 should make rare). Every SDK release records the exact committed
spec revision it was generated from, so any build can be tied to a contract state.

---

*If you build to §1–§3 — ignore unknown fields, tolerate unknown enum values, and rely
only on `required` fields — your integration keeps working across every additive change we
ship, and the only changes that can ever affect you arrive with `deprecated: true`, an
email, a `Sunset` header, and at least 90 days to react.*
