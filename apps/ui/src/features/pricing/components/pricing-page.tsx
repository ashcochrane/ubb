import { PageHeader } from "@/components/shared/page-header";
import { BooksTable } from "./books-table";
import { HowPricingResolves } from "./how-pricing-resolves";

/**
 * /pricing — rate-card books and a plain-language explainer of how an
 * event's billed price is resolved. Editing the tenant's default markup
 * moved off this page as part of consolidating a plan's commercial axes
 * (access fee, per-seat fee, markup) onto one /plans page.
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
