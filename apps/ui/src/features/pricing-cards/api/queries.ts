import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toastOnError } from "@/lib/mutations";
import { pricingCardsApi } from "./provider";
import type { CreateCardRequest } from "./types";
import type { DimensionIn, UpdateCardRequest } from "./api";

export function usePricingCards() {
  return useQuery({
    queryKey: ["pricing-cards"],
    queryFn: () => pricingCardsApi.getCards(),
  });
}

export function useTemplates() {
  return useQuery({
    queryKey: ["pricing-card-templates"],
    queryFn: () => pricingCardsApi.getTemplates(),
  });
}

export function useGroups() {
  return useQuery({
    queryKey: ["pricing-card-groups"],
    queryFn: () => pricingCardsApi.getGroups(),
  });
}

export function useCreateCard() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (req: CreateCardRequest) => pricingCardsApi.createCard(req),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pricing-cards"] });
    },
    onError: toastOnError("Couldn't create pricing card"),
  });
}

const CARD_KEY = (cardId: string) => ["pricing-card", cardId] as const;

export function usePricingCard(cardId: string) {
  return useQuery({
    queryKey: CARD_KEY(cardId),
    queryFn: () => pricingCardsApi.getCard(cardId),
    enabled: !!cardId,
  });
}

export function useUpdateCard(cardId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: UpdateCardRequest) =>
      pricingCardsApi.updateCard(cardId, req),
    onSuccess: (data) => {
      qc.setQueryData(CARD_KEY(cardId), data);
      qc.invalidateQueries({ queryKey: ["pricing-cards"] });
    },
    onError: toastOnError("Couldn't update pricing card"),
  });
}

export function useDeleteCard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cardId: string) => pricingCardsApi.deleteCard(cardId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pricing-cards"] }),
    onError: toastOnError("Couldn't delete pricing card"),
  });
}

export function useCreateRate(cardId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: DimensionIn) => pricingCardsApi.createRate(cardId, req),
    onSuccess: () => qc.invalidateQueries({ queryKey: CARD_KEY(cardId) }),
    onError: toastOnError("Couldn't add rate"),
  });
}

export function useUpdateRate(cardId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ rateId, body }: { rateId: string; body: DimensionIn }) =>
      pricingCardsApi.updateRate(cardId, rateId, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: CARD_KEY(cardId) }),
    onError: toastOnError("Couldn't update rate"),
  });
}

export function useDeleteRate(cardId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (rateId: string) =>
      pricingCardsApi.deleteRate(cardId, rateId),
    onSuccess: () => qc.invalidateQueries({ queryKey: CARD_KEY(cardId) }),
    onError: toastOnError("Couldn't delete rate"),
  });
}
