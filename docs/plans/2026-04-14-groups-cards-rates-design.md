# Groups, Cards & Rates — Design

**Goal:** Introduce a `Group` model for tenant-defined billing hierarchy and margin management, extract a `Card` model from `ProviderRate` to represent pricing cards, and rename `ProviderRate` to `Rate` as individual price lines within a Card. Standardise all margin/markup fields to margin percentage throughout the system.

**Architecture:** Group lives in `apps/platform/groups/` (shared platform entity), Card and Rate live in `apps/metering/pricing/` (pure pricing). UsageEvent gets a simple `group` CharField linking events to Groups by slug. Card and Group are independent — the event connects them, not a FK.

**Tech Stack:** Django 6.0, PostgreSQL, existing BaseModel/SoftDeleteMixin, django-ninja API.

---

## Current State (Problems)

### No product/group abstraction

Tenants have no way to organise their pricing into business-meaningful groups (products, departments, services). The UI's "Billing margins" hierarchy (Default → Product → Card) has no backend model to support it — the entire feature runs on mock data.

### ProviderRate conflates two levels

`ProviderRate` is a single flat model that represents both the "pricing card" concept (a named collection of rates for a provider/model combination) and individual rate lines (per-metric pricing). The UI's pricing card wizard creates "cards" but the backend has no card entity — only individual rates.

### Markup/margin inconsistency

`TenantMarkup` stores `markup_percentage_micros` (additive: cost + markup = price) and `fixed_uplift_micros`. The UI displays margin everywhere (revenue - cost / revenue). These are different math, creating a conversion burden on every display and report.

### group_keys is over-engineered for billing

`group_keys` is a `JSONField(dict[str, str])` on `UsageEvent`. It was designed for flexible analytics tagging but the billing use case only needs one value — which group this event belongs to. The dict adds unnecessary complexity: GIN indexes, JSON extraction, and a `billing_dimensions` config to specify which key matters.

---

## Target State

```
apps/platform/groups/
  models.py       → Group (hierarchy + margin)
  admin.py        → GroupAdmin
  apps.py         → GroupsConfig

apps/platform/tenants/
  models.py       → Tenant + group_label field

apps/metering/pricing/
  models.py       → Card (new) + Rate (renamed from ProviderRate)
  services/       → PricingService (updated resolution)
  admin.py        → CardAdmin, RateAdmin

apps/metering/usage/
  models.py       → UsageEvent.group (CharField, replaces group_keys)
```

### Import direction (preserved)

```
platform/groups/   ← defines Group
    ↑         ↑
billing/     metering/    ← both import from platform, never from each other
```

---

## Design Decisions

### 1. Group lives in platform, not billing

Group is an organisational entity (like Customer, Run) that multiple domains reference. Billing uses it for margins. Metering uses it for analytics. The dashboard uses it for hierarchy display.

If Group lived in billing, Card (in metering) could not FK to it — breaking the import rule. Platform is the shared layer, same pattern as Customer and Run which both carry billing-adjacent fields.

### 2. Card has no Group FK

The same Card (e.g. "Gemini 2.0 Flash") can serve multiple Groups (Property Search, Doc Summariser). Card → Group is not 1:1 and not even M:N in a fixed sense — it depends on which events use which Card with which Group.

Card and Group are independent dimensions of an event:
- Card determines **cost** (via its Rates)
- Group determines **margin** (via its margin_pct)

The event connects them. The dashboard derives "cards in this group" from event data.

### 3. Card has no billing/margin fields

Card is a pure metering model. It knows about provider costs, not about what the tenant earns. Margin lives on Group (the organisational layer) and TenantMarkup (the default fallback). This preserves clean domain boundaries.

### 4. UsageEvent.group is a simple CharField, not a FK

Events are immutable records. A string reference (like `idempotency_key`, `request_id`) is the right choice:
- No write-time FK resolution on the hot path
- Events can be recorded before a Group exists (shows as "unmapped" in dashboard)
- No referential integrity issues when Groups are archived
- Simple btree index, no JSON parsing

### 5. Single `group` field replaces `group_keys` dict

The billing use case needs one value — which group this event belongs to. Analytics tags belong in the existing `metadata` JSONField. Having both `group_keys` and `metadata` is redundant.

This eliminates: the `billing_dimensions` config on Tenant, the "which key is the billing dimension?" question, GIN index overhead, and JSON extraction at resolution time.

### 6. Margin everywhere, not markup

The system standardises on **margin percentage** (target margin as % of billed price). Markup percentage is removed.

- Margin is bounded (0-99%) and intuitive — "60% margin means I keep 60 cents of every dollar"
- Margin is how the business thinks and how the UI displays
- One formula everywhere: `billed_cost = provider_cost / (1 - margin_pct)`
- No conversion between storage and display

