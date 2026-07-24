// TanStack hooks over the pricing provider. ALL query keys and invalidation
// for this feature live here. First key segment = backend namespace
// ("metering" — pricing lives under /metering/pricing). Pricing changes feed
// future billed cost, which feeds margin, so mutations over-invalidate the
// "margin" namespace too.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useCursorList } from "@/api/pagination";
import { pricingApi } from "./provider";
import type { BookIn, PublishIn, RateIn, TenantMarkupIn } from "./types";

const booksKey = (cardType: string | undefined) =>
  ["metering", "pricing", "rate-cards", { card_type: cardType ?? null }] as const;
const bookKey = (bookId: string) => ["metering", "pricing", "book", bookId] as const;
const ratesKey = (
  bookId: string,
  view: { include_history: boolean; as_of: string | null },
) => ["metering", "pricing", "rate-cards", bookId, "rates", view] as const;
const markupKey = ["metering", "pricing", "markup"] as const;

export function useBooks(cardType?: string) {
  return useCursorList(booksKey(cardType), (cursor) =>
    pricingApi.listBooks({ card_type: cardType, cursor }),
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

export function useTenantMarkup() {
  return useQuery({
    queryKey: markupKey,
    queryFn: () => pricingApi.getTenantMarkup(),
  });
}

/** Invalidate everything pricing touches (and margin, which derives from it). */
function usePricingInvalidation() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["metering", "pricing"] });
    void queryClient.invalidateQueries({ queryKey: ["margin"] });
  };
}

export function useCreateBook() {
  const invalidate = usePricingInvalidation();
  return useMutation({
    mutationFn: (body: BookIn) => pricingApi.createBook(body),
    onSuccess: invalidate,
  });
}

export function useAddRate(bookId: string) {
  const invalidate = usePricingInvalidation();
  return useMutation({
    mutationFn: (body: RateIn) => pricingApi.addRate(bookId, body),
    onSuccess: invalidate,
  });
}

export function useRetireRate(bookId: string) {
  const invalidate = usePricingInvalidation();
  return useMutation({
    mutationFn: (rateId: string) => pricingApi.deleteRate(bookId, rateId),
    onSuccess: invalidate,
  });
}

export function usePublishBook(bookId: string) {
  const invalidate = usePricingInvalidation();
  return useMutation({
    mutationFn: (body: PublishIn) => pricingApi.publishBook(bookId, body),
    onSuccess: invalidate,
  });
}

export function useUpdateTenantMarkup() {
  const invalidate = usePricingInvalidation();
  return useMutation({
    mutationFn: (body: TenantMarkupIn) => pricingApi.putTenantMarkup(body),
    onSuccess: invalidate,
  });
}
