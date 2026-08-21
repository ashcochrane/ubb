import { PageHeader } from "@/components/shared/page-header";
import { BooksTable } from "./books-table";
import { HowPricingResolves } from "./how-pricing-resolves";

/**
 * /pricing — pricing books and a plain-language explainer of how an event's
 * billed price is resolved. There is no markup editor on this page and none on
 * /plans either: the plan's own markup columns are deleted (#369), and the
 * tenant's declared default markup rung has no console surface until #372
 * rebuilds this feature around books, rules and publishes.
 * Navigation is injected by the route file so this page renders without
 * router context in tests.
 */
export function PricingPage({ onOpenBook }: { onOpenBook: (bookId: string) => void }) {
  return (
    <div className="space-y-4">
      <PageHeader
        title="Pricing"
        description="Rate-card books that decide what usage costs — and what customers are billed."
      />
      <HowPricingResolves />
      <BooksTable onOpenBook={onOpenBook} />
    </div>
  );
}
