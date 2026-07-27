import { AlertTriangle } from "lucide-react";

import { isFeatureNotEnabled, isForbidden, problemMessage } from "@/api/problem";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Inline failure state for a query-backed section. Problem-aware: permission
 * and product-gate failures get specific copy instead of a generic error.
 */
export function ErrorCard({
  error,
  onRetry,
  title,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
  className?: string;
}) {
  const heading = isForbidden(error)
    ? "You don't have access to this"
    : isFeatureNotEnabled(error)
      ? "This product isn't enabled"
      : (title ?? "Couldn't load this section");

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-lg border border-border bg-bg-surface px-6 py-8 text-center",
        className,
      )}
    >
      <AlertTriangle className="h-5 w-5 text-text-muted" strokeWidth={1.5} />
      <p className="text-sm font-medium text-text-primary">{heading}</p>
      <p className="max-w-sm text-[13px] text-text-secondary">{problemMessage(error)}</p>
      {onRetry && !isForbidden(error) && !isFeatureNotEnabled(error) && (
        <Button variant="outline" size="sm" onClick={onRetry} className="mt-2">
          Try again
        </Button>
      )}
    </div>
  );
}
