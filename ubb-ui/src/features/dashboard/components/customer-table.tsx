import { Download } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatEventCount } from "@/lib/format";
import type { CustomerRow } from "../api/types";

interface CustomerTableProps {
  customers: CustomerRow[];
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
            <Th align="center">Type</Th>
            <Th align="right">API costs</Th>
            <Th align="right">Margin</Th>
            <Th>Margin %</Th>
            <Th align="right">Events</Th>
          </tr>
        </thead>
        <tbody>
          {customers.length === 0 ? (
            <tr>
              <td colSpan={7} className="px-6 py-10 text-center text-[13px] text-text-muted">
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
                  <div className="font-semibold">{c.name}</div>
                  <div className="mt-0.5 font-mono text-[10px] text-text-muted">{c.customerId}</div>
                </Td>
                <Td align="right" mono>
                  ${c.revenue.toLocaleString()}
                </Td>
                <Td align="center">
                  <TypeBadge type={c.revenueType} />
                </Td>
                <Td align="right" mono>
                  ${c.apiCosts.toLocaleString()}
                </Td>
                <Td align="right" mono>
                  <span className={cn(c.margin < 0 && "text-red")}>
                    {c.margin < 0
                      ? `−$${Math.abs(c.margin).toLocaleString()}`
                      : `$${c.margin.toLocaleString()}`}
                  </span>
                </Td>
                <Td>
                  <MarginCell percentage={c.marginPercentage} />
                </Td>
                <Td align="right" mono className="text-text-muted">
                  {formatEventCount(c.events)}
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

function TypeBadge({ type }: { type: "Sub" | "Usage" }) {
  return (
    <span
      className={cn(
        "inline-block rounded-full px-2.5 py-[3px] text-[10px] font-semibold",
        type === "Sub"
          ? "bg-blue-light text-blue-text"
          : "bg-amber-light text-amber-text",
      )}
    >
      {type}
    </span>
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
