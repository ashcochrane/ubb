import { selectProvider } from "@/lib/api-provider";

import * as api from "./api";
import * as mock from "./mock";

export const eventsApi = selectProvider({ mock, api });
