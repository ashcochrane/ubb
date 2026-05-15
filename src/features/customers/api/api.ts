// src/features/customers/api/api.ts
import { platformApi } from "@/api/client";
import type {
  CreateCustomerRequest,
  CreatedCustomer,
  Customer,
  CustomerListResponse,
  UpdateCustomerRequest,
} from "./types";

export async function listCustomers(params?: {
  cursor?: string;
  limit?: number;
}): Promise<CustomerListResponse> {
  const { data, error } = await platformApi.GET("/customers", {
    params: { query: params },
  });
  if (error || !data) throw error ?? new Error("Failed to list customers");
  return data;
}

export async function getCustomer(customerId: string): Promise<Customer> {
  const { data, error } = await platformApi.GET("/customers/{customer_id}", {
    params: { path: { customer_id: customerId } },
  });
  if (error || !data) throw error ?? new Error("Failed to load customer");
  return data;
}

export async function createCustomer(
  req: CreateCustomerRequest,
): Promise<CreatedCustomer> {
  const { data, error } = await platformApi.POST("/customers", {
    body: req,
  });
  if (error || !data) {
    throw error ?? new Error("Create customer failed");
  }
  return data;
}

export async function updateCustomer(
  customerId: string,
  req: UpdateCustomerRequest,
): Promise<Customer> {
  const { data, error } = await platformApi.PATCH("/customers/{customer_id}", {
    params: { path: { customer_id: customerId } },
    body: req,
  });
  if (error || !data) throw error ?? new Error("Failed to update customer");
  return data;
}

export async function deleteCustomer(customerId: string): Promise<void> {
  const { error } = await platformApi.DELETE("/customers/{customer_id}", {
    params: { path: { customer_id: customerId } },
  });
  if (error) throw error;
}
