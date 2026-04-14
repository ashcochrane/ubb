import {
  LayoutDashboard,
  Users,
  CreditCard,
  Package,
  DollarSign,
  Download,
  Settings,
  Activity,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  title: string;
  url: string;
  icon: LucideIcon;
}

export interface NavSection {
  /** Section label (e.g. "METERING"). Omit for ungrouped top items. */
  label?: string;
  items: NavItem[];
  /** Only show this section when this condition is true. Undefined = always show. */
  visibleWhen?: "billing";
}

export const navSections: NavSection[] = [
  {
    items: [
      { title: "Dashboard", url: "/", icon: LayoutDashboard },
      { title: "Customers", url: "/customers", icon: Users },
    ],
  },
  {
    label: "METERING",
    items: [
      { title: "Events", url: "/events", icon: Activity },
      { title: "Pricing Cards", url: "/pricing-cards", icon: CreditCard },
      { title: "Products", url: "/products", icon: Package },
    ],
  },
  {
    label: "BILLING",
    visibleWhen: "billing",
    items: [
      { title: "Billing", url: "/billing", icon: DollarSign },
    ],
  },
  {
    items: [
      { title: "Export", url: "/export", icon: Download },
    ],
  },
  {
    label: "SETTINGS",
    items: [
      { title: "Settings", url: "/settings", icon: Settings },
    ],
  },
];
