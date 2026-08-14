// Mock implementation — same exported signatures as api.ts. Mutations update
// module-level state so the session stays coherent, and server-side rules
// (currency lock, last-admin guard, invalid_config validation, invitation
// conflicts) are simulated with real ApiProblem rejections.

import type { CursorPage } from "@/api/pagination";
import { ApiProblem } from "@/api/problem";
import { mockDelay } from "@/lib/api-provider";
import { PRODUCTS } from "@/lib/labels";
import { readMockTenantConfig, writeMockTenantConfig } from "@/hooks/use-tenant-config";

import {
  AUDIT_RECORDS,
  BILLING_PERIODS,
  CURRENCY_LOCK_REASON,
  CURRENCY_LOCKED,
  INITIAL_CONNECT_STATUS,
  INITIAL_INVITATIONS,
  INITIAL_MARGIN_THRESHOLD,
  INITIAL_MEMBERS,
  STRIPE_TAX_ACTIVE,
  TENANT_INVOICES,
} from "./mock-data";
import type {
  AuditFilters,
  AuditRecord,
  BillingPeriod,
  ConnectStartResult,
  ConnectStatus,
  Invitation,
  MarginThreshold,
  MarginThresholdInput,
  Member,
  TenantConfig,
  TenantConfigPatch,
  TenantInvoice,
} from "./types";

// Session state (module-level so mutations persist across queries).
// Workspace config lives in the FOUNDATION mock store (@/hooks/use-tenant-config)
// because the nav shell and product gates observe the same ["tenant","config"]
// cache entry — one source of truth prevents refetches reverting mutations.
let members: Member[] = INITIAL_MEMBERS.map((m) => ({ ...m }));
let invitations: Invitation[] = INITIAL_INVITATIONS.map((i) => ({ ...i }));
const connectStatus: ConnectStatus = { ...INITIAL_CONNECT_STATUS };
let marginThreshold: MarginThreshold = { ...INITIAL_MARGIN_THRESHOLD };

function problem(status: number, code: string, title: string, detail: string): ApiProblem {
  return new ApiProblem({ status, code, title, detail });
}

function invalidConfig(detail: string): ApiProblem {
  return problem(422, "invalid_config", "Invalid configuration", detail);
}

function page<T>(rows: T[], cursor: string | undefined, size = 50): CursorPage<T> {
  const start = cursor ? Number.parseInt(cursor, 10) || 0 : 0;
  const data = rows.slice(start, start + size);
  const has_more = start + size < rows.length;
  return { data, has_more, next_cursor: has_more ? String(start + size) : null };
}

// --- Workspace config -------------------------------------------------------

export async function getTenantConfig(): Promise<TenantConfig> {
  await mockDelay();
  return readMockTenantConfig();
}

