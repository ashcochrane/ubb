import { cn } from "@/lib/utils";

export interface ChartLegendItem {
  label: string;
  color: string;
  dashed?: boolean;
}

export interface ChartLegendProps {
  items: ChartLegendItem[];
  variant: "dot" | "line";
  className?: string;
}

export function ChartLegend({ items, variant, className }: ChartLegendProps) {
  return (
    <div className={cn("flex flex-wrap items-center gap-3.5", className)}>
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-1.5 text-[11px] text-text-muted">
          <Swatch color={item.color} dashed={item.dashed} variant={variant} />
          {item.label}
        </div>
      ))}
    </div>
  );
}

function Swatch({
  color,
  dashed,
  variant,
}: {
  color: string;
  dashed?: boolean;
  variant: "dot" | "line";
}) {
  if (variant === "dot") {
    return (
      <span
        className="block h-[7px] w-[7px] shrink-0 rounded-full"
        style={{ backgroundColor: color }}
      />
    );
  }
  return (
    <span
      className="block h-[2px] w-4 shrink-0 rounded-[1px]"
      style={{
        backgroundColor: dashed ? "transparent" : color,
        borderTop: dashed ? `1.5px dashed ${color}` : undefined,
      }}
    />
  );
}
