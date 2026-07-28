import {
  LayoutDashboard,
  Users,
  Activity,
  Tags,
  Wallet,
  Layers,
  Gift,
  Webhook,
  Terminal,
  Settings,
  type LucideIcon,
} from "lucide-react";

import type { Product } from "@/lib/labels";

export interface NavItem {
  title: string;
  url: string;
  icon: LucideIcon;
  /** Only show when this product is enabled for the tenant. */
  product?: Product;
}

export interface NavSection {
  /** Section label (e.g. "REVENUE"). Omit for ungrouped top items. */
  label?: string;
  items: NavItem[];
}

// Routes must exist for every entry; items are filtered by the tenant's
// enabled products (TenantConfigOut.products) in the nav shell.
export const navSections: NavSection[] = [
  {
    items: [
      { title: "Overview", url: "/", icon: LayoutDashboard },
      { title: "Events", url: "/events", icon: Activity },
      { title: "Customers", url: "/customers", icon: Users },
    ],
  },
  {
    label: "REVENUE",
    items: [
      { title: "Pricing", url: "/pricing", icon: Tags },
      { title: "Billing", url: "/billing", icon: Wallet, product: "billing" },
      { title: "Plans", url: "/plans", icon: Layers, product: "billing" },
      { title: "Referrals", url: "/referrals", icon: Gift, product: "referrals" },
    ],
  },
  {
    label: "PLATFORM",
    items: [
      { title: "Webhooks", url: "/webhooks", icon: Webhook },
      { title: "Developers", url: "/developers", icon: Terminal },
      { title: "Settings", url: "/settings", icon: Settings },
    ],
  },
];