`TenantMarkup.markup_percentage_micros` and `fixed_uplift_micros` are replaced with `margin_pct`.

### 7. Margin resolution: Group overrides TenantMarkup

TenantMarkup stays as the default fallback. Group is an optional override layer:

```
Card-level TenantMarkup (event_type + provider match)?  →  use it
         ↓ no match
Group.margin_pct (from event.group)?                    →  use it
         ↓ null or no group
Walk parent chain (Group.parent.margin_pct)?            →  use it
         ↓ null or no parent
TenantMarkup (event_type only)?                         →  use it
         ↓ no match
TenantMarkup (global)?                                  →  use it (always exists)
```

Tenants who never set up Groups: zero change, TenantMarkup works as today. Tenants who create Groups: get an override layer with TenantMarkup as fallback.

### 8. Nesting is supported but not used yet

Group has `parent = FK("self", null=True)`. For launch, all Groups are flat (parent is always null). The hierarchy is: Default → Group → Card.

When a tenant needs sub-groups (e.g. "Property Search > Residential > Gemini Flash"), the parent FK enables it without schema changes. Resolution walks up the parent chain until it finds a non-null margin_pct.

---

## Models

### Group (`apps/platform/groups/models.py`)

```python
class Group(BaseModel):
    """
    Tenant-defined billing group for organising pricing and margins.
    Maps to UsageEvent.group via slug.
    """
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="groups"
    )
    parent = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children"
    )
    name = models.CharField(max_length=255)
    slug = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    margin_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Target margin %. Null = inherit from parent or default."
    )
    status = models.CharField(
        max_length=20, choices=[("active", "Active"), ("archived", "Archived")],
        default="active",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "slug"],
                condition=models.Q(status="active"),
                name="unique_active_group_per_tenant_slug",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status"]),
        ]
```

### Card (`apps/metering/pricing/models.py`)

```python
class Card(BaseModel):
    """
    A pricing card grouping related Rates for a specific provider + model combination.
    Pure metering — no billing/margin awareness.
    """
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="pricing_cards"
    )
    name = models.CharField(max_length=255)
    provider = models.CharField(max_length=100, db_index=True)
    event_type = models.CharField(max_length=100, db_index=True)
    dimensions = models.JSONField(default=dict)
    dimensions_hash = models.CharField(max_length=64, db_index=True)
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20, choices=[("active", "Active"), ("archived", "Archived")],
        default="active",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "provider", "event_type", "dimensions_hash"],
                condition=models.Q(status="active"),
                name="unique_active_card_per_tenant_provider_event_dims",
            ),
        ]
```

### Rate (`apps/metering/pricing/models.py` — renamed from ProviderRate)

```python
class Rate(BaseModel):
    """
    A single metric price line within a Card.
    Renamed from ProviderRate.
    """
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="rates")
    metric_name = models.CharField(max_length=100, db_index=True)
    cost_per_unit_micros = models.BigIntegerField()
    unit_quantity = models.BigIntegerField(default=1_000_000)
    currency = models.CharField(max_length=3, default="USD")
    valid_from = models.DateTimeField(db_index=True)
    valid_to = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["card", "metric_name"],
                condition=models.Q(valid_to__isnull=True),
                name="unique_active_rate_per_card_metric",
            ),
        ]

    def calculate_cost_micros(self, units: int) -> int:
        """Round-half-up: (units * cost_per_unit + unit_quantity/2) // unit_quantity"""
        return (units * self.cost_per_unit_micros + self.unit_quantity // 2) // self.unit_quantity
```

### TenantMarkup changes (`apps/metering/pricing/models.py`)

```python
class TenantMarkup(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="markups"
    )
    event_type = models.CharField(max_length=100, blank=True, default="", db_index=True)
    provider = models.CharField(max_length=100, blank=True, default="", db_index=True)

    # CHANGED: was markup_percentage_micros + fixed_uplift_micros
    margin_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text="Target margin %. 0 = pass-through (no margin)."
    )

    valid_from = models.DateTimeField(auto_now_add=True, db_index=True)
    valid_to = models.DateTimeField(null=True, blank=True)
```

### UsageEvent changes (`apps/metering/usage/models.py`)

```python
class UsageEvent(BaseModel):
    # ... existing fields ...

    # REMOVE: group_keys = models.JSONField(null=True, blank=True)
    # ADD:
    group = models.CharField(
        max_length=255, null=True, blank=True, db_index=True,
        help_text="Billing group slug. Resolves to Group model for margin."
    )

    # KEEP as-is:
    properties = models.JSONField(default=dict)   # dimension matching for rates
    metadata = models.JSONField(default=dict)     # free-form analytics tags
```

### Tenant changes (`apps/platform/tenants/models.py`)

