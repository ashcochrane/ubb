import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

const createRateMutate = vi.fn();
const updateRateMutate = vi.fn();

vi.mock("../api/queries", () => ({
  useCreateRate: () => ({ mutateAsync: createRateMutate, isPending: false }),
  useUpdateRate: () => ({ mutateAsync: updateRateMutate, isPending: false }),
}));

import { RateEditDialog } from "./rate-edit-dialog";

function renderDialog(props: Partial<React.ComponentProps<typeof RateEditDialog>> = {}) {
  const qc = new QueryClient();
  return render(
    React.createElement(QueryClientProvider, { client: qc },
      React.createElement(RateEditDialog, {
        cardId: "card_1",
        open: true,
        onOpenChange: vi.fn(),
        ...props,
      }),
    ),
  );
}

describe("RateEditDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    createRateMutate.mockResolvedValue(undefined);
    updateRateMutate.mockResolvedValue(undefined);
  });

  it("creates a new rate", async () => {
    renderDialog();
    fireEvent.change(screen.getByLabelText(/metric name/i), {
      target: { value: "input_tokens" },
    });
    fireEvent.change(screen.getByLabelText(/cost per unit/i), {
      target: { value: "500" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => {
      expect(createRateMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          metricName: "input_tokens",
          costPerUnitMicros: 500,
          unitQuantity: 1_000_000,
        }),
      );
    });
  });

  it("updates an existing rate", async () => {
    renderDialog({
      rate: {
        id: "rate_1",
        metricName: "input_tokens",
        label: "Input tokens",
        unit: "token",
        unitQuantity: 1_000_000,
        currency: "USD",
        pricingType: "per_unit",
        costPerUnitMicros: 500,
        providerCostPerUnitMicros: null,
      },
    });
    fireEvent.change(screen.getByLabelText(/cost per unit/i), {
      target: { value: "750" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => {
      expect(updateRateMutate).toHaveBeenCalledWith({
        rateId: "rate_1",
        body: expect.objectContaining({ costPerUnitMicros: 750 }),
      });
    });
  });
});
