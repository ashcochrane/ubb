import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";

import { renderInRouter } from "../test-utils";
import { DevelopersPage } from "./developers-page";

describe("the Developers page", () => {
  // The API-basics card was a second, hand-written integration example; its
  // lesson is the Code Builder's onboarding state now (#579), and the page
  // points there instead of keeping a copy that could drift from the code.
  it("leads to the Code Builder, and keeps no API-basics card of its own", async () => {
    renderInRouter(
      <TooltipProvider>
        <DevelopersPage />
      </TooltipProvider>,
    );

    expect(await screen.findByRole("link", { name: "Open the Code Builder" })).toHaveAttribute(
      "href",
      "/developers/code-builder",
    );
    expect(screen.queryByText("API basics")).toBeNull();
    expect(screen.queryByText("Base URL")).toBeNull();
  });
});
