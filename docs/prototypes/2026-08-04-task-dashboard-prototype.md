# Tasks in the console — prototype notes (#152)

**Status:** prototype, awaiting reaction. **Not a decision, not a specification.**
**Artifact:** [`2026-08-04-task-dashboard-wireframe.html`](./2026-08-04-task-dashboard-wireframe.html) —
open it in a browser; it is self-contained, has no build step and no dependencies.
**Drawn against:** `main` @ `0cf00b5`, rendering decisions #138–#155 and #165.

Issue [#152](https://github.com/ashcochrane/ubb/issues/152) is a `wayfinder:prototype` ticket: *build a
cheap, rough artifact that makes the shape concrete enough to react to. Do not build the real surface.*
These notes are the reading companion to the wireframe — the positions in text, and the inventory of
what already constrains this surface.

---

## 1. The problem, restated

Tasks have no surface in the console. `GET /api/v1/metering/analytics/tasks` exists with no UI on top
of it; `GET /metering/tasks` and `/tasks/{id}` return per-task detail nobody can see; and
`PUT /api/v1/metering/task-types` is the only way to declare a kind of work.

Meanwhile the re-model has given a task six lifecycle states, three ceilings, four spend-control
families, four pricing statuses, three costing states and a cost-completeness rule — and **none of it
has a consumer**. #155 §9.5 makes that a problem rather than an oversight:

> A semantic state is not complete until one real consumer demonstrates its intended rendering.

This surface is that consumer.

## 2. Six questions, six positions

| # | Question | Position taken | What needs a ruling |
|---|---|---|---|
| 1 | Task type: first-class object or settings row? | **First-class**, own route `/tasks/kinds/{key}` | Whether the fixed price appears here at all, or stays a link into the pricing book |
| 2 | Primary reporting unit: type or run? | **Kinds of work lands**; runs is a sibling | Whether an operator debugging live work is badly served by that |
| 3 | Where are spend limits set? | **Wherever their subject lives — no Limits page** | Distributed config + centralised report, or one config page? |
| 4 | What does a breach look like? | An **episode row**; the past-limit report becomes the breach report, widened to three families, and gains a sibling | Whether "past-limit report" survives as a phrase (#154 left this open) |
| 5 | Subtask tree with ten children? | A **two-level table with a roll-up row**, never a tree widget | At what child count the flat table stops working — nothing bounds it |
| 6 | New top-level tab? | **Two**: `Tasks` (ungated group, beside Events) and `Spend controls` (PLATFORM) | Two new nav items in one change, on a nav that has ten |

### Why Q3 resolves structurally

#150 replaced ten bespoke mechanisms with four families, and each family bounds a different subject:

```
Ceiling            bounds one unit of work        → the kind of work
Customer spend pool bounds a customer's period    → the customer
Wallet policy      bounds available funds         → the wallet
Admission control  bounds the rate work enters    → settings
```

A single "Limits" page would put all four back in one table — re-collapsing the distinction the
decision was written to create. Configuration is therefore distributed by subject; **reporting** is
centralised, because #153 §10 gives Spend Controls two report contracts in one product area.

### Why Q4 splits the existing report

`GET /customers/{id}/past-limit-report` today reconstructs wallet-floor episodes from the
`stop.fired`/`stop.cleared` pair plus the durable ledger row (`api/v1/past_limit.py:88-116`). Under
#153 §10 it becomes:

- **Stops and breaches** — episodic, three families (`task_ceiling`, `customer_spend_pool`,
  `wallet_policy`), tenant-wide with a customer filter. The pool is entirely new; it is what today's
  report is missing.
- **Utilisation and headroom** — continuous, and the only home for the indeterminate count, which
  produces no episode by construction and is otherwise invisible.

## 3. What already constrains this surface

Every one of these was handed to #152 by a merged decision. The wireframe renders all of them; this is
the checklist for whoever implements the real thing.

| Constraint | Source |
|---|---|
| Never count `expired` or `cancelled` as failures | #140 §11 |
| Group attempts by `external_task_id`; bucket by `reason_code`; `reason_detail` never grouped | #140 §3.3, §11 |
| Surface `charge_created` per job | #140 §11 |
| Unknown revenue ≠ zero revenue | #141 §8 |
| Foreign-currency mirrors: exclude **and** report the excluded count | #142 |
| `indeterminate` must never render as "under limit" | #146 §5, #150 §17 |
| Margin *unavailable* must never render as 0% | #147 |
| Four pricing statuses, not three | #148 §4 |
| Aggregate on measurements, never on raw event counts, unless the unit is held constant | #149 §3.1, #153 §7.2 |
| Render the ceiling's three states; utilisation averaged **per task then across tasks** | #150 §9.3, §17 |
| Show ceiling against price for fixed-price kinds | #150 §17 |
| Must **not** build a dimension-scoped cap affordance | #150 §6.4 |
| Render `not_applicable_reason` distinctly (`fixed_task_pricing` vs `tenant_not_billing`) | #151 §8 |
| Mixed-derivation total is **complete**; only unresolved makes it incomplete; "at least £4.20" | #151 §10 |
| `charging_summary` derived, never editable | #151 §2.4, ADR-0006 §4 |
| Label wallet affordability and the pool as answering different questions | #151 §11.3 |
| May not invent a number the analytics contract cannot express | #153 §18 |
| Percentiles over known lower bounds, with completeness stated | #153 §11.3 |
| Synthetic charge postings excluded from every count | #153 §7.2 |
| Vocabulary: Task/Subtask, Ceiling, `customer_spend_pool`, Pricing Receipt; "limit" retired as a field word | ADR-0006 |
| Seven canonical fixture scenarios, each with a rendering assertion | #155 §9.2, #165 |

### The seven states this surface must distinguish

`known_economics` · `unknown_cost` · `waived_revenue` · `pricing_not_applicable` ·
`incomplete_total` · `indeterminate_ceiling` · `measurements_pruned`

The named defect shapes are ordinary and easy to write — `amount ?? 0`, `measurements ?? {}`,
`status === "unknown" ? "0%" : …`. TypeScript proves only that the console can *receive* these states.

## 4. Deliberately absent

- **Dimension-scoped caps** — #150 §6.4 forbids the affordance.
- **An editable price on the kind of work** — the kind declares *priced as a whole*; the amount is a
  work line in the pricing book (#139 §3.1).
- **A counterfactual metered price** on fixed-price work — declined by #151 §12; the COGS distribution
  is the replacement and answers a narrower question on purpose.
- **A warning threshold or amber ceiling state** — enforcement is binary and v1 adds no warning event
  (#150 §9.1), so the UI must not imply one exists.
- **Real components** — nothing here uses the console's design system, and none of it should be lifted
  into `apps/ui`.

## 5. The hazard this sits on

#155 recorded it as residue: **#152 and #157 now prototype against a paper model** — #144's named
hazard. Every screen renders a contract that exists only in decision documents. No endpoint returns a
measure status; no fixture carries an indeterminate ceiling; and by #155's count every value in the
console's 2,963 lines of mock fixtures is known.

That is the argument for drawing it before slice 0 — a rendering contract nobody has drawn is a
rendering contract nobody has tested. It is equally the reason this file is not a specification.

## 6. Open, and not answered here

- Whether "past-limit report" survives as a phrase (#154's open naming question, now two reports over
  four families under a vocabulary where "limit" was retired as a field word).
- Where query presets live — tenant rows, shipped defaults, or both (#153 §19). Decides whether the
  named reports on these screens are a console feature or an API concept.
- How a kind of work's `task_pricing_mode` may change over time (#151 residue). The wireframe shows a
  warning at the point of change because there is no publish record to show instead.
- A child-count bound for the steps table. Ten is comfortable; nothing in the model caps it.
- Whether the three unbuilt recovery surfaces (#146 §11, #147 §14, #148 §7.3 — four with #165's) get a
  console home here. #151 §16 names this surface as the obvious host; this prototype does not draw one.
