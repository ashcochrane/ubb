import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { Plus, Search } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { usePricingCards } from "../api/queries";
import { PricingCardItem } from "./pricing-card-item";
import { Skeleton } from "@/components/ui/skeleton";

export function PricingCardsPage() {
  const { data: cards, isLoading } = usePricingCards();
  const [search, setSearch] = useState("");

  const filtered = cards?.filter((c) =>
    c.name.toLowerCase().includes(search.toLowerCase()) ||
    c.provider.toLowerCase().includes(search.toLowerCase()) ||
    c.cardId.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="space-y-5">
      <PageHeader
        title="Pricing Cards"
        description="Define how API costs are calculated."
        actions={
          <Link
            to="/pricing-cards/new"
            className="flex items-center gap-1.5 rounded-md bg-foreground px-3.5 py-1.5 text-[12.5px] font-medium text-background hover:opacity-90"
          >
            <Plus className="h-3.5 w-3.5" /> Create card
          </Link>
        }
      />

      <div className="relative max-w-xs">
        <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search cards..."
          className="w-full rounded-lg border border-border bg-background py-1.5 pl-8 pr-3 text-[12.5px] outline-none focus:border-muted-foreground"
        />
      </div>

      {isLoading ? (
        <div className="grid grid-cols-3 gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-md" />
          ))}
        </div>
      ) : filtered && filtered.length > 0 ? (
        <div className="grid grid-cols-3 gap-3">
          {filtered.map((card) => (
            <PricingCardItem key={card.id} card={card} />
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-dashed p-12 text-center text-sm text-muted-foreground">
          {search ? "No cards match your search." : "No pricing cards yet. Create your first card."}
        </div>
      )}
    </div>
  );
}
