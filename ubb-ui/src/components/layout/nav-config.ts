import {
  LayoutDashboard,
  Users,
  Gauge,
  DollarSign,
  CreditCard,
  BarChart3,
  Search,
  Wallet,
  ArrowUpDown,
  FileText,
  ArrowUpCircle,
  Settings,
  UserPlus,
  Webhook,
  Link,
} from "lucide-react";

export const navConfig = [
  { title: "Dashboard", url: "/", icon: LayoutDashboard },
  { title: "Customers", url: "/customers", icon: Users },
  {
    title: "Metering",
    icon: Gauge,
    items: [
      { title: "Pricing", url: "/metering/pricing", icon: DollarSign },
      { title: "Usage Explorer", url: "/metering/usage", icon: Search },
      { title: "Analytics", url: "/metering/analytics", icon: BarChart3 },
    ],
  },
  {
    title: "Billing",
    icon: CreditCard,
    items: [
      { title: "Wallets", url: "/billing/wallets", icon: Wallet },
      { title: "Transactions", url: "/billing/transactions", icon: ArrowUpDown },
      { title: "Invoices", url: "/billing/invoices", icon: FileText },
      { title: "Top-Ups", url: "/billing/top-ups", icon: ArrowUpCircle },
    ],
  },
  {
    title: "Settings",
    icon: Settings,
    items: [
      { title: "General", url: "/settings/general", icon: Settings },
      { title: "Team", url: "/settings/team", icon: UserPlus },
      { title: "Webhooks", url: "/settings/webhooks", icon: Webhook },
      { title: "Stripe", url: "/settings/stripe", icon: Link },
    ],
  },
];
