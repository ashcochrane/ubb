import {
  LayoutDashboard,
  Users,
  Activity,
  Tags,
  Wallet,
  TrendingUp,
  Repeat,
  Gift,
  Webhook,
  ScrollText,
  Settings,
  type LucideIcon,
} from "lucide-react";

/** Product/mode gate for a nav entry. Evaluated against `useAuth()`. */
export type NavGate = "metering" | "billing" | "subscriptions" | "referrals";

export interface NavItem {
  title: string;
  url: string;
  icon: LucideIcon;
  /** Hide unless the tenant has this product / billing posture enabled. */
  gate?: NavGate;
}

export interface NavSection {
  /** Section label (e.g. "METERING"). Omit for ungrouped top items. */
  label?: string;
  items: NavItem[];
}

/**
 * The full tenant-admin information architecture. Product-gated items are
 * hidden when the tenant lacks the relevant product (see nav-shell). Sections
 * with no visible items are dropped automatically.
 */
export const navSections: NavSection[] = [
  {
    items: [
      { title: "Overview", url: "/", icon: LayoutDashboard },
      { title: "Customers", url: "/customers", icon: Users },
    ],
  },
  {
    label: "METERING",
    items: [
      { title: "Usage", url: "/usage", icon: Activity, gate: "metering" },
      { title: "Pricing", url: "/pricing", icon: Tags, gate: "metering" },
    ],
  },
  {
    label: "BILLING",
    items: [
      { title: "Billing", url: "/billing", icon: Wallet, gate: "billing" },
      { title: "Margin", url: "/margin", icon: TrendingUp, gate: "billing" },
    ],
  },
  {
    label: "GROWTH",
    items: [
      { title: "Subscriptions", url: "/subscriptions", icon: Repeat, gate: "subscriptions" },
      { title: "Referrals", url: "/referrals", icon: Gift, gate: "referrals" },
    ],
  },
  {
    label: "PLATFORM",
    items: [
      { title: "Webhooks", url: "/webhooks", icon: Webhook },
      { title: "Audit log", url: "/audit", icon: ScrollText },
      { title: "Settings", url: "/settings", icon: Settings },
    ],
  },
];
