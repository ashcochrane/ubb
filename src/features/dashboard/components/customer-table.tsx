import { cn } from "@/lib/utils";
import type { CustomerRow } from "../api/types";

interface CustomerTableProps {
  customers: CustomerRow[];
}

export function CustomerTable({ customers }: CustomerTableProps) {
  return (
    <div className="overflow-hidden rounded-xl border border-border">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="border-b border-border text-left">
            <th className="min-w-[120px] px-3 py-2 text-[11px] font-semibold text-muted-foreground">Customer</th>
            <th className="px-3 py-2 text-right text-[11px] font-semibold text-muted-foreground">Revenue</th>
            <th className="px-3 py-2 text-right text-[11px] font-semibold text-muted-foreground/50">Type</th>
            <th className="px-3 py-2 text-right text-[11px] font-semibold text-muted-foreground">API costs</th>
            <th className="px-3 py-2 text-right text-[11px] font-semibold text-muted-foreground">Margin</th>
            <th className="px-3 py-2 text-[11px] font-semibold text-muted-foreground">Margin %</th>
            <th className="px-3 py-2 text-right text-[11px] font-semibold text-muted-foreground">Events</th>
          </tr>
        </thead>
        <tbody>
          {customers.map((c) => (
            <tr key={c.customerId} className="border-b border-border/50 last:border-0 hover:bg-accent/30">
              <td className="px-3 py-2">
                <div className="font-semibold">{c.name}</div>
                <div className="font-mono text-[10px] text-muted-foreground">{c.customerId}</div>
              </td>
              <td className="px-3 py-2 text-right font-mono">${c.revenue.toLocaleString()}</td>
              <td className="px-3 py-2 text-right">
                <span
                  className={cn(
                    "inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold",
                    c.revenueType === "Sub"
                      ? "bg-[#EEEDFE] text-[#534AB7]"
                      : "bg-[#E1F5EE] text-[#0F6E56]",
                  )}
                >
                  {c.revenueType}
                </span>
              </td>
              <td className="px-3 py-2 text-right font-mono">${c.apiCosts.toLocaleString()}</td>
              <td
                className={cn(
                  "px-3 py-2 text-right font-mono",
                  c.margin < 0 && "text-[#A32D2D]",
                )}
              >
                {c.margin < 0 ? `-$${Math.abs(c.margin).toLocaleString()}` : `$${c.margin.toLocaleString()}`}
              </td>
              <td className="px-3 py-2">
                <div className="flex items-center gap-1.5">
                  <MarginBar percentage={c.marginPercentage} />
                  <span
                    className={cn(
                      "font-mono text-[11px]",
                      c.marginPercentage >= 70
                        ? "text-[#3B6D11]"
                        : c.marginPercentage >= 30
                          ? "text-[#854F0B]"
                          : "text-[#A32D2D]",
                    )}
                  >
                    {c.marginPercentage}%
                  </span>
                </div>
              </td>
              <td className="px-3 py-2 text-right text-muted-foreground">
                {formatEvents(c.events)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MarginBar({ percentage }: { percentage: number }) {
  const positive = Math.max(0, Math.min(100, percentage));
  const isNegative = percentage < 0;

  return (
    <div className="flex h-1.5 w-[52px] overflow-hidden rounded-full">
      {isNegative ? (
        <div className="h-full w-full rounded-full bg-[#F09595]" />
      ) : (
        <>
          <div className="h-full rounded-full bg-[#5DCAA5]" style={{ width: `${positive}%` }} />
          <div className="h-full flex-1 bg-muted" />
        </>
      )}
    </div>
  );
}

function formatEvents(count: number): string {
  if (count >= 1000) return `${(count / 1000).toFixed(1)}k`;
  return count.toLocaleString();
}
