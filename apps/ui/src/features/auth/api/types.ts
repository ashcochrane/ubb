export interface MeTenantUser {
  id: string;
  email: string;
  role: "owner" | "admin" | "member";
}

export interface MeTenant {
  id: string;
  name: string;
  products: string[];
  pricingCardsCount: number;
  usageEventsCount: number;
}

export interface Me {
  tenantUser: MeTenantUser | null;
  tenant: MeTenant | null;
  onboardingCompleted: boolean;
}
