// src/features/customers/api/provider.ts
import { selectProvider } from "@/lib/api-provider";
import * as mock from "./mock";
import * as api from "./api";

export const customersApi = selectProvider({ mock, api });
