// src/features/billing-ops/api/mock.ts
import { mockDelay } from "@/lib/api-provider";
import type {
  Balance,
  ConfigureAutoTopUpRequest,
  CreateTopUpRequest,
  RefundRequest,
  TransactionsPage,
  WithdrawRequest,
} from "./types";

const _balances = new Map<string, Balance>();

export async function getBalance(customerId: string): Promise<Balance> {
  await mockDelay();
  return _balances.get(customerId) ?? { balanceMicros: 0, currency: "USD" };
}

export async function getTransactions(): Promise<TransactionsPage> {
  await mockDelay();
  return { data: [], hasMore: false, nextCursor: null };
}

export async function createTopUp(
  customerId: string,
  body: CreateTopUpRequest,
): Promise<void> {
  await mockDelay();
  const current = _balances.get(customerId)?.balanceMicros ?? 0;
  _balances.set(customerId, {
    balanceMicros: current + body.amountMicros,
    currency: "USD",
  });
}

export async function withdraw(
  customerId: string,
  body: WithdrawRequest,
): Promise<void> {
  await mockDelay();
  const current = _balances.get(customerId)?.balanceMicros ?? 0;
  _balances.set(customerId, {
    balanceMicros: current - body.amountMicros,
    currency: "USD",
  });
}

export async function refund(
  customerId: string,
  body: RefundRequest,
): Promise<void> {
  void customerId;
  void body;
  await mockDelay();
}

export async function configureAutoTopUp(
  customerId: string,
  body: ConfigureAutoTopUpRequest,
): Promise<void> {
  void customerId;
  void body;
  await mockDelay();
}
