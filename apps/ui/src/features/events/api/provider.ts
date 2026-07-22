// src/features/events/api/provider.ts
import { selectProvider } from "@/lib/api-provider";
import * as mock from "./mock";
import * as api from "./api";

export const eventsApi = selectProvider({ mock, api });
