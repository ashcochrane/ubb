import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import type { TenantConfig } from "@/features/auth/api/types";

const meData = vi.fn<() => { tenant: Partial<TenantConfig> } | undefined>();

vi.mock("@/features/auth/api/queries", () => ({
  useMe: () => ({ data: meData() }),
}));

import { useAuth } from "./use-auth";

function tenant(overrides: Partial<TenantConfig> = {}): Partial<TenantConfig> {
  return {
    name: "Acme",
    billing_mode: "meter_only",
    products: [],
    default_currency: "USD",
    stripe_connected_account_id: "",
    is_active: true,
    automatic_tax_enabled: false,
    enforcement_mode: "off",
    ...overrides,
  };
}

describe("useAuth mode flags", () => {
  beforeEach(() => {
    meData.mockReset();
  });

  it("is neither prepaid nor postpaid, but is billing-mode, for meter_only + billing product", () => {
    meData.mockReturnValue({ tenant: tenant({ billing_mode: "meter_only", products: ["billing"] }) });
    const { result } = renderHook(() => useAuth());
    expect(result.current.isPrepaid).toBe(false);
    expect(result.current.isPostpaid).toBe(false);
    // isBillingMode conflates "has a billing posture" with "billing product enabled" —
    // deliberately kept for call sites that mean "billing at all".
    expect(result.current.isBillingMode).toBe(true);
  });

  it("sets isPrepaid (and not isPostpaid) for billing_mode: prepaid", () => {
    meData.mockReturnValue({ tenant: tenant({ billing_mode: "prepaid" }) });
    const { result } = renderHook(() => useAuth());
    expect(result.current.isPrepaid).toBe(true);
    expect(result.current.isPostpaid).toBe(false);
    expect(result.current.isBillingMode).toBe(true);
  });

  it("sets isPostpaid (and not isPrepaid) for billing_mode: postpaid — the core defect this fixes", () => {
    meData.mockReturnValue({ tenant: tenant({ billing_mode: "postpaid" }) });
    const { result } = renderHook(() => useAuth());
    expect(result.current.isPrepaid).toBe(false);
    expect(result.current.isPostpaid).toBe(true);
    expect(result.current.isBillingMode).toBe(true);
  });

  it("threads enforcement_mode through from tenant config", () => {
    meData.mockReturnValue({ tenant: tenant({ enforcement_mode: "enforcing" }) });
    const { result } = renderHook(() => useAuth());
    expect(result.current.enforcementMode).toBe("enforcing");
  });

  it("reports null flags before the tenant loads", () => {
    meData.mockReturnValue(undefined);
    const { result } = renderHook(() => useAuth());
    expect(result.current.isPrepaid).toBe(false);
    expect(result.current.isPostpaid).toBe(false);
    expect(result.current.enforcementMode).toBeNull();
  });
});
