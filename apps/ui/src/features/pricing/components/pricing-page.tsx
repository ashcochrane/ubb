import { PageHeader } from "@/components/shared/page-header";
import { BooksTable } from "./books-table";
import { HowPricingResolves } from "./how-pricing-resolves";
import { TenantMarkupCard } from "./tenant-markup-card";

/**
 * /pricing — rate-card books, the tenant default markup, and a plain-language
 * explainer of how an event's billed price is resolved. Navigation is injected
 * by the route file so this page renders without router context in tests.
 */
export function PricingPage({ onOpenBook }: { onOpenBook: (bookId: string) => void }) {
  return (
    <div className="space-y-4">
      <PageHeader
        title="Pricing"
        description="Rate-card books and the default markup that decide what usage costs — and what customers are billed."
      />
      <HowPricingResolves />
      <TenantMarkupCard />
      <BooksTable onOpenBook={onOpenBook} />
    </div>
  );
}
