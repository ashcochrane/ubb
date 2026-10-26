# ADR-0022: An event naming an Event Type nobody published is recorded and held, and a publication answers it

**Status:** accepted
**Date:** 2026-10-26
**Decision records:** #568 — its "Done when": *"stored with no COGS and no price; visibly held for
remediation; blocks a silent period close; replays from its original timestamp once the name is
declared or mapped"* · slice 2's specification on #193, §B5: *"Accept, quarantine, replay —
unamended. Never auto-register. The period-close safeguard survives"*, restating #138
(`docs/plans/2026-07-29-event-type-entity-model-decision.md`) · #605's ruling that production reads
an Event Type's last publication and never its draft · #473, rows 2–4 as the owner ruled them on
2026-10-22 (#190)
**Supersedes:** three rows of the table in #146 §3.4
(`docs/plans/2026-07-31-provider-supplied-cost-decision.md`), in its Quarantine column — *"Is it
recorded as a usage event? **No** — held outside the record until registered"*, *"Does it appear in
usage reports? No"* and *"Does it count toward a task's ceiling? No"*. The rest of §3.4 stands: the
line between an event UBB cannot place and one it cannot price, and both resolutions replaying at
the original timestamp.
**Companion:** ADR-0007 §2 (resolve-once, and what a replay may complete) · ADR-0020 (a quantity is
exact text, which the held bag keeps)

## Context

#146 §3.4 drew a line between *quarantine* — UBB cannot place an event, because no Event Type
declares its key — and *unresolved* — UBB can place it and cannot price it. It put the first kind
outside the record: not a usage event, not in reports, not against a ceiling, *"held outside the
record until registered"*. The argument was that such an event has *"no attribution, no validated
measurements and no declared meaning — there is nothing to record it as"*.

Nothing built that. Until #568 an event naming an undeclared Event Type was recorded and **costed**
against whatever Cost Rates matched its quantities' spellings — the opposite failure. #568's done
condition then asked for the event to be **stored** with no cost and no price, visibly held, blocking
a silent close, and replayed from its own moment once the name is declared or mapped; #193 §B5 and
#138 say *store the event immutably*. Those are later decisions than #146, and they describe a
record, not a holding area beside one.

Two facts made "outside the record" the wrong shape once it had to be built:

1. **The replay needs everything the call said.** A replay costs and prices the event at its own
   moment, for its customer, under its unit of work, against its idempotency key — a recording's
   whole input. The held row is kernel-owned and may not hold product facts (ADR-001); only a
   posting carries them all. A second store of the same facts beside the posting would be a second
   record of one call.
2. **"Visibly held" and "blocks a silent close" are already answered for postings.** A posting whose
   cost is `unresolved` with a reason is listed by every read that shows what UBB could not resolve
   (the unresolved queue, the event's own read), and its price can say `unknown` — not zero, not a
   charge. An event outside the record would need all of that rebuilt.

## Decision

**The event is recorded, and held.** It becomes a posting whose cost is `unresolved` with the reason
`event_type_not_declared` and whose price is `unknown` — no rule consulted on either side, so no
amount UBB has no basis for is ever published — and, in the same savepoint, a held row names the key
as it arrived, keeps the whole measured bag as exact text, and names the event. The posting is the
record; the held row is the quarantine: what the period close reads and what a tenant decides about.
"No production declaration" is the publication read answering nothing (#605) — never declared, or
declared and never published — so a draft takes no path of its own. An event naming no Event Type
holds nothing (#567).

**A publication answers it, and only a publication.** Publishing an Event Type is the tenant
declaring every name it carries, so `EventType.publish` registers each undecided name held at its
key, or held beneath it under a code it now carries, and replays the event in the publication's own
transaction. Mapping a name to a declaration requires that declaration to be published; a draft
answers for nothing (`NotYetPublished`). A remediation's replay re-costs the event from its own
moment with every answer on it applied, holds any quantity the answer's publication does not carry,
and refuses — by name, leaving the name held — where the call named a supplier the answer does not.
Nothing creates a declaration from a held name: never auto-register stands.

**What the tenant dismisses stays dismissed.** A dismissed name frees the close and re-costs nothing,
then or after its key is published (#473 row 2).

## Consequences

- The superseded rows read, for an Event Type nobody published: recorded — **yes**, as a held
  posting; in usage reports — **yes**, with its cost unknown; against a task's ceiling — as any
  `unresolved` cost is, which §5 of the same document already makes `indeterminate`.
- The held posting's reason column is resolve-once history: once a publication answers the name and
  the cost settles, the column is cleared with the settlement; where no rate reaches it yet, it keeps
  saying why it was unresolved when the call arrived, and the held row says the name is decided.
- A publication is never refused over held history the tenant can still decide: a replay refused by
  name leaves that one name held and the publication lands; anything else a replay raises is a
  contradiction in the record, and takes the publication back with it.
- Reversing this means a second store for the call's facts and a second definition of "visible" — the
  cost the two numbered facts above avoid.
