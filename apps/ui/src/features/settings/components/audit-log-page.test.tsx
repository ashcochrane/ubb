import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UNRECOGNISED_MARK } from "@/components/shared/open-set-value";

import { settingsApi } from "../api/provider";
import type { AuditRecord } from "../api/types";
import { renderWithQuery } from "../test-utils";
import { AuditLogPage } from "./audit-log-page";

describe("AuditLogPage", () => {
  it("renders records in the catalogue's words, actor badges, and load more", async () => {
    renderWithQuery(<AuditLogPage />);

    expect(await screen.findByText("Tenant configuration changed")).toBeInTheDocument();
    expect(screen.getByText("API key rotated")).toBeInTheDocument();
    expect(screen.getAllByText("mia@acme.ai").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Team member").length).toBeGreaterThan(0);
    expect(screen.getAllByText("System").length).toBeGreaterThan(0);

    // 18 fixture records, mock page size 10 → more available.
    expect(screen.getByRole("button", { name: "Load more" })).toBeInTheDocument();
  });

  it("expands a row into a key-value metadata tree (not raw JSON)", async () => {
    renderWithQuery(<AuditLogPage />);
    await screen.findByText("Tenant configuration changed");

    const toggles = screen.getAllByRole("button", { name: "Show details" });
    expect(toggles.length).toBeGreaterThan(0);
    fireEvent.click(toggles[0] as HTMLElement);

    // tenant.config_changed → changes → enforcement_mode → from/to.
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
        search={{
          // The pair the pricing book page sends. It names WHICH KIND of book,
          // because a Pricing Book and a cost book are two records with two
          // sets of audit actions (#368, #372).
          resource_type: "pricing_book",
          resource_id: "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e03",
        }}
      />,
    );

    expect(await screen.findByText("Pricing Book declared")).toBeInTheDocument();
    expect(screen.queryByText("Tenant configuration changed")).not.toBeInTheDocument();
  });
});

// R10-W4: the action, the resource type and who acted are the catalogue's
// words, on a record assembled HERE rather than read from the mock, so the
// mock cannot narrow along with the page. Who acted is OPEN (ADR-004 §4): a
// kind the console has never met renders as its token, marked, never guessed.
describe("AuditLogPage — the catalogue's words", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("words the action and the resource type, and marks an unfamiliar actor kind", async () => {
    const record: AuditRecord = {
      id: "aud-x",
      created_at: "2026-10-27T09:00:00Z",
      action: "grouping_field.declared",
      actor_kind: "a_kind_from_next_year",
      actor_id: "who",
      actor_display: "someone",
      resource_type: "grouping_field_registry",
      resource_id: "tenant-1",
      correlation_id: "corr-x",
      metadata: {},
    };
    vi.spyOn(settingsApi, "listAuditRecords").mockResolvedValue({
      data: [record],
      has_more: false,
      next_cursor: null,
    });

    renderWithQuery(<AuditLogPage />);

    expect(await screen.findByText("Grouping Field declared")).toBeInTheDocument();
    expect(screen.getByText("Grouping Fields")).toBeInTheDocument();
    const actor = screen.getByText("a_kind_from_next_year").closest("[data-label]");
    expect(actor?.getAttribute("data-label")).toBe("unfamiliar");
    expect(within(actor as HTMLElement).getByText(UNRECOGNISED_MARK)).toBeInTheDocument();
    expect(screen.queryByText("A kind from next year")).not.toBeInTheDocument();
  });
});
