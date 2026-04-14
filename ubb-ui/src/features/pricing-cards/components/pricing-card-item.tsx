import { Link } from "@tanstack/react-router";
import type { PricingCard } from "../api/types";
import { cn } from "@/lib/utils";

interface PricingCardItemProps {
  card: PricingCard;
}

export function PricingCardItem({ card }: PricingCardItemProps) {
  return (
    <Link to="/pricing-cards/$cardId" params={{ cardId: card.id }} className="block rounded-md border border-border bg-bg-surface px-4 py-3 transition-colors hover:border-border-mid hover:shadow-md">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[13px] font-medium">{card.name}</div>
          <div className="text-label text-muted-foreground">{card.provider}</div>
        </div>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-muted font-medium",
            card.status === "active"
              ? "bg-green-light text-green-text"
              : "bg-amber-light text-amber-text",
          )}
        >
          {card.status === "active" ? "Active" : "Draft"}
        </span>
      </div>
      <div className="mt-1.5 font-mono text-muted text-muted-foreground">{card.cardId}</div>
      <div className="mt-1 text-muted text-muted-foreground">
        {card.dimensions.length} dimension{card.dimensions.length !== 1 ? "s" : ""} · v{card.version}
      </div>
    </Link>
  );
}
