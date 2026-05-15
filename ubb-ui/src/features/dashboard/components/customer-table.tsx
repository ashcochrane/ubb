import { Download } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatCostMicros, formatEventCount } from "@/lib/format";
import type { DashboardCustomerRow } from "../api/types";

interface CustomerTableProps {
  customers: DashboardCustomerRow[];
  onExport?: () => void;
}

export function CustomerTable({ customers, onExport }: CustomerTableProps) {
  return (
    <div className="overflow-hidden rounded-md border border-border bg-bg-surface">
      <div className="flex items-center justify-between px-6 py-[18px]">
        <div className="text-[14px] font-semibold tracking-[-0.15px]">Customer profitability</div>
        <button
          type="button"
          onClick={onExport}
          disabled={!onExport}
          className="inline-flex items-center gap-1.5 rounded-full border border-border-mid bg-bg-surface px-3 py-[5px] text-[11px] font-medium text-text-secondary transition-colors hover:bg-bg-subtle hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-bg-surface disabled:hover:text-text-secondary"
        >
          <Download className="h-[11px] w-[11px]" />
          Export table
        </button>
      </div>

      <table className="w-full border-collapse">
        <thead>
          <tr>
            <Th>Customer</Th>
            <Th align="right">Revenue</Th>
            <Th align="right">API costs</Th>
            <Th align="right">Margin</Th>
            <Th>Margin %</Th>
            <Th align="right">Events</Th>
          </tr>
        </thead>
        <tbody>
          {customers.length === 0 ? (
            <tr>
              <td colSpan={6} className="px-6 py-10 text-center text-[13px] text-text-muted">
                No customers in the current view.
              </td>
            </tr>
          ) : (
            customers.map((c) => (
              <tr
                key={c.customerId}
                className="border-b border-bg-subtle last:border-0 transition-colors hover:bg-bg-page"
              >
                <Td>
                  <div className="font-semibold">{c.externalId}</div>
                  <div className="mt-0.5 font-mono text-[10px] text-text-muted">{c.customerId}</div>
                </Td>
                <Td align="right" mono>
                  {formatCostMicros(c.revenueMicros)}
                </Td>
                <Td align="right" mono>
                  {formatCostMicros(c.apiCostsMicros)}
                </Td>
                <Td align="right" mono>
                  <span className={cn(c.marginMicros < 0 && "text-red")}>
                    {c.marginMicros < 0
                      ? `−${formatCostMicros(Math.abs(c.marginMicros))}`
                      : formatCostMicros(c.marginMicros)}
                  </span>
                </Td>
                <Td>
                  <MarginCell percentage={c.marginPercentage} />
                </Td>
                <Td align="right" mono className="text-text-muted">
                  {formatEventCount(c.eventCount)}
                </Td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function Th({
  children,
  align = "left",
}: {
  children: React.ReactNode;
  align?: "left" | "right" | "center";
}) {
  return (
    <th
      className={cn(
        "border-t border-b border-border bg-bg-subtle px-6 py-2.5 text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted",
        align === "right" && "text-right",
        align === "center" && "text-center",
        align === "left" && "text-left",
      )}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  align = "left",
  mono,
  className,
}: {
  children: React.ReactNode;
  align?: "left" | "right" | "center";
  mono?: boolean;
  className?: string;
}) {
  return (
    <td
      className={cn(
        "px-6 py-3.5 align-middle text-[13px]",
        align === "right" && "text-right",
        align === "center" && "text-center",
        mono && "font-mono text-[12px]",
        className,
      )}
    >
      {children}
    </td>
  );
}

function MarginCell({ percentage }: { percentage: number }) {
  const clamped = Math.max(-100, Math.min(100, percentage));
  const barColor =
    percentage < 0
      ? "bg-red"
      : percentage < 50
        ? "bg-amber"
        : "bg-accent-base";
  const textColor =
    percentage < 0
      ? "text-red-text"
      : percentage < 50
        ? "text-amber-text"
        : "text-green-text";

  const width = percentage < 0 ? Math.abs(clamped) : clamped;

  return (
    <div className="flex items-center gap-1.5">
      <div className="h-1 w-12 overflow-hidden rounded-full bg-bg-subtle">
        <div className={cn("h-full rounded-full", barColor)} style={{ width: `${width}%` }} />
      </div>
      <span className={cn("font-mono text-[12px] font-semibold", textColor)}>
        {percentage < 0 ? "−" : ""}
        {Math.abs(percentage)}%
      </span>
    </div>
  );
}
