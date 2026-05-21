# Production Resilience Design

**Date:** 2026-03-11
**Status:** Approved

## Overview

Add production resilience to the UBB platform and SDK: API rate limiting, SDK retry logic, and deployment configuration for request timeouts and connection pooling.

## 1. API Rate Limiting

### Architecture

Two-layer rate limiting using Redis fixed window counters:

1. **Global rate limit** — Django middleware (pre-auth), protects the server itself
2. **Per-tenant rate limit** — django-ninja dependency (post-auth), enforces fair usage

### Global Rate Limit (Middleware)

- Runs before authentication, counts all inbound requests
- Redis key: `ratelimit:global:{window_ts}` (1-second windows)
- Default: `UBB_GLOBAL_RATE_LIMIT = 5000` req/s
- Returns 429 with `Retry-After: 1` if exceeded
- Skips health/ready endpoints using exact full-path matching: `request.path in {"/api/v1/health", "/api/v1/ready"}`

### Per-Tenant Rate Limit (Ninja Dependency)

- Runs after `ApiKeyAuth`, has access to `request.auth.tenant`
- Redis key: `ratelimit:tenant:{tenant_id}:{window_ts}`
- Default: `UBB_TENANT_RATE_LIMIT = 500` req/s
- Per-tenant override: `Tenant.rate_limit_per_second` field (nullable, falls back to default)
- No separate caching needed — `ApiKeyAuth` already loads the tenant object into `request.auth.tenant`, so the dependency reads `request.auth.tenant.rate_limit_per_second` directly

### Two Endpoint Tiers

- **High throughput** — usage recording (`POST /metering/usage`), pre-check (`POST /billing/pre-check`), close run. These use the full tenant limit.
- **Standard** — everything else. Uses `max(1, tenant_limit // 5)` of tenant limit (default: 100 req/s). Integer division ensures no fractional values.

The dependency accepts a `tier` parameter: `RateLimit("high")` or `RateLimit("standard")`.

### Atomic Counter (Lua Script)

A single Lua script executes INCR + conditional EXPIRE atomically to prevent race conditions where a key leaks without an expiry:

```lua
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
```

### Redis Client

- **Global middleware:** Obtain a raw Redis client via `redis.from_url(settings.REDIS_URL)` and register the Lua script using `script.register()`. This avoids Django cache abstraction limitations with `EVALSHA`.
- **Per-tenant dependency:** Also uses the raw Redis client for consistency.

### Graceful Degradation

If Redis is unreachable, both the global middleware and per-tenant dependency **fail open** — skip rate limiting and allow the request through. Log a warning on each failure. This follows the same pattern as `RiskService` graceful degradation.

### Response Headers

Every authenticated response includes:
- `X-RateLimit-Limit` — the applicable limit
- `X-RateLimit-Remaining` — requests remaining in current window
- `X-RateLimit-Reset` — Unix timestamp when window resets

These are set on all responses, not just 429s, so SDK callers can self-throttle.

**Injection mechanism:** The per-tenant dependency stores rate limit data on `request` (e.g., `request.rate_limit_info`). A lightweight response middleware reads these values and injects the headers on every response. This cleanly separates the rate limit check (dependency) from header injection (middleware).

### Files

| File | Change |
|------|--------|
| `core/rate_limit.py` | New — Lua script, global middleware, per-tenant dependency |
| `apps/platform/tenants/models.py` | Add `rate_limit_per_second` field (nullable BigIntegerField) |
| `config/settings.py` | Add `UBB_GLOBAL_RATE_LIMIT`, `UBB_TENANT_RATE_LIMIT` defaults, add middleware |
| `config/urls.py` or API routers | Add `RateLimit` dependency to product routers |
| Migration | New migration for `rate_limit_per_second` field |

## 2. SDK Retry Logic

### Behaviour

Built-in retry with exponential backoff + jitter, enabled by default.

### Retryable Conditions

The retry wrapper catches UBB exception types (not raw httpx exceptions), since each client's `_request()` already converts `httpx.TimeoutException` / `httpx.ConnectError` → `UBBConnectionError` and HTTP errors → `UBBAPIError` subclasses.

| Exception | Retried |
|-----------|---------|
| `UBBConnectionError` | Yes — covers timeouts and connection failures |
| `UBBAPIError` with `status_code` in {429, 502, 503, 504} | Yes — **unless** the error is an instance of `UBBHardStopError` or `UBBRunNotActiveError` |
| `UBBHardStopError` (subclass of `UBBAPIError`, status 429) | No — domain error, even though status is 429 |
| `UBBRunNotActiveError` (subclass of `UBBAPIError`) | No — domain error |
| Any other `UBBAPIError` (400, 401, 403, 404, 409, 422) | No — client errors, retrying won't help |

**Important:** `_request_usage()` in `MeteringClient` converts hard-stop 429s into `UBBHardStopError` before raising. The retry wrapper must check `isinstance(error, (UBBHardStopError, UBBRunNotActiveError))` first and skip retry for those, even though their `status_code` is in the retryable set.

### Retry-After Header

