// TanStack hooks over the pricing provider. ALL query keys and invalidation
// for this feature live here. First key segment = backend namespace
// ("metering" — pricing lives under /metering/pricing). Pricing changes feed
// future billed cost, which feeds margin, and every pricing mutation is
// audited, so mutations over-invalidate the "margin" and "audit" namespaces
// too (see usePricingInvalidation).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useCursorList } from "@/api/pagination";
import { pricingApi } from "./provider";
import type {
  BookPublishIn,
  CostBookIn,
  CustomerOverrideIn,
  InheritedRuleParams,
  PricingBookIn,
  TenantDefaultMarkupIn,
} from "./types";

// ⚠ TWO KEYS, NOT ONE KEYED ON A KIND (#368). A Pricing Book and a cost book
// are separate entities on separate paths; one key carrying which kind it
// wanted would be the deleted column living on in the cache.
const pricingBooksKey = ["metering", "pricing", "pricing-books"] as const;
const costBooksKey = ["metering", "pricing", "cost-books"] as const;
const bookKey = (bookId: string) => ["metering", "pricing", "book", bookId] as const;
const rulesKey = (
  bookId: string,
  view: { include_history: boolean; as_of: string | null },
) => ["metering", "pricing", "books", bookId, "rules", view] as const;
const publishesKey = (bookId: string) =>
  ["metering", "pricing", "books", bookId, "publishes"] as const;
const markupKey = ["metering", "pricing", "default-markup"] as const;
// ⚠ A TAIL, BECAUSE THIS CACHES A PROJECTION AND NOT THE RAW RESPONSE. The
// route answers an envelope and `listGroupingFields` unwraps it to the list;
// the console's rule is that shared keys cache the RAW response and a
// projection adds a tail, so a second feature that comes to want the envelope
// can hold it under the bare key without the two colliding on one cached shape.
const groupingFieldsKey = ["metering", "grouping-fields", "declared"] as const;
const inheritedRuleKey = (customerId: string, params: InheritedRuleParams) =>
  ["metering", "pricing", "customers", customerId, "inherited-rule", params] as const;

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

export function useRules(
  bookId: string,
  view: { include_history?: boolean; as_of?: string },
  options?: { enabled?: boolean },
) {
  const normalized = {
    include_history: view.include_history ?? false,
    as_of: view.as_of ?? null,
  };
  return useCursorList(
    rulesKey(bookId, normalized),
    (cursor) =>
      pricingApi.listRules(bookId, {
        include_history: normalized.include_history,
        as_of: normalized.as_of ?? undefined,
        cursor,
      }),
    { enabled: options?.enabled },
  );
}

/**
 * The changes pending on a book — the drafts, each with its diff.
 *
 * ⚠ **A SERIES, NOT A PENDING ITEM.** There is no limit on how many changes a
 * book may have scheduled at once, and the screen that renders them says so by
 * rendering a list; a hook that took the first row would turn a schedule into a
 * single next-change and lose the very thing a tenant dating changes forward is
 * trying to see.
 */
export function useBookPublishes(bookId: string) {
  return useCursorList(publishesKey(bookId), (cursor) =>
    pricingApi.listBookPublishes(bookId, { cursor }),
  );
}

/**
 * Invalidate everything pricing touches. The whole "metering" namespace, not
 * just ["metering","pricing"]: other features cache off-prefix metering keys
 * that pricing mutations affect. "margin" derives from pricing; every one of
 * these mutations also writes an audit record (`pricing_book.declared`,
 * `pricing_book_publish.published`, `tenant_default_markup.declared`), so the
 * settings audit ledger ("audit" namespace) must refetch too. Over-invalidate
 * rather than miss.
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

// --- Publishes --------------------------------------------------------------

/**
 * Declare a change to a book as a draft.
 *
 * ⚠ **IT INVALIDATES, EVEN THOUGH IT WRITES NO RULE.** What moved is the list
 * of drafts pending on the book, which is a thing on the screen; and the
 * declaration itself is an audited act, so the ledger moved too. A mutation
 * that "changed nothing" and skipped invalidation would leave a tenant looking
 * at a book with no sign of the change they just made.
 */
export function useDeclareBookPublish(bookId: string) {
  const invalidate = usePricingInvalidation();
  return useMutation({
    mutationFn: (body: BookPublishIn) =>
      pricingApi.declareBookPublish(bookId, body),
    onSuccess: invalidate,
  });
}

export function usePublishBookPublish(bookId: string) {
  const invalidate = usePricingInvalidation();
  return useMutation({
    mutationFn: (publishId: string) =>
      pricingApi.publishBookPublish(bookId, publishId),
    onSuccess: invalidate,
  });
}

export function useDiscardBookPublish(bookId: string) {
  const invalidate = usePricingInvalidation();
  return useMutation({
    mutationFn: (publishId: string) =>
      pricingApi.discardBookPublish(bookId, publishId),
    onSuccess: invalidate,
  });
}

// --- One customer's own rules -----------------------------------------------

/**
 * What this customer inherits for one rule — the starting point for an
 * override.
 *
 * `enabled` is how the editor asks only once it has a quantity to ask about:
 * `measurement_key` is required on the route, so a query fired from an empty
 * form would be a 422 the tenant never asked for.
 */
export function useInheritedRule(customerId: string, params: InheritedRuleParams) {
  return useQuery({
    queryKey: inheritedRuleKey(customerId, params),
    queryFn: () => pricingApi.getInheritedRule(customerId, params),
    // ⚠ `measurement_key` IS REQUIRED ON THE ROUTE, so a query fired from an
    // empty form is a 422 the tenant never asked for. One guard, stated where
    // the reason for it is — rather than a caller-facing `enabled` beside it
    // that every call site would have to remember to pass.
    enabled: params.measurement_key !== "",
  });
}

export function useDeclareCustomerOverride(customerId: string) {
  const invalidate = usePricingInvalidation();
  return useMutation({
    mutationFn: (body: CustomerOverrideIn) =>
      pricingApi.declareCustomerOverride(customerId, body),
    onSuccess: invalidate,
  });
}

// ⚠ NO `useWithdrawCustomerOverride`, AND THE ACT IS STILL REACHABLE. Ending a
// customer's own deal declares a draft that RETIRES the rule — which is exactly
// what the book's own page already does, because a customer's own book is a
// Pricing Book like any other and appears in the books list with the rest. A
// dedicated hook here would be a second console path to one act, and the two
// would then have to agree forever about what withdrawing means. The API
// function beside it went for the same reason: a wrapper with no caller is a
// dead export the next reader has to classify.

// --- The markup rung --------------------------------------------------------

export function useTenantDefaultMarkup() {
  return useQuery({
    queryKey: markupKey,
    queryFn: () => pricingApi.getTenantDefaultMarkup(),
  });
}

export function useDeclareTenantDefaultMarkup() {
  const invalidate = usePricingInvalidation();
  return useMutation({
    mutationFn: (body: TenantDefaultMarkupIn) =>
      pricingApi.declareTenantDefaultMarkup(body),
    onSuccess: invalidate,
  });
}

export function useWithdrawTenantDefaultMarkup() {
  const invalidate = usePricingInvalidation();
  return useMutation({
    mutationFn: () => pricingApi.withdrawTenantDefaultMarkup(),
    onSuccess: invalidate,
  });
}

// --- The tenant's declared grouping vocabulary ------------------------------

/** The slots a rule may be pinned on — however many this tenant declared. */
export function useGroupingFields() {
  return useQuery({
    queryKey: groupingFieldsKey,
    queryFn: () => pricingApi.listGroupingFields(),
  });
}
