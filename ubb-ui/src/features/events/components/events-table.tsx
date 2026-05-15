import { cn } from "@/lib/utils";
import { formatCostMicros } from "@/lib/format";
import type { EventFilterOptions, UsageEvent } from "../api/types";

interface EventsTableProps {
  events: UsageEvent[];
  filterOptions: EventFilterOptions;
  onUpdateEvent: (idx: number, field: "customerExternalId" | "group", value: string | null) => void;
}

export function EventsTable({ events, filterOptions, onUpdateEvent }: EventsTableProps) {
  return (
    <div className="overflow-hidden rounded-md border border-border bg-bg-surface">
      <div className="max-h-[380px] overflow-auto">
        <table className="w-full min-w-[820px] border-collapse text-[10px]">
          <thead>
            <tr>
              {["", "TIME", "CUSTOMER", "GROUP", "CARD", "METRICS", "COST", ""].map((h, i) => (
                <th key={i} className={cn(
                  "sticky top-0 z-[2] border-t border-b border-border bg-bg-subtle px-1.5 py-2.5 text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted",
                  i === 0 && "w-[22px]",
                  i === 1 && "w-[88px] text-left",
                  i === 2 && "w-[90px] text-left",
                  i === 3 && "w-[90px] text-left",
                  i === 4 && "w-[90px] text-left",
                  i === 5 && "text-left",
                  i === 6 && "w-[72px] text-right",
                  i === 7 && "w-[24px]",
                )}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {events.map((ev, i) => {
              const ts = formatTimestamp(ev.effectiveAt);
              const metricsStr = Object.entries(ev.usageMetrics)
                .map(([k, v]) => `${k}=${v.toLocaleString()}`)
                .join(", ");

              return (
                <tr key={ev.id} className="border-b border-bg-subtle last:border-0 transition-colors hover:bg-bg-page">
                  <td className="px-1.5 py-3.5" />
                  <td className="px-1.5 py-3.5 font-mono text-text-muted">{ts}</td>
                  <td className="px-1.5 py-3.5">
                    <EditableCell
                      value={ev.customerExternalId}
                      options={filterOptions.customers.map((c) => c.key)}
                      onChange={(v) => onUpdateEvent(i, "customerExternalId", v)}
                    />
                  </td>
                  <td className="px-1.5 py-3.5">
                    <EditableCell
                      value={ev.group ?? ""}
                      options={filterOptions.groups.map((g) => g.key)}
                      emptyLabel="none"
                      isMono
                      onChange={(v) => onUpdateEvent(i, "group", v || null)}
                    />
                  </td>
                  <td className="px-1.5 py-3.5 text-text-muted opacity-60">
                    {ev.cardName ?? ev.cardSlug ?? "—"}
                  </td>
                  <td className="px-1.5 py-3.5 font-mono text-text-secondary opacity-60">
                    {metricsStr || "—"}
                  </td>
                  <td className="px-1.5 py-3.5 text-right font-mono font-medium">
                    {ev.billedCostMicros != null ? formatCostMicros(ev.billedCostMicros) : "—"}
                  </td>
                  <td className="px-1.5 py-3.5" />
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EditableCell({
  value,
  options,
  emptyLabel,
  isMono,
  onChange,
}: {
  value: string;
  options: string[];
  emptyLabel?: string;
  isMono?: boolean;
  onChange: (v: string) => void;
}) {
  return (
    <span
      className="group relative cursor-pointer rounded-sm transition-colors hover:bg-accent-ghost"
      onClick={(e) => {
        const span = e.currentTarget;
        const select = document.createElement("select");
        select.className =
          "absolute inset-0 w-full rounded-sm border border-accent-border bg-bg-surface px-1 py-0.5 text-[10px] text-text-primary outline-none";
        const noneOpt = document.createElement("option");
        noneOpt.value = "";
        noneOpt.textContent = emptyLabel ? `(${emptyLabel})` : "Select...";
        select.appendChild(noneOpt);
        for (const opt of options) {
          const o = document.createElement("option");
          o.value = opt;
          o.textContent = opt;
          if (opt === value) o.selected = true;
          select.appendChild(o);
        }
        span.style.position = "relative";
        span.appendChild(select);
        select.focus();
        const cleanup = () => {
          onChange(select.value);
          select.remove();
        };
        select.addEventListener("blur", cleanup);
        select.addEventListener("change", cleanup);
      }}
    >
      {value ? (
        <span className={cn(isMono && "font-mono", !isMono && "font-semibold")}>
          {value}
        </span>
      ) : (
        <span className="italic text-amber-text">
          {emptyLabel ?? "none"}
        </span>
      )}
      <span className="absolute bottom-0.5 left-0 top-0.5 w-0.5 rounded-sm bg-accent-base opacity-0 transition-opacity group-hover:opacity-100" />
    </span>
  );
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  const day = d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  return `${day} ${time}`;
}
