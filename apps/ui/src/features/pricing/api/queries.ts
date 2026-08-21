// TanStack hooks over the pricing provider. ALL query keys and invalidation
// for this feature live here. First key segment = backend namespace
// ("metering" — pricing lives under /metering/pricing). Pricing changes feed
// future billed cost, which feeds margin, and every pricing mutation is
// audited, so mutations over-invalidate the "margin" and "audit" namespaces
// too (see usePricingInvalidation).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useCursorList } from "@/api/pagination";
import { pricingApi } from "./provider";
import type { CostBookIn, PricingBookIn } from "./types";

// ⚠ TWO KEYS, NOT ONE KEYED ON A KIND (#368). A Pricing Book and a cost book
// are separate entities on separate paths; one key carrying which kind it
// wanted would be the deleted column living on in the cache.
const pricingBooksKey = ["metering", "pricing", "pricing-books"] as const;
const costBooksKey = ["metering", "pricing", "cost-books"] as const;
const bookKey = (bookId: string) => ["metering", "pricing", "book", bookId] as const;
const ratesKey = (
  bookId: string,
  view: { include_history: boolean; as_of: string | null },
) => ["metering", "pricing", "books", bookId, "rates", view] as const;

export function usePricingBooks() {
  return useCursorList(pricingBooksKey, (cursor) =>
    pricingApi.listPricingBooks({ cursor }),
  );
}

export function useCostBooks() {
  return useCursorList(costBooksKey, (cursor) =>
    pricingApi.listCostBooks({ cursor }),
  );
}

export function useBook(bookId: string) {
  return useQuery({
    queryKey: bookKey(bookId),
    queryFn: () => pricingApi.getBook(bookId),
  });
}

export function useRates(
  bookId: string,
  view: { include_history?: boolean; as_of?: string },
  options?: { enabled?: boolean },
) {
  const normalized = {
    include_history: view.include_history ?? false,
    as_of: view.as_of ?? null,
  };
  return useCursorList(
    ratesKey(bookId, normalized),
    (cursor) =>
      pricingApi.listRates(bookId, {
        include_history: normalized.include_history,
        as_of: normalized.as_of ?? undefined,
        cursor,
      }),
    { enabled: options?.enabled },
  );
}

/**
 * Invalidate everything pricing touches. The whole "metering" namespace, not
 * just ["metering","pricing"]: other features cache off-prefix metering keys
 * that pricing mutations affect. "margin" derives from pricing; every one of
 * these mutations also writes an audit record (`pricing_book.declared`,
 * `cost_book.declared`), so the settings audit ledger ("audit" namespace) must
 * refetch too. Over-invalidate rather than miss.
 */
function usePricingInvalidation() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["metering"] });
    void queryClient.invalidateQueries({ queryKey: ["margin"] });
    void queryClient.invalidateQueries({ queryKey: ["audit"] });
  };
}

export function useDeclarePricingBook() {
  const invalidate = usePricingInvalidation();
  return useMutation({
    mutationFn: (body: PricingBookIn) => pricingApi.declarePricingBook(body),
    onSuccess: invalidate,
  });
}

export function useDeclareCostBook() {
  const invalidate = usePricingInvalidation();
  return useMutation({
    mutationFn: (body: CostBookIn) => pricingApi.declareCostBook(body),
    onSuccess: invalidate,
  });
}

// ⚠ NO `usePublishBook` (#368). The immediate reprice route it wrapped is
// deleted with the last of the retired audit action names it wrote. A book
// changes by a declared publish now — read as a diff first — and the feature
// that speaks that body arrives with #372.

