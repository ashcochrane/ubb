import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toastOnError } from "@/lib/mutations";
import { pricingCardsApi } from "./provider";
import type { CreateCardRequest } from "./types";

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

export function useProducts() {
  return useQuery({
    queryKey: ["products"],
    queryFn: () => pricingCardsApi.getProducts(),
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
