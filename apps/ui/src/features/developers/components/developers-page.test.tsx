import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";

import { renderInRouter } from "../test-utils";
import { DevelopersPage } from "./developers-page";

function renderPage() {
  renderInRouter(
    <TooltipProvider>
      <DevelopersPage />
    </TooltipProvider>,
  );
}

describe("the Developers page", () => {
  // The API-basics card was a second, hand-written integration example; its
  // lesson is the Code Builder's onboarding state now (#579), and the page
  // points there instead of keeping a copy that could drift from the code.
  it("leads to the Code Builder, and keeps no API-basics card of its own", async () => {
    renderPage();

    expect(await screen.findByRole("link", { name: "Open the Code Builder" })).toHaveAttribute(
      "href",
      "/developers/code-builder",
    );
    expect(screen.queryByText("API basics")).toBeNull();
    expect(screen.queryByText("Base URL")).toBeNull();
  });

  // ⚠ THE TEST-EVENT FORM IS GONE (#581, #559). It posted a field the
  // recording request does not publish, and the server dropped it silently on
  // every send. Verify replaced it on the Code Builder page, posting only what
  // the contract publishes; this tab now offers no form of its own at all.
  it("no longer offers a form that sends a usage event", async () => {
    renderPage();
    await screen.findByRole("link", { name: "Open the Code Builder" });
    // Both sections that load their own data have answered — the keys and the
    // sandbox's — so an absence below is not a form still on its way.
    await screen.findAllByText(/ubb_live_/);
    await screen.findAllByText(/ubb_test_/);

    expect(screen.queryByText(/test event/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /send/i })).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("spinbutton")).toBeNull();
    expect(document.querySelectorAll("form")).toHaveLength(0);
  });
});
