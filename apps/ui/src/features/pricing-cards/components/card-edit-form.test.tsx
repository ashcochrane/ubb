import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

const updateMutate = vi.fn();

vi.mock("../api/queries", () => ({
  useUpdateCard: () => ({ mutateAsync: updateMutate, isPending: false }),
  useGroups: () => ({ data: [], isLoading: false }),
}));

import { CardEditForm } from "./card-edit-form";

const card = {
  id: "card_1",
  slug: "openai-gpt-4o",
  provider: "openai",
  name: "OpenAI GPT-4o",
  description: "OpenAI pricing",
  pricingSourceUrl: "https://openai.com/pricing",
  groupId: null,
  groupName: null,
  status: "active" as const,
  dimensions: [],
  createdAt: "2026-05-01T00:00:00Z",
  updatedAt: "2026-05-01T00:00:00Z",
};

function renderForm() {
  const qc = new QueryClient();
  return render(
    React.createElement(QueryClientProvider, { client: qc },
      React.createElement(CardEditForm, { card }),
    ),
  );
}

describe("CardEditForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateMutate.mockResolvedValue(card);
  });

  it("renders the current card metadata", () => {
    renderForm();
    expect(screen.getByDisplayValue("OpenAI GPT-4o")).toBeInTheDocument();
    expect(screen.getByDisplayValue("OpenAI pricing")).toBeInTheDocument();
  });

  it("submits a metadata change", async () => {
    renderForm();
    const name = screen.getByLabelText(/^name$/i);
    fireEvent.change(name, { target: { value: "OpenAI GPT-4o (USD)" } });
    fireEvent.click(screen.getByRole("button", { name: /save card/i }));
    await waitFor(() => {
      expect(updateMutate).toHaveBeenCalledWith(
        expect.objectContaining({ name: "OpenAI GPT-4o (USD)" }),
      );
    });
  });
});
