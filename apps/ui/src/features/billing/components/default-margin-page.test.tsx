import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

const updateMutate = vi.fn();

vi.mock("../api/queries", () => ({
  useDefaultMargin: () => ({ data: { defaultMarginPct: 20 }, isLoading: false }),
  useUpdateDefaultMargin: () => ({ mutateAsync: updateMutate, isPending: false }),
}));

import { DefaultMarginPage } from "./default-margin-page";

function renderPage() {
  const qc = new QueryClient();
  return render(
    React.createElement(QueryClientProvider, { client: qc },
      React.createElement(DefaultMarginPage),
    ),
  );
}

describe("DefaultMarginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateMutate.mockResolvedValue({ defaultMarginPct: 25 });
  });

  it("renders the current default margin", () => {
    renderPage();
    expect(screen.getByDisplayValue("20")).toBeInTheDocument();
  });

  it("submits a new margin value", async () => {
    renderPage();
    const input = screen.getByLabelText(/default margin/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "25" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => {
      expect(updateMutate).toHaveBeenCalledWith({ defaultMarginPct: 25 });
    });
  });
});
