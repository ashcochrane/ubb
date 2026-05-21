import { selectProvider } from "@/lib/api-provider";
import * as mock from "./mock";
import * as api from "./api";

// Templates are UI-only — both providers serve the same static data.
const apiWithTemplates = { ...api, getTemplates: mock.getTemplates };

export const pricingCardsApi = selectProvider({ mock, api: apiWithTemplates });
