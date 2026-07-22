// src/features/billing/api/mock.ts
import { mockDelay } from "@/lib/api-provider";
import type { DefaultMargin, UpdateDefaultMarginRequest } from "./types";

let _stub: DefaultMargin = { defaultMarginPct: 20 };

export async function getDefaultMargin(): Promise<DefaultMargin> {
  await mockDelay();
  return _stub;
}

export async function updateDefaultMargin(
  req: UpdateDefaultMarginRequest,
): Promise<DefaultMargin> {
  await mockDelay();
  _stub = { defaultMarginPct: req.defaultMarginPct };
  return _stub;
}
