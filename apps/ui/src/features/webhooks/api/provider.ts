import { selectProvider } from "@/lib/api-provider";

import * as api from "./api";
import * as mock from "./mock";

export const webhooksApi = selectProvider({ mock, api });
