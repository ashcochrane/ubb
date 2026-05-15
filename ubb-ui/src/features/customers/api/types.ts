// src/features/customers/api/types.ts
import type { PlatformSchemas } from "@/api/types";

export type Customer = PlatformSchemas["CustomerDetailResponse"];
export type CustomerListResponse = PlatformSchemas["CustomerListResponse"];
// POST /customers returns 201 with CustomerResponse, which is a thinner shape
// than CustomerDetailResponse (no `metadata` etc.). Re-export for clarity.
export type CreatedCustomer = PlatformSchemas["CustomerResponse"];
export type CreateCustomerRequest = PlatformSchemas["CreateCustomerRequest"];
export type UpdateCustomerRequest = PlatformSchemas["UpdateCustomerRequest"];

export type CustomerStatus = "active" | "suspended" | "archived";
export const CUSTOMER_STATUSES: CustomerStatus[] = [
  "active",
  "suspended",
  "archived",
];
