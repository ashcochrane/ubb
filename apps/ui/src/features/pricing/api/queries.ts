import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { toastOnError } from "@/lib/mutations";
import { useCursorList } from "@/lib/use-cursor-list";
import * as api from "./api";
import type {
  BookInput,
  RateInput,
  PublishInput,
  TenantMarkupInput,
} from "./types";

const BOOKS_KEY = ["pricing", "books"] as const;
const ratesKey = (id: string) => ["pricing", "rates", id] as const;
const MARKUP_KEY = ["pricing", "markup"] as const;

export function useBooks(cardType?: string) {
  return useCursorList({
    queryKeyBase: [...BOOKS_KEY, "list", cardType ?? "__all__"],
    fetchPage: (cursor) =>
      api.listBooks({ card_type: cardType || undefined, cursor, limit: 50 }),
  });
}

/**
 * Look up a single rate card. There is no single-GET route, so we read the
 * first page (up to 100) and find it — sufficient for realistic card counts;
 * returns null if it lives beyond the first page.
 */
export function useBook(bookId: string) {
  return useQuery({
    queryKey: [...BOOKS_KEY, "one", bookId],
    queryFn: async () => {
      const page = await api.listBooks({ limit: 100 });
      return page.data.find((b) => b.id === bookId) ?? null;
    },
    enabled: !!bookId,
  });
}

export function useRates(
  bookId: string,
  opts: { includeHistory: boolean; asOf?: string },
) {
  return useCursorList({
    queryKeyBase: [
      ...ratesKey(bookId),
      opts.includeHistory ? "history" : "current",
      opts.asOf ?? "__now__",
    ],
    fetchPage: (cursor) =>
      api.listRates(bookId, {
        include_history: opts.includeHistory,
        as_of: opts.asOf || undefined,
        cursor,
        limit: 50,
      }),
    enabled: !!bookId,
  });
}

export function useCreateBook() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: BookInput) => api.createBook(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: BOOKS_KEY });
      toast.success("Rate card created");
    },
    onError: toastOnError("Couldn't create rate card"),
  });
}

export function useAddRate(bookId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RateInput) => api.addRate(bookId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ratesKey(bookId) });
      toast.success("Rate added");
    },
    onError: toastOnError("Couldn't add rate"),
  });
}

export function useDeleteRate(bookId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (rateId: string) => api.deleteRate(bookId, rateId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ratesKey(bookId) });
      toast.success("Rate deleted");
    },
    onError: toastOnError("Couldn't delete rate"),
  });
}

export function usePublishBook(bookId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PublishInput) => api.publishBook(bookId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ratesKey(bookId) });
      qc.invalidateQueries({ queryKey: BOOKS_KEY });
      toast.success("Published a new rate-card version");
    },
    onError: toastOnError("Couldn't publish changes"),
  });
}

export function useMarkup() {
  return useQuery({
    queryKey: MARKUP_KEY,
    queryFn: () => api.getMarkup(),
  });
}

export function useUpdateMarkup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TenantMarkupInput) => api.putMarkup(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: MARKUP_KEY });
      toast.success("Markup saved");
    },
    onError: toastOnError("Couldn't save markup"),
  });
}