export async function updateTenantConfig(
  patch: TenantConfigPatch,
): Promise<TenantConfig> {
  await mockDelay(400);
  const config = readMockTenantConfig();
  const next: TenantConfig = { ...config };

  if (patch.default_currency != null && patch.default_currency !== config.default_currency) {
    if (CURRENCY_LOCKED) {
      throw problem(409, "currency_locked", "Currency locked", CURRENCY_LOCK_REASON);
    }
    next.default_currency = patch.default_currency;
  }
  if (patch.products != null) {
    const unknown = patch.products.filter((p) => !(PRODUCTS as readonly string[]).includes(p));
    if (unknown.length > 0) {
      throw invalidConfig(`Unknown products: ${unknown.join(", ")}`);
    }
    // Annotated: the contract enumerates `products` since #240, so the empty
    // branch's bare literal widens to `string[]` without a target type.
    const normalized: TenantConfig["products"] =
      patch.products.length === 0 ? ["metering"] : [...new Set(patch.products)].sort();
    if (!normalized.includes("metering")) {
      throw invalidConfig("The metering product cannot be disabled.");
    }
    next.products = normalized;
  }
  if (patch.billing_mode != null) {
    if (!["meter_only", "prepaid", "postpaid"].includes(patch.billing_mode)) {
      throw invalidConfig(`Unknown billing mode: ${patch.billing_mode}`);
    }
    next.billing_mode = patch.billing_mode;
  }
  if (
    ["prepaid", "postpaid"].includes(next.billing_mode) &&
    !next.products.includes("billing")
  ) {
    throw invalidConfig(
      "Prepaid and postpaid billing modes require the Billing product to be enabled.",
    );
  }
  // NO COST-COVERAGE RULE HERE, AND NOTHING REPLACES IT (#321). This mock
  // enforced its own "needs at least one active cost pricing book" refusal
  // alongside the backend's. Both are gone: the setting they guarded is
  // deleted, and onboarding is not a wall. A mock that kept the rule would be
  // a SECOND definition of a behaviour the server no longer has — and the one
  // a developer meets first, because mock mode is this console's default.
  if (patch.automatic_tax_enabled != null) {
    if (patch.automatic_tax_enabled && !STRIPE_TAX_ACTIVE) {
      throw problem(
        422,
        "stripe_tax_not_active",
        "Stripe Tax not active",
        "Activate Stripe Tax on the connected Stripe account first.",
      );
    }
    next.automatic_tax_enabled = patch.automatic_tax_enabled;
  }
  if (patch.enforcement_mode != null) {
    if (!["off", "enforcing"].includes(patch.enforcement_mode)) {
      throw invalidConfig(`enforcement_mode must be "off" or "enforcing".`);
    }
    next.enforcement_mode = patch.enforcement_mode;
  }
  if (patch.live_counter_maintenance_enabled != null) {
    next.live_counter_maintenance_enabled = patch.live_counter_maintenance_enabled;
  }
  if (patch.min_balance_micros != null) {
    if (patch.min_balance_micros < 0) {
      throw invalidConfig(
        "min_balance_micros is the allowed overdraft magnitude and must be zero or more.",
      );
    }
    next.min_balance_micros = patch.min_balance_micros;
  }
  // Clearable fields: explicit null clears, omitted key preserves.
  if ("soft_min_balance_micros" in patch) {
    const soft = patch.soft_min_balance_micros ?? null;
    const hard = next.min_balance_micros ?? 0;
    // Server rule: the soft VALUE must not exceed the effective hard value —
    // both are wire values whose line sits at minus the value, so a larger
    // soft value would put the wind-down line below the hard stop line.
    if (soft !== null && soft > hard) {
      throw invalidConfig(
        "soft_min_balance_micros must not exceed the hard floor value (the allowed overdraft) — that would place the wind-down line below the hard stop line.",
      );
    }
    next.soft_min_balance_micros = soft;
  }
  if ("default_task_provider_cost_limit_micros" in patch) {
    const limit = patch.default_task_provider_cost_limit_micros ?? null;
    if (limit !== null && limit <= 0) {
      throw invalidConfig("The default task spend limit must be more than zero, or empty.");
    }
    next.default_task_provider_cost_limit_micros = limit;
  }

  writeMockTenantConfig(next);
  return readMockTenantConfig();
}

// --- Margin-alert thresholds ------------------------------------------------

export async function getMarginThreshold(): Promise<MarginThreshold> {
  await mockDelay();
  return { ...marginThreshold };
}

export async function updateMarginThreshold(
  input: MarginThresholdInput,
): Promise<MarginThreshold> {
  await mockDelay(350);
  if (input.consecutive_periods < 1) {
    throw problem(
      422,
      "validation_error",
      "Validation error",
      "consecutive_periods must be 1 or more.",
    );
  }
  marginThreshold = {
    min_margin_pct: input.min_margin_pct,
    consecutive_periods: input.consecutive_periods,
    provider_cost_spike_pct: input.provider_cost_spike_pct,
  };
  return { ...marginThreshold };
}

// --- Stripe Connect ---------------------------------------------------------

export async function getConnectStatus(): Promise<ConnectStatus> {
  await mockDelay(200);
  return { ...connectStatus };
}

export async function startConnect(returnUrl: string): Promise<ConnectStartResult> {
  await mockDelay(400);
  // Simulate the full OAuth loop: "authorize" then bounce straight back with
  // the callback's ?connected= marker appended.
  const sep = returnUrl.includes("?") ? "&" : "?";
  return { authorize_url: `${returnUrl}${sep}connected=true` };
}

// --- Team -------------------------------------------------------------------

function activeAdminCount(): number {
  return members.filter((m) => m.role === "admin" && m.status === "active").length;
}

