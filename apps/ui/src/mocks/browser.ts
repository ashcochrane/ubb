import { setupWorker } from "msw/browser";
import { handlers } from "./handlers";

/** MSW worker for the mock provider (VITE_API_PROVIDER=mock). */
export const worker = setupWorker(...handlers);
