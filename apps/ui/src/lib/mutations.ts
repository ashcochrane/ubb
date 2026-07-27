import { toast } from "sonner";

import { isForbidden, problemMessage } from "@/api/problem";

/**
 * Factory for useMutation onError handlers that surface a toast.
 * Problem-aware: role-floor 403s get a consistent explanation, and the
 * backend's own detail text is never swallowed.
 * Usage: onError: toastOnError("Couldn't save the budget")
 */
export const toastOnError = (defaultMessage: string) => (error: unknown) => {
  const description = problemMessage(error);
  toast.error(
    isForbidden(error) ? "You don't have permission to do that" : defaultMessage,
    description ? { description } : undefined,
  );
};

/** Success toast with an optional detail line. */
export function toastSuccess(message: string, description?: string) {
  toast.success(message, description ? { description } : undefined);
}
