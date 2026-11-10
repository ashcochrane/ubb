# Handoff — the billing-readiness handover package (November 2026)

This folder is the handover from the internal billing-readiness programme to the operational launch owner. It is
**frozen history** in the sense of `CLAUDE.md`'s ratchet: read it for what was verified and decided, never edit it as
current truth. The living product documentation stays where it always was (`CONTEXT-MAP.md`, the per-product
`CONTEXT.md` files, `docs/adr/`, `docs/architecture/`, `docs/conventions/`).

Start with the product brief, then `R10-ASH-HANDOFF-2/START-HERE-ASH.md`.

| Path | What it is |
|---|---|
| `UBB-PRODUCT-BRIEF.pdf` / `UBB-PRODUCT-BRIEF.md` | The plain-English product brief: what UBB is, what is built, what was verified, what is not built, what remains before a real launch. Same content in both formats. |
| `R10-ASH-HANDOFF-2/` | **The authoritative engineering handoff.** `START-HERE-ASH.md` gives the reading order; `00` the index and identities; `01` the plain-English product; `02` the technical system map with code citations; `03` the safe local recipe and golden paths; `04` the verification coverage matrix; `05` the register of what the launch owner inherits. |
| `R10-SDK-V5-RELEASE/` | The SDK 5.0.0 release record: the release manifest, the build and verification evidence. **The wheel itself is not committed**; rebuild it from the annotated tag `sdk-v5.0.0` with `ubb-sdk/release/build_wheel.py` — the build is reproducible and `ubb-sdk/CHANGELOG.md` records the expected SHA-256. |
| `R10-W7-DELIVERY-PROMPT.md` | The launch plan ("W7"): deployment, measurement, acceptance audit and first-client admission. Its STATUS line reads `PRE-LAUNCH — NOT FINAL`; it is not to be executed until its seven launch inputs are real and the line reads FINAL. |
| `R10-BILLING-READINESS-FINAL-TRANSITION.md` | The record of the programme's closing window: identity checks, the anchor refresh, hygiene, and the final owner rulings. |
| `R10-ASH-HANDOFF/` | The earlier handoff (2 November 2026). Historical only; superseded in full by `R10-ASH-HANDOFF-2/`. |

Not committed, held by the owner: the raw local verification transcripts (`R10-BILLING-STAGE-D-EVIDENCE/` and the
earlier `R10-BILLING-READINESS/`), which the matrix in `04` cites by file name. They contain API keys minted in a
disposable test database and belong outside the repository.

Identities at the time of this handoff: `main` `90d008b709a86ff0d63588d8dd6b0a160978230b`; behavioural proof anchor
`a6738e78e96ab10eabd45dc10fafdc842b7de519`; SDK release commit `b41b395f59d798cec83289d83d5ec71f83201c7f` (tag
`sdk-v5.0.0`, wheel SHA-256 `56d28b90876beff35532e48df6a5fb8545f665f9c781b40d9febf0b418555948`).

Nothing here is evidence of a production deployment, real payment flow or a live customer.