```python
class Tenant(BaseModel):
    # ... existing fields ...

    # ADD:
    group_label = models.CharField(
        max_length=100, default="Products",
        help_text="Display label for groups in the UI (Products, Departments, etc.)"
    )
```

---

## Pricing + Margin Resolution

### Current flow

```
UsageService.record_usage()
  → PricingService.price_event(tenant, event_type, provider, usage_metrics, properties)
    → find ProviderRate(s) by provider/event_type/metric/dimensions
    → calculate provider_cost (sum of rate costs)
    → find TenantMarkup (event_type+provider → event_type → global)
    → calculate billed_cost (provider_cost + markup)
  → store UsageEvent with both costs
  → emit outbox event
```

### New flow

```
UsageService.record_usage()
  → PricingService.price_event(tenant, event_type, provider, usage_metrics, properties, group)
    → find Card by (tenant, provider, event_type, dimensions_hash)
    → get active Rates from Card
    → calculate provider_cost (sum of rate costs)
    → resolve_margin(tenant, event_type, provider, group):
        1. TenantMarkup(event_type + provider) match?  → return margin_pct
        2. Group slug lookup → margin_pct not null?     → return margin_pct
        3. Walk Group.parent chain → margin_pct?        → return margin_pct
        4. TenantMarkup(event_type) match?              → return margin_pct
        5. TenantMarkup(global) match?                  → return margin_pct
        6. Default: 0 (pass-through)
    → billed_cost = provider_cost / (1 - margin_pct)
  → store UsageEvent with both costs + group slug
  → emit outbox event
```

### Margin formula

```python
def apply_margin(provider_cost_micros: int, margin_pct: Decimal) -> int:
    """
    Calculate billed cost from provider cost and target margin.
    
    margin_pct=0:   billed = provider_cost (pass-through)
    margin_pct=0.60: billed = provider_cost / 0.40 (tenant keeps 60%)
    margin_pct=0.80: billed = provider_cost / 0.20 (tenant keeps 80%)
    """
    if margin_pct <= 0:
        return provider_cost_micros
    divisor = 1 - margin_pct
    return int((provider_cost_micros * 1_000_000 + int(divisor * 1_000_000) // 2) // int(divisor * 1_000_000))
```

---

## SDK Changes

### Before

```python
ubb.metering.record_usage(
    customer_id="cust_123",
    event_type="llm_call",
    provider="google_gemini",
    usage_metrics={"input_tokens": 1500, "output_tokens": 800},
    properties={"model": "gemini-2.0-flash"},
    group_keys={"product": "property_search", "region": "qld"},  # dict
)
```

### After

```python
ubb.metering.record_usage(
    customer_id="cust_123",
    event_type="llm_call",
    provider="google_gemini",
    usage_metrics={"input_tokens": 1500, "output_tokens": 800},
    properties={"model": "gemini-2.0-flash"},
    group="property_search",                                      # simple string
    metadata={"region": "qld", "team": "residential"},            # analytics tags
)
```

### Backward compatibility

During transition, the API accepts both `group` and `group_keys`:
- If `group` is provided, use it directly
- If `group_keys` is provided (legacy), extract the first value as `group` and log a deprecation warning
- If both are provided, `group` takes precedence

---

## API Endpoints

### New: Group CRUD (`/api/v1/platform/groups`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/platform/groups` | Create group |
| GET | `/api/v1/platform/groups` | List groups (cursor pagination) |
| GET | `/api/v1/platform/groups/{group_id}` | Get group |
| PATCH | `/api/v1/platform/groups/{group_id}` | Update group (name, margin_pct, status) |
| DELETE | `/api/v1/platform/groups/{group_id}` | Archive group (soft) |

### New: Card CRUD (`/api/v1/metering/pricing/cards`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/metering/pricing/cards` | Create card with rates |
| GET | `/api/v1/metering/pricing/cards` | List cards (cursor pagination) |
| GET | `/api/v1/metering/pricing/cards/{card_id}` | Get card with rates |
| PATCH | `/api/v1/metering/pricing/cards/{card_id}` | Update card metadata |
| DELETE | `/api/v1/metering/pricing/cards/{card_id}` | Archive card |

### Modified: Rate management (via Card)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/metering/pricing/cards/{card_id}/rates` | Add rate to card |
| PUT | `/api/v1/metering/pricing/cards/{card_id}/rates/{rate_id}` | Update rate (soft-expire old, create new) |
| DELETE | `/api/v1/metering/pricing/cards/{card_id}/rates/{rate_id}` | Deactivate rate |

### Modified: existing endpoints

- `POST /api/v1/metering/usage` — accepts `group` (string) instead of `group_keys` (dict)
- `GET /api/v1/metering/pricing/rates` — deprecated in favour of card-based endpoints
- `POST /api/v1/metering/pricing/rates` — deprecated in favour of card-based endpoints

