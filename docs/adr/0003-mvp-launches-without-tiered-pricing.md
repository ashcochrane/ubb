---
status: accepted
date: 2026-07-15
---

# MVP launches without tiered pricing — deleted end to end, not gated

Decided during the estimate-hold-settle walkthrough
([#22](https://github.com/ashcochrane/ubb/issues/22), map
[#9](https://github.com/ashcochrane/ubb/issues/9)): the `graduated` and `package` pricing models
are **deleted end to end** for the MVP / first launch — the models, both pricer branches, the
period ladder (`PricingPeriodCounter`) and its row locks, the tier mirror, the estimator's
conservative tiered branch, and their tests. Reinstatement, if tiers return post-MVP, is a rebuild
from git history, not a flag flip.

**Why.** Tiered cards were the only place the async path's arrival-time estimate could differ from
the settled price by *design* (the deliberately-high three-anchor guess), the only stateful,
lock-contended part of pricing, and the only caveat in the overspend-guarantee story. With them
gone, **the hold equals the exact price by construction**, settle's estimate−exact correction
shrinks to a net for rate-card config drift (a card edited between an event's arrival and its
settle, or a backdated event pricing on an older card version), and the guarantee-legibility
artifact can say "we reserve the exact price at arrival" without a footnote.

**Considered options.** (a) Config-only — just don't sell tiers to the first tenant: rejected
because the complexity stays in the code and the guarantee story keeps its caveat. (b) Gate + strip
— validation refuses tiered cards, the durable pricer stays dormant: rejected in favor of full
deletion for maximal simplification; the driver explicitly accepted that reinstatement becomes a
rebuild.

**Consequences.** Reverses the tier work shipped in the F-program. The estimation walkthrough's
"never knowingly under-hold" machinery (tier mirror, three-anchor worst case, ceiling-rounding
guard) goes with it. `Rate.pricing_model` narrows to `per_unit`/`flat`. The settle-side correction
path stays (config drift is still possible); the orphan-hold repair arithmetic
([#23](https://github.com/ashcochrane/ubb/issues/23)) gets exact inputs.
