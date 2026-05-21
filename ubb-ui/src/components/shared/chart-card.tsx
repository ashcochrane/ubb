import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface ChartCardProps {
  title: string;
  legend?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function ChartCard({ title, legend, actions, children, className }: ChartCardProps) {
  return (
    <div
      className={cn(
        "rounded-md border border-border bg-bg-surface p-6 transition-colors",
        "hover:border-border-mid",
        className,
      )}
    >
      <div className="mb-5 flex items-center justify-between gap-4">
        <div className="text-[14px] font-semibold tracking-[-0.15px]">{title}</div>
        {(legend || actions) && (
          <div className="flex items-center gap-4">
            {legend}
            {actions}
          </div>
        )}
      </div>
      {children}
    </div>
  );
}
