// src/features/billing-ops/api/provider.ts
import { selectProvider } from "@/lib/api-provider";
import * as mock from "./mock";
import * as api from "./api";

export const billingOpsApi = selectProvider({ mock, api });