To preserve the `Retry-After` header value when a 429 is raised, add a `retry_after` attribute to `UBBAPIError`. The `_request()` method sets it from the response header. The retry wrapper reads `error.retry_after` and uses it as the sleep duration instead of computed backoff.

### Backoff Schedule

Same pattern as the existing `stripe_service.py`:
- Base: 0.5s * 2^attempt
- Jitter: +/-25%
- Max delay capped at 10s
- Default `max_retries=3` (attempts: 0.5s, 1s, 2s)

For 429 responses with `Retry-After` header, the header value is used instead of computed backoff.

### Configuration

```python
client = UBBClient(
    api_key="ubb_live_...",
    max_retries=3,  # default; set 0 to disable
)
```

The `max_retries` parameter is passed from `UBBClient` to all product clients.

### Implementation

A shared `_request_with_retry()` method (or mixin) wrapping each client's `_request()`. No new dependencies — uses `time.sleep` + `random` (same as `stripe_service.py`).

### Files

| File | Change |
|------|--------|
| `ubb-sdk/ubb/retry.py` | New — shared retry logic (backoff, jitter, retryable check) |
| `ubb-sdk/ubb/exceptions.py` | Add `retry_after` attribute to `UBBAPIError` |
| `ubb-sdk/ubb/metering.py` | Accept `max_retries` in `__init__`, wrap `_request()` and `_request_usage()` with retry, set `retry_after` on 429 errors |
| `ubb-sdk/ubb/billing.py` | Accept `max_retries` in `__init__`, wrap `_request()` with retry, set `retry_after` on 429 errors |
| `ubb-sdk/ubb/subscriptions.py` | Accept `max_retries` in `__init__`, wrap `_request()` with retry, set `retry_after` on 429 errors |
| `ubb-sdk/ubb/referrals.py` | Accept `max_retries` in `__init__`, wrap `_request()` with retry, set `retry_after` on 429 errors |
| `ubb-sdk/ubb/client.py` | Accept `max_retries` parameter, pass to product clients |

## 3. Request Timeouts (Deployment Config)

No application code. Timeouts are enforced at the infrastructure layer.

### Requirements

| Layer | Setting | Value | Purpose |
|-------|---------|-------|---------|
| **Gunicorn** | `--timeout` | 30 | Kills worker if request exceeds 30s |
| **Nginx / ALB** | `proxy_read_timeout` | 30 | Returns 504 to client if upstream doesn't respond |
| **Render** | Service settings | 30s | Render's default request timeout |

### Existing Application Timeouts (already in place)

- Celery tasks: `TASK_SOFT_TIME_LIMIT=300`, `TASK_TIME_LIMIT=600`
- SDK httpx client: configurable `timeout` parameter (default 10s)
- Stripe calls: retried with backoff, capped at 3 attempts

### Setting

Add `UBB_REQUEST_TIMEOUT_SECONDS = 30` to `config/settings.py` as documentation reference for deployment configuration.

## 4. Connection Pooling (Deployment Config)

No application code changes needed now.

### Current Configuration (correct for direct PostgreSQL)

```python
CONN_MAX_AGE = 600          # Reuse connections for 10 minutes
CONN_HEALTH_CHECKS = True   # Verify connection before use
```

### When Behind PgBouncer (Render, Supabase, RDS Proxy)

```python
CONN_MAX_AGE = 0             # Let PgBouncer manage pooling
CONN_HEALTH_CHECKS = False   # PgBouncer handles health checks
```

PgBouncer connection string is provided by the platform (Render exposes a separate PgBouncer URL). Switch `DATABASE_URL` to point at PgBouncer instead of PostgreSQL directly.

### Setting

Add environment-aware configuration to `config/settings.py`:

```python
# Connection pooling: set USE_PGBOUNCER=true when behind PgBouncer
if os.getenv("USE_PGBOUNCER", "").lower() == "true":
    CONN_MAX_AGE = 0
    CONN_HEALTH_CHECKS = False
```

## Implementation Order

1. Rate limiting (API side) — biggest gap, protects the system
2. SDK retry logic — improves reliability for all SDK consumers
3. Deployment config (timeouts + pooling) — settings only, quick

## Testing Strategy

### Rate Limiting
- Unit tests for Lua script (mock Redis)
- Test per-tenant limit respects override
- Test global limit returns 429
- Test response headers present on all responses
- Test health/ready endpoints bypass global limit
- Test standard tier uses `max(1, tenant_limit // 5)`
- Test Redis unavailable → fail open (requests allowed, warning logged)

### SDK Retry
- Test retries on `UBBConnectionError` (timeout/connection error)
- Test retries on 429 with `Retry-After` header (uses header value as sleep)
- Test retries on 502/503/504
- Test no retry on 400/401/404
- Test no retry on `UBBHardStopError` (even though status 429)
- Test no retry on `UBBRunNotActiveError`
- Test max_retries=0 disables retry
- Test backoff timing (mock `time.sleep` in `ubb.retry` namespace)
- Test `retry_after` attribute set on `UBBAPIError` for 429 responses
