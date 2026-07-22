import { toast } from "sonner";

/**
 * Factory for useMutation onError handlers that surface a toast.
 * Usage: onError: toastOnError("Couldn't save margin changes")
 */
export const toastOnError = (defaultMessage: string) => (error: unknown) => {
  const description =
    error instanceof Error && error.message ? error.message : undefined;
  toast.error(defaultMessage, description ? { description } : undefined);
};
