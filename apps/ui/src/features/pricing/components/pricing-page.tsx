import { PageHeader } from "@/components/shared/page-header";
import { BooksTable } from "./books-table";
import { DefaultMarkupCard } from "./default-markup-card";
import { HowPricingResolves } from "./how-pricing-resolves";

/**
 * /pricing — the books this workspace prices from, the rung that answers when
 * none of them does, and a plain-language account of how the two fit together.
 *
 * ⚠ **THE MARKUP RUNG IS ON THIS PAGE AND NOT ON /plans (#369, #372).** It used
 * to be a column on a plan, and a plan is the wrong place for it: a markup is
 * the tenant's answer for events nothing else priced, not a property of one
 * package. It sits beside the books because that is the question a reader of
 * this page is asking — *what decides what my customers pay* — and the ladder
 * above it is the answer that names both halves.
 *
 * Navigation is injected by the route file so this page renders without router
 * context in tests.
 */
export function PricingPage({ onOpenBook }: { onOpenBook: (bookId: string) => void }) {
  return (
    <div className="space-y-4">
      <PageHeader
        title="Pricing"
        description="The books of rules that decide what your customers are billed — and what your suppliers charge you."
      />
      <HowPricingResolves />
      <DefaultMarkupCard />
      <BooksTable onOpenBook={onOpenBook} />
    </div>
  );
}
