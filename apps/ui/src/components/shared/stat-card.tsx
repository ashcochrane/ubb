import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { DeltaPill } from "./delta-pill";

export type StatCardVariant = "muted" | "raised" | "purple";

export interface StatCardProps {
  label: string;
  value: ReactNode;
  /** Legacy prop — colored text delta. Preserved for back-compat. */
  change?: { value: string; positive: boolean };
  /** New: renders a <DeltaPill> with up/down/flat styling. */
  trend?: "up" | "down" | "flat";
  /** Label text inside the delta pill (required when `trend` is set). */
  trendLabel?: string;
  /** New: optional slot rendered below the delta row (sparkline). */
  sparkline?: ReactNode;
  subtitle?: string;
  variant?: StatCardVariant;
  className?: string;
}

/**
 * Shared stat card used across dashboard, billing, and customer mapping.
 *
 * Variants:
 * - `muted`  (default) — quiet bg-accent/50 card used by billing + mapping pages
 * - `raised`            — bordered bg-bg-surface card used by the v4 dashboard KPI grid
 * - `purple`            — muted layout with a purple-tinted value (billing mode)
 */
export function StatCard({
  label,
  value,
  change,
  trend,
  trendLabel,
  sparkline,
  subtitle,
  variant = "muted",
  className,
}: StatCardProps) {
  const isRaised = variant === "raised";

  return (
    <div
      data-variant={variant}
      className={cn(
        isRaised
          ? "rounded-md border border-border bg-bg-surface px-5 pt-[18px] pb-[14px] transition-colors hover:border-border-mid hover:shadow-md"
          : "rounded-lg bg-accent/50 px-3 py-2.5",
        className,
      )}
    >
      <div
        className={cn(
          "text-label text-text-muted",
          isRaised && "mb-1.5 font-medium",
        )}
      >
        {label}
      </div>
      <div
        className={cn(
          isRaised
            ? "mb-1 text-[26px] font-bold leading-[1.15] tracking-[-0.6px]"
            : "mt-1 text-[17px] font-semibold tracking-tight",
          variant === "purple" && "text-purple-fg",
        )}
      >
        {value}
      </div>

      {trend && <DeltaPill trend={trend}>{trendLabel ?? ""}</DeltaPill>}

      {!trend && change && (
        <div
          className={cn(
            "mt-0.5 text-muted",
            change.positive ? "text-success-dark" : "text-danger-dark",
          )}
        >
          {change.positive ? "+" : ""}
          {change.value}
        </div>
      )}

      {subtitle && !change && !trend && (
        <div className="mt-0.5 text-tiny text-text-muted/60">{subtitle}</div>
      )}

      {sparkline && <div className="-mx-1 mt-2.5 h-8">{sparkline}</div>}
    </div>
  );
}
