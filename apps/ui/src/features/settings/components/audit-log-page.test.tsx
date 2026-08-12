import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithQuery } from "../test-utils";
import { AuditLogPage } from "./audit-log-page";

describe("AuditLogPage", () => {
  it("renders records with humanized actions, actor badges, and load more", async () => {
    renderWithQuery(<AuditLogPage />);

    expect(await screen.findByText("Config updated")).toBeInTheDocument();
    expect(screen.getByText("API key rotated")).toBeInTheDocument();
    expect(screen.getAllByText("mia@acme.ai").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Team member").length).toBeGreaterThan(0);
    expect(screen.getAllByText("System").length).toBeGreaterThan(0);

    // 18 fixture records, mock page size 10 → more available.
    expect(screen.getByRole("button", { name: "Load more" })).toBeInTheDocument();
  });

  it("expands a row into a key-value metadata tree (not raw JSON)", async () => {
    renderWithQuery(<AuditLogPage />);
    await screen.findByText("Config updated");

    const toggles = screen.getAllByRole("button", { name: "Show details" });
    expect(toggles.length).toBeGreaterThan(0);
    fireEvent.click(toggles[0] as HTMLElement);

    // config.updated → changes → enforcement_mode → from/to.
    //
    // The keys render AS THE TENANT WROTE THEM (#279, ADR-0008 §4.4). They used
    // to arrive title-cased — "Changes", "Enforcement mode" — which is UBB
    // manufacturing user-facing English out of somebody else's identifier, and
    // it made two keys differing only in case or punctuation read as one word.
    expect(await screen.findByText("changes")).toBeInTheDocument();
    expect(screen.getByText("enforcement_mode")).toBeInTheDocument();
    expect(screen.getByText("enforcing")).toBeInTheDocument();

    // The old rendering must be gone rather than merely unasserted: the tree
    // walks nested objects through one node component, so a humaniser left on
    // either the leaf branch or the group branch would still title-case half of
    // what a reader sees while the assertions above passed.
    expect(screen.queryByText("Changes")).not.toBeInTheDocument();
    expect(screen.queryByText("Enforcement mode")).not.toBeInTheDocument();
  });

  it("honors deep-linked filters and offers to clear them when nothing matches", async () => {
    const onSearchChange = vi.fn();
    renderWithQuery(
      <AuditLogPage
        search={{ resource_type: "nonexistent_type" }}
        onSearchChange={onSearchChange}
      />,
    );

    expect(await screen.findByText("No matching records")).toBeInTheDocument();
    // "Clear filters" exists in both the filter strip and the empty state.
    const clearButtons = screen.getAllByRole("button", { name: "Clear filters" });
    fireEvent.click(clearButtons[clearButtons.length - 1] as HTMLElement);
    expect(onSearchChange).toHaveBeenCalledWith({});
  });

  it("filters by resource id from the URL (deep link from other pages)", async () => {
    renderWithQuery(
      <AuditLogPage
        search={{ resource_type: "rate_card", resource_id: "rc-openai-price-v4" }}
      />,
    );

    expect(await screen.findByText("Rate card published")).toBeInTheDocument();
    expect(screen.queryByText("Config updated")).not.toBeInTheDocument();
  });
});
