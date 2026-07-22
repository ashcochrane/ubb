import { useState, type ReactNode } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { AlertTriangle, Lock, Check, Copy } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { EmptyState } from "./empty-state";
import { errorMessage } from "@/api/errors";
import { cn } from "@/lib/utils";

/**
 * Render-prop wrapper that resolves the four canonical states of a query:
 * loading → error → empty → data. Keeps every list/detail screen consistent.
 *
 *   <QueryState query={q} empty={{ title: "No customers yet" }}>
 *     {(data) => <Table>…</Table>}
 *   </QueryState>
 */
export function QueryState<T>({
  query,
  children,
  loading,
  empty,
  isEmpty,
}: {
  query: Pick<UseQueryResult<T>, "data" | "isLoading" | "isError" | "error" | "refetch">;
  children: (data: T) => ReactNode;
  loading?: ReactNode;
  empty?: { title: string; description?: string };
  /** Custom emptiness test; defaults to null/undefined or empty-array data. */
  isEmpty?: (data: T) => boolean;
}) {
  if (query.isLoading) return <>{loading ?? <LoadingRows />}</>;
  if (query.isError) return <ErrorInline error={query.error} onRetry={() => query.refetch()} />;
  const data = query.data;
  if (data === undefined || data === null) {
    return empty ? <EmptyState {...empty} /> : null;
  }
  const emptyByDefault = Array.isArray(data) && data.length === 0;
  if (empty && (isEmpty ? isEmpty(data) : emptyByDefault)) {
    return <EmptyState {...empty} />;
  }
  return <>{children(data)}</>;
}

/** Skeleton block for initial loads (never spinners, per house style). */
export function LoadingRows({ rows = 5, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)} aria-busy="true" aria-live="polite">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-9 w-full rounded-md" />
      ))}
    </div>
  );
}

/** Inline error with retry — for sections that shouldn't blow up the whole route. */
export function ErrorInline({
  error,
  onRetry,
  title = "Couldn't load this",
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
}) {
  return (
    <Alert variant="destructive" className="items-center">
      <AlertTriangle />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>{errorMessage(error)}</AlertDescription>
      {onRetry && (
        <div className="mt-2">
          <Button variant="outline" size="sm" onClick={onRetry}>
            Try again
          </Button>
        </div>
      )}
    </Alert>
  );
}

/** Shown when a product/module is not enabled for the tenant. */
export function ProductUnavailable({
  product,
  description,
}: {
  product: string;
  description?: string;
}) {
  return (
    <EmptyState
      icon={Lock}
      title={`${product} isn't enabled`}
      description={
        description ??
        `This tenant doesn't have the ${product} product enabled. Enable it in Settings → Products to use this area.`
      }
    />
  );
}

/** A titled content section for detail pages. */
export function Section({
  title,
  description,
  actions,
  children,
  className,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-xl bg-card ring-1 ring-foreground/10", className)}>
      <div className="flex items-start justify-between gap-4 border-b border-border px-4 py-3">
        <div>
          <h2 className="text-sm font-medium">{title}</h2>
          {description && (
            <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
          )}
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

/** Key/value grid for summary blocks. */
export function DetailGrid({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <dl className={cn("grid grid-cols-1 gap-x-8 gap-y-3 sm:grid-cols-2", className)}>
      {children}
    </dl>
  );
}

export function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm">{children ?? <span className="text-muted-foreground">—</span>}</dd>
    </div>
  );
}

/**
 * Read-only field with a copy button. Use for secrets (rotate/create results),
 * API keys, tokens, and technical ids. `mono` renders the value monospaced.
 */
export function CopyField({
  value,
  label,
  mono = true,
  className,
}: {
  value: string;
  label?: string;
  mono?: boolean;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable — no-op */
    }
  };
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      {label && <span className="text-xs text-muted-foreground">{label}</span>}
      <div className="flex items-center gap-1.5">
        <code
          className={cn(
            "min-w-0 flex-1 truncate rounded-md border border-border bg-muted px-2.5 py-1.5 text-xs",
            mono && "font-mono",
          )}
        >
          {value}
        </code>
        <Button
          type="button"
          variant="outline"
          size="icon-sm"
          onClick={copy}
          aria-label="Copy to clipboard"
        >
          {copied ? <Check /> : <Copy />}
        </Button>
      </div>
    </div>
  );
}
