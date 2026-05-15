// src/features/customers/api/mock.ts
import { mockDelay } from "@/lib/api-provider";
import type {
  CreateCustomerRequest,
  CreatedCustomer,
  Customer,
  CustomerListResponse,
  UpdateCustomerRequest,
} from "./types";

let _store: Customer[] = [
  {
    id: "cus_001",
    externalId: "acme",
    stripeCustomerId: "cus_stripe_001",
    status: "active",
    minBalanceMicros: null,
    metadata: {},
    createdAt: new Date().toISOString(),
  } as Customer,
];

export async function listCustomers(): Promise<CustomerListResponse> {
  await mockDelay();
  return { data: _store, hasMore: false, nextCursor: null };
}

export async function getCustomer(id: string): Promise<Customer> {
  await mockDelay();
  const found = _store.find((c) => c.id === id);
  if (!found) throw new Error("not found");
  return found;
}

export async function createCustomer(
  req: CreateCustomerRequest,
): Promise<CreatedCustomer> {
  await mockDelay();
  const created: Customer = {
    id: `cus_${Math.random().toString(36).slice(2, 8)}`,
    externalId: req.externalId,
    stripeCustomerId: req.stripeCustomerId ?? "",
    status: "active",
    minBalanceMicros: null,
    metadata: req.metadata ?? {},
    createdAt: new Date().toISOString(),
  } as Customer;
  _store.push(created);
  return {
    id: created.id,
    externalId: created.externalId,
    stripeCustomerId: created.stripeCustomerId ?? "",
    status: created.status,
  };
}

export async function updateCustomer(
  id: string,
  req: UpdateCustomerRequest,
): Promise<Customer> {
  await mockDelay();
  const idx = _store.findIndex((c) => c.id === id);
  if (idx < 0) throw new Error("not found");
  _store[idx] = {
    ...(_store[idx] as Customer),
    ...(req.status != null ? { status: req.status } : {}),
    ...(req.stripeCustomerId != null
      ? { stripeCustomerId: req.stripeCustomerId }
      : {}),
    ...(req.minBalanceMicros !== undefined
      ? { minBalanceMicros: req.minBalanceMicros }
      : {}),
    ...(req.metadata != null ? { metadata: req.metadata } : {}),
  } as Customer;
  return _store[idx] as Customer;
}

export async function deleteCustomer(id: string): Promise<void> {
  await mockDelay();
  _store = _store.filter((c) => c.id !== id);
}
