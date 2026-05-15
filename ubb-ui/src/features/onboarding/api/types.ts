import type { MeTenant } from "@/features/auth/api/types";

export interface CreateTenantRequest {
  name: string;
}

export interface CreateTenantResponse {
  tenant: MeTenant;
  apiKey: string | null;
}
