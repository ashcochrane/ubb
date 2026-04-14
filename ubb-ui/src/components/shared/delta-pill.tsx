import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface DeltaPillProps {
  trend: "up" | "down" | "flat";
  children: ReactNode;
  className?: string;
}

const TREND_STYLES: Record<DeltaPillProps["trend"], string> = {
  up: "bg-green-light text-green-text",
  down: "bg-red-light text-red-text",
  flat: "bg-bg-subtle text-text-muted",
};

export function DeltaPill({ trend, children, className }: DeltaPillProps) {
  return (
    <span
      data-trend={trend}
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium",
        TREND_STYLES[trend],
        className,
      )}
    >
      <TrendIcon trend={trend} />
      {children}
    </span>
  );
}

function TrendIcon({ trend }: { trend: DeltaPillProps["trend"] }) {
  if (trend === "flat") {
    return (
      <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden="true">
        <rect x="1" y="3.5" width="6" height="1" fill="currentColor" />
      </svg>
    );
  }
  return (
    <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden="true">
      {trend === "up" ? (
        <path d="M4 1L7 5H1z" fill="currentColor" />
      ) : (
        <path d="M4 7L7 3H1z" fill="currentColor" />
      )}
    </svg>
  );
}
