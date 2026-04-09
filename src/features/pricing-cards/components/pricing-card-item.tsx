import type { PricingCard } from "../api/types";
import { cn } from "@/lib/utils";

interface PricingCardItemProps {
  card: PricingCard;
}

export function PricingCardItem({ card }: PricingCardItemProps) {
  return (
    <div className="rounded-xl border border-border px-4 py-3 transition-colors hover:border-muted-foreground">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[13px] font-medium">{card.name}</div>
          <div className="text-[11px] text-muted-foreground">{card.provider}</div>
        </div>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-[10px] font-medium",
            card.status === "active"
              ? "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400"
              : "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400",
          )}
        >
          {card.status === "active" ? "Active" : "Draft"}
        </span>
      </div>
      <div className="mt-1.5 font-mono text-[10px] text-muted-foreground">{card.cardId}</div>
      <div className="mt-1 text-[10px] text-muted-foreground">
        {card.dimensions.length} dimension{card.dimensions.length !== 1 ? "s" : ""} · v{card.version}
      </div>
    </div>
  );
}
