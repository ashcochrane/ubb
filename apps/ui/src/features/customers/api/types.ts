import type {
  PlatformSchemas,
  MarginSchemas,
  BillingSchemas,
  MeteringSchemas,
  SubscriptionSchemas,
} from "@/api/types";

// Create (the only platform customer write that returns a customer)
export type CreateCustomerRequest = PlatformSchemas["CreateCustomerRequest"];
export type CustomerResponse = PlatformSchemas["CustomerResponse"];

// Roster + margin (the closest thing to a customer directory)
export type MarginList = MarginSchemas["MarginListOut"];
export type MarginRow = MarginSchemas["CustomerMarginListRow"];
export type CustomerMargin = MarginSchemas["CustomerMarginOut"];
export type MarginTrend = MarginSchemas["MarginTrendOut"];
export type RevenueProfile = MarginSchemas["RevenueProfileOut"];
export type RevenueProfileIn = MarginSchemas["RevenueProfileIn"];
export type RevenueMode = MarginSchemas["RevenueModeOut"];
export type RevenueModeIn = MarginSchemas["RevenueModeIn"];

// Billing (customer-scoped)
export type Grant = BillingSchemas["GrantOut"];
export type CreateGrantRequest = BillingSchemas["CreateGrantRequest"];
export type BudgetConfig = BillingSchemas["BudgetConfigOut"];
export type BudgetConfigIn = BillingSchemas["BudgetConfigIn"];
export type BudgetStatus = BillingSchemas["BudgetStatusOut"];
export type BillingProfile = BillingSchemas["CustomerBillingProfileOut"];
export type BillingProfileIn = BillingSchemas["CustomerBillingProfileIn"];
export type PastLimitReport = BillingSchemas["PastLimitReportResponse"];

// Metering (customer-scoped)
export type CustomerMarkup = MeteringSchemas["TenantMarkupOut"];
export type CustomerMarkupIn = MeteringSchemas["TenantMarkupIn"];
export type AssignBook = MeteringSchemas["AssignIn"];
export type UsageEvent = MeteringSchemas["UsageEventOut"];

// Subscriptions (customer-scoped)
export type StripeSubscription = SubscriptionSchemas["StripeSubscriptionOut"];
export type SubscriptionInvoice = SubscriptionSchemas["SubscriptionInvoiceOut"];
export type SubscribeIn = PlatformSchemas["SubscribeIn"];
export type SeatsIn = PlatformSchemas["SeatsIn"];
export type SubscriptionCancelIn = PlatformSchemas["SubscriptionCancelIn"];
