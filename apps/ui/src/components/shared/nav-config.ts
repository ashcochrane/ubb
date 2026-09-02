import {
  LayoutDashboard,
  Users,
  Activity,
  ListChecks,
  Tags,
  Wallet,
  Layers,
  Gift,
  Webhook,
  Terminal,
  Settings,
  type LucideIcon,
} from "lucide-react";

import type { TenantProduct } from "@/lib/vocabulary";

export interface NavItem {
  title: string;
  url: string;
  icon: LucideIcon;
  /** Only show when this product is enabled for the tenant. */
  product?: TenantProduct;
}

export interface NavSection {
  /** Section label (e.g. "REVENUE"). Omit for ungrouped top items. */
  label?: string;
  items: NavItem[];
}

// Routes must exist for every entry; items are filtered by the tenant's
// enabled products (TenantConfigOut.products) through `visibleNavSections`.
export const navSections: NavSection[] = [
  {
    items: [
      { title: "Overview", url: "/", icon: LayoutDashboard },
      { title: "Events", url: "/events", icon: Activity },
      // UNGATED, beside Events, on purpose (#423, spec §25 Q6): a unit of work
      // is a kernel concept no product owns, so what a tenant's business
      // sells is visible to every tenant and not only to the billing ones.
      // No `product` here is the whole of that decision, and
      // `nav-config.test.ts` holds it.
      { title: "Tasks", url: "/tasks", icon: ListChecks },
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

/**
 * The sections a tenant with these products actually sees.
 *
 * Product-gated navigation: never show a surface the tenant can't use. A
 * section left with nothing visible disappears with its label. Pure over the
 * product list rather than over the config hook so a test can hold a tab's
 * gating to a product set it names — `undefined` is the config still loading,
 * and it hides exactly what an empty product list hides.
 */
export function visibleNavSections(
  products: readonly string[] | undefined,
): NavSection[] {
  return navSections
    .map((section) => ({
      ...section,
      items: section.items.filter(
        (item) => !item.product || (products?.includes(item.product) ?? false),
      ),
    }))
    .filter((section) => section.items.length > 0);
}
