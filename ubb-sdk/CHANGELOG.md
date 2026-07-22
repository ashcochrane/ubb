# Changelog

All notable changes to `ubb-sdk`. This project follows [semantic versioning](https://semver.org);
each release is stamped with the exact committed API-contract revision it was
generated against (`ubb.__spec_revision__`).

## 3.0.0

**The coordinated v3.0 release (#85).** One breaking cut carrying the generated
typed core (#84) and the RFC 9457 problem+json error model (#78) together — the
one integrating tenant migrates exactly once. **No compatibility shim.**

Full upgrade guide, covering every breaking edge: **[MIGRATION.md](./MIGRATION.md)**.

_Release date is set at tag time; publishing is gated on operator↔tenant
coordination recorded on issue #85 (see MIGRATION.md → Release checklist)._

**Spec-revision stamp** (verifiable on the release):

| Stamp | Value |
|---|---|
| `ubb.__version__` | `3.0.0` |
| `ubb.__spec_revision__` | `9b98badf0155e8dbe1de6425170c2d9004f3d09b0bac18ddf66375333b110c12` |
| `ubb.__spec_version__` | `v1` |
| Generator | `openapi-python-client==0.29.0` |

The `__spec_revision__` is the sha256 of the committed `openapi/v1.json`; CI
regenerates the core from that spec and fails on any drift, so the stamp cannot
disagree with the shipped bytes.

### Breaking

- **Error model → problem+json + typed exceptions.** Every error is RFC 9457
  `application/problem+json` with a stable snake_case `code`. The SDK maps each
  to a per-code exception under a status-family parent (`ConflictError`,
  `UnprocessableEntityError`, …), all subclassing `UBBAPIError`.
  `UBBAPIError.code` is new. Several conditions changed HTTP status (withdraw
  insufficient-balance and would-overdraw `400→409`; duplicate creates
  `422→409`; grant-expiry / webhook validation `400→422`). See MIGRATION.md §1.
- **Cursor envelope on every list.** `PaginatedResponse[T]` (`data`,
  `next_cursor`, `has_more`); lists take `cursor`/`limit`, not `offset`. Bare
  arrays and `{invoices}` / `{grants}` wrappers are gone. `/me/grants` ordering
  changed to the creation keyset. See MIGRATION.md §2.
- **One verdict field set for batch/async ingest.**
  `BatchResult.succeeded/failed → accepted/rejected`;
  `BatchItemResult.ok/error → accepted/code (+detail)`. See MIGRATION.md §3.
- **Generated DTOs replace the nine hand dataclasses.** `record_usage` returns
  `RecordUsageResponse` — `balance_after_micros` is removed, use
  `new_balance_micros`. `UsageEventOut.id` is now `uuid.UUID` (was `str`). See
  MIGRATION.md §4.
- **The last untyped 200s are typed (#98)** — top-up / withdraw / refund /
  transactions / auto-top-up and the margin surface now return generated
  models (`TopUpCheckoutResponse`, `WithdrawResponse`, `RefundResponse`,
  `WalletTransactionOut`, `StatusResponse`, `CustomerMarginOut`,
  `DimensionMarginRow`, `MarginTrendPointOut`); the corresponding hand result
  types are retired. `WalletTransactionOut.id` is `uuid.UUID` (was `str`).
  See MIGRATION.md §4.
- **`idempotency_key` now required on top-ups** (tenant + widget). See
  MIGRATION.md §5.
- **Single versioned API.** All routes under `/api/v1/…`; per-mount
  `docs`/`openapi.json` and API-roots removed (`base_url` unchanged). See
  MIGRATION.md §5.

### Added

- Registry-derived per-code exception hierarchy (`ConflictError`,
  `InsufficientBalanceError`, …) — catch a family or one exact code.
- Generated transport + DTO core (`ubb._core`), sync and async, produced from
  the committed spec under the CI ratchet (#84).
- `ubb.__version__` on the public surface, paired with the existing
  `ubb.__spec_revision__` / `ubb.__spec_version__` so a build is self-describing.
- Open-world tolerance: unknown fields land in `additional_properties`, response
  enums parse as plain `str` — a pinned client never crashes on a newly added
  field or enum value (ADR-003).

### Retained (not shims)

- `UBBConflictError` alias for `ConflictError`; `verify_webhook_legacy`
  (webhook-secret rotation, a product feature); `credit()` (base-money
  primitive). None dual-runs the old contract — see MIGRATION.md §7.

### Known gaps

- A few billing/margin endpoints remain untyped in the committed spec and still
  return raw `dict`s (#98). `MeteringClient.update_rate_card` /
  `get_rate_card_history` / `bulk_create_rate_cards` call routes the big-bang
  removed and are dead against a v3.0 server — removal tracked in the launch
  sweep (#86).