export async function listMembers(cursor?: string): Promise<CursorPage<Member>> {
  await mockDelay();
  return page(members.map((m) => ({ ...m })), cursor);
}

export async function updateMemberRole(memberId: string, role: string): Promise<Member> {
  await mockDelay(350);
  const member = members.find((m) => m.id === memberId);
  if (!member) throw problem(404, "not_found", "Not found", "Unknown member.");
  if (!["read", "write", "admin"].includes(role)) {
    throw problem(422, "validation_error", "Validation error", `Unknown role: ${role}`);
  }
  if (
    member.role === "admin" &&
    role !== "admin" &&
    member.status === "active" &&
    activeAdminCount() <= 1
  ) {
    throw problem(
      409,
      "conflict",
      "Last admin",
      "This is the workspace's last active Admin — promote someone else first.",
    );
  }
  member.role = role;
  return { ...member };
}

export async function removeMember(memberId: string): Promise<void> {
  await mockDelay(350);
  const member = members.find((m) => m.id === memberId);
  if (!member) throw problem(404, "not_found", "Not found", "Unknown member.");
  if (member.role === "admin" && member.status === "active" && activeAdminCount() <= 1) {
    throw problem(
      409,
      "conflict",
      "Last admin",
      "You can't remove the workspace's last active Admin.",
    );
  }
  members = members.filter((m) => m.id !== memberId);
}

export async function listInvitations(cursor?: string): Promise<CursorPage<Invitation>> {
  await mockDelay();
  return page(invitations.map((i) => ({ ...i })), cursor);
}

export async function createInvitation(input: {
  email: string;
  role: string;
}): Promise<Invitation> {
  await mockDelay(400);
  const email = input.email.trim().toLowerCase();
  if (!["read", "write", "admin"].includes(input.role)) {
    throw problem(422, "validation_error", "Validation error", `Unknown role: ${input.role}`);
  }
  const alreadyMember = members.some((m) => m.email.toLowerCase() === email);
  const alreadyPending = invitations.some(
    (i) => i.email.toLowerCase() === email && i.status === "pending",
  );
  if (alreadyMember || alreadyPending) {
    throw problem(
      409,
      "conflict",
      "Already invited",
      `${email} is already a member or has a pending invitation.`,
    );
  }
  const invitation: Invitation = {
    id: `inv-${Math.random().toString(36).slice(2, 8)}`,
    email,
    role: input.role,
    status: "pending",
    created_at: new Date().toISOString(),
  };
  invitations = [invitation, ...invitations];
  members = [
    {
      id: `mem-${Math.random().toString(36).slice(2, 8)}`,
      email,
      role: input.role,
      status: "pending",
      clerk_user_id: "",
      activated_at: null,
      created_at: invitation.created_at,
    },
    ...members,
  ];
  return { ...invitation };
}

export async function revokeInvitation(invitationId: string): Promise<void> {
  await mockDelay(350);
  const invitation = invitations.find((i) => i.id === invitationId);
  if (!invitation) throw problem(404, "not_found", "Not found", "Unknown invitation.");
  if (invitation.status === "accepted") {
    throw problem(
      409,
      "conflict",
      "Already accepted",
      "This invitation was already accepted — remove the member instead.",
    );
  }
  invitation.status = "revoked";
  members = members.filter(
    (m) => !(m.email.toLowerCase() === invitation.email.toLowerCase() && m.status === "pending"),
  );
}

// --- UBB platform bill ------------------------------------------------------

export async function listBillingPeriods(cursor?: string): Promise<CursorPage<BillingPeriod>> {
  await mockDelay();
  return page(BILLING_PERIODS, cursor);
}

export async function listTenantInvoices(cursor?: string): Promise<CursorPage<TenantInvoice>> {
  await mockDelay();
  return page(TENANT_INVOICES, cursor);
}

// --- Audit ledger -----------------------------------------------------------

export async function listAuditRecords(
  filters: AuditFilters,
  cursor?: string,
): Promise<CursorPage<AuditRecord>> {
  await mockDelay();
  const rows = AUDIT_RECORDS.filter(
    (r) =>
      (!filters.action || r.action === filters.action) &&
      (!filters.resource_type || r.resource_type === filters.resource_type) &&
      (!filters.resource_id || r.resource_id === filters.resource_id),
  );
  return page(rows, cursor, 10);
}