### Dashboard-specific endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/platform/groups/{group_id}/cards` | Cards used in this group (derived from events) |
| GET | `/api/v1/platform/groups/tree` | Full margin hierarchy tree for dashboard |

---

## Migration Strategy

Since the platform is not live and has no production data, migrations can be done as direct replacements without backward compatibility periods.

### Phase 1: New models + schema changes

1. Create `apps/platform/groups/` app with Group model
2. Create Card model in `apps/metering/pricing/`
3. Rename ProviderRate → Rate, add `card` FK
4. Replace `group_keys` JSONField with `group` CharField on UsageEvent
5. Replace `markup_percentage_micros` and `fixed_uplift_micros` with `margin_pct` on TenantMarkup
6. Add `group_label` to Tenant
7. Run migrations

### Phase 2: Data migration (ProviderRate → Card + Rate)

1. Group existing ProviderRates by `(tenant, provider, event_type, dimensions_hash)`
2. Create a Card for each group, copying shared fields (provider, event_type, dimensions, dimensions_hash, name derived from provider + first dimension value)
3. Create Rate records from each ProviderRate, linking to the parent Card
4. Convert any existing TenantMarkup values: `margin = markup / (1 + markup)`
5. Verify data integrity (rate count matches, costs preserved)

### Phase 3: Update services + API

1. Update PricingService to find Card → get Rates (instead of individual ProviderRates)
2. Add Group resolution step in margin calculation
3. Update API schemas: `group` replaces `group_keys` in request/response
4. Add Group CRUD endpoints, Card CRUD endpoints, nested Rate endpoints
5. Deprecate old standalone rate endpoints
6. Update SDK: `group` parameter replaces `group_keys`

### Phase 4: Cleanup

1. Remove old ProviderRate model
2. Remove `group_keys` field, GIN index, and validation code
3. Remove `markup_percentage_micros` and `fixed_uplift_micros` from TenantMarkup
4. Remove old rate endpoint handlers
5. Update all tests

---

## Dashboard Tree Derivation

The UI margin hierarchy tree is not stored — it's derived:

```
1. Fetch all active Groups for tenant (with parent relationships)
2. For each Group, find Cards used via event data:
   SELECT DISTINCT e.provider, e.event_type, 
          encode(digest(e.properties::text, 'sha256'), 'hex') as dims_hash
   FROM usage_events e
   WHERE e.group = {group.slug} AND e.tenant_id = {tenant.id}
   — then JOIN to Card on (tenant, provider, event_type, dimensions_hash)
3. Build tree: Default → Groups → Cards under each Group
4. Annotate each node with effective margin (own or inherited)
```

**Performance note:** At scale, the "cards in this group" query may need materialisation (a lightweight association table updated on event recording, or a periodic aggregation task). The schema supports this optimisation without changes — it's an implementation concern for when query latency warrants it.

---

## Validation Rules

### Group

- `slug`: 2-64 characters, lowercase alphanumeric + underscores, must start with letter (same pattern as group_keys key validation)
- `margin_pct`: 0.00 to 99.99 (null allowed for inheritance)
- `parent`: must belong to same tenant, no circular references
- `status`: active groups have unique (tenant, slug)

### Card

- `name`: required, max 255 characters
- `provider`: required, max 100 characters
- `event_type`: required, max 100 characters
- `dimensions_hash`: auto-calculated SHA256 of sorted dimensions
- Active cards have unique (tenant, provider, event_type, dimensions_hash)

### Rate

- `metric_name`: required, max 100 characters
- `cost_per_unit_micros`: required, positive integer
- `unit_quantity`: required, positive integer, default 1,000,000
- Active rates (valid_to IS NULL) have unique (card, metric_name)

### UsageEvent.group

- Optional string, max 255 characters
- Not validated against Group model at recording time (permissive write path)
- Unmatched values show as "unmapped" in dashboard

---

## Future Considerations

### Already wired, not built yet

- **Group nesting**: `parent` FK on Group supports sub-groups. Resolution walks up the parent chain. UI shows nested tree. No schema change needed.
- **Dashboard tree materialisation**: Lightweight M2M or aggregation cache for "cards in this group". Added when query performance warrants it.

### Potential future additions

- **Per-customer Group overrides**: Customer-specific margin for a Group. Could be a `CustomerGroupOverride` model or a nullable customer FK on a margin config.
- **Group-level analytics**: Revenue/cost breakdowns by Group. Straightforward with the `group` field on events.
- **Rate card templates**: Card with `is_template=True` that gets cloned to a tenant. No schema change.
- **Tiered pricing**: RateTier model under Rate for volume-based pricing. Card and Group unaffected.
- **Multiple billing dimensions**: If ever needed, `group` could evolve to a dict or a second field could be added. YAGNI for now — no major billing platform supports multiple dimensions.
