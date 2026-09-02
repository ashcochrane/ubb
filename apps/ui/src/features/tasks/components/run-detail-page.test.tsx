import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  METERING_ONLY_BILLING_MODE,
  readMockTenantConfig,
  writeMockTenantConfig,
} from "@/hooks/use-tenant-config";

import {
  CONTAINED_UNDER_ACTIVE_RUN,
  MOCK_CONTAINED,
  RUN_ACTIVE_ID,
  RUN_DELIVERED_FIXED_ID,
  RUN_EXPIRED_ID,
  RUN_FAILED_ID,
  RUN_UNKNOWN_COST_ID,
} from "../api/mock-data";
import { CONTAINED_ROWS_SHOWN_INLINE } from "../lib/runs";
import { DRAWN_AS_FAILURE, renderWithProviders } from "../test-utils";
import { RunDetailPage } from "./run-detail-page";

async function opened(taskId: string) {
  renderWithProviders(<RunDetailPage taskId={taskId} />);
  await screen.findByRole("heading", { name: `Run ${taskId.slice(0, 8)}…` });
}

function region(name: string): HTMLElement {
  return screen.getByRole("region", { name });
}

/** The row of a detail list holding a label and the value beside it. */
function rowBeside(scope: HTMLElement, label: string): HTMLElement {
  const row = within(scope).getByText(label).parentElement;
  if (!row) throw new Error(`${label} has no row`);
  return row;
}

function readingBeside(scope: HTMLElement, label: string): HTMLElement {
  const found = rowBeside(scope, label).querySelector<HTMLElement>("[data-reading]");
  if (!found) throw new Error(`${label} holds no reading`);
  return found;
}

describe("RunDetailPage", () => {
  it("renders a run from its routed id: how it ended, what it cost and earned, and the work it contains", async () => {
    await opened(RUN_ACTIVE_ID);
    expect(within(region("How it ended")).getByText("Active")).toBeInTheDocument();

    const money = region("What it cost and earned");
    expect(within(rowBeside(money, "Events")).getByText("30")).toBeInTheDocument();
    const cost = readingBeside(money, "Supplier cost");
    expect(cost).toHaveAttribute("data-reading", "floor");
    expect(cost).toHaveTextContent("at least $1.24");
    expect(cost).toHaveTextContent(/1 event has a supplier cost UBB has not learned/);
    const price = readingBeside(money, "Customer price");
    expect(price).toHaveAttribute("data-reading", "not_applicable");
    expect(price).toHaveTextContent("Not applicable");
    expect(price).toHaveTextContent("Priced at the task");
    expect(price).toHaveTextContent(/sold at one agreed price/);
    expect(
      within(rowBeside(money, "Agreed price")).getByText("$5.00 — owed if the run delivers."),
    ).toBeInTheDocument();
    expect(within(rowBeside(money, "Ceiling")).getByText("$3.00")).toBeInTheDocument();

    const contained = region("Contained work");
    expect(contained.querySelectorAll("tbody tr[data-contained-row]")).toHaveLength(
      CONTAINED_ROWS_SHOWN_INLINE,
    );
    expect(
      within(contained).getByText(
        `${CONTAINED_UNDER_ACTIVE_RUN} pieces of contained work, ${CONTAINED_UNDER_ACTIVE_RUN - CONTAINED_ROWS_SHOWN_INLINE} not shown`,
      ),
    ).toBeInTheDocument();
    expect(
      within(contained).getByRole("button", { name: `Show all ${CONTAINED_UNDER_ACTIVE_RUN}` }),
    ).toBeInTheDocument();
  });

  it("renders an expired run as its own state and says it is not a failure", async () => {
    await opened(RUN_EXPIRED_ID);
    const ended = region("How it ended");
    const badge = ended.querySelector<HTMLElement>("[data-status]");
    if (!badge) throw new Error("the section holds no drawn state");
    expect(badge).toHaveAttribute("data-status", "expired");
    expect(badge).toHaveTextContent("Expired");
    expect(badge.className).not.toMatch(DRAWN_AS_FAILURE);
    expect(within(ended).getByText(/Not a failure/)).toBeInTheDocument();
    expect(within(ended).queryByText("Reason")).toBeNull();
  });

  it("says Unknown for a run whose totals nobody knows, and never a zero amount", async () => {
    await opened(RUN_UNKNOWN_COST_ID);
    const money = region("What it cost and earned");
    expect(readingBeside(money, "Supplier cost")).toHaveTextContent("Unknown");
    expect(readingBeside(money, "Supplier cost")).toHaveTextContent(/missing, not zero/);
    expect(readingBeside(money, "Customer price")).toHaveTextContent("Unknown");
    expect(money).not.toHaveTextContent("$0.00");
  });

  it("says a delivered fixed-price run's agreed price is owed", async () => {
    await opened(RUN_DELIVERED_FIXED_ID);
    const money = region("What it cost and earned");
    expect(
      within(rowBeside(money, "Agreed price")).getByText("$5.00 — owed: the run delivered."),
    ).toBeInTheDocument();
    expect(readingBeside(money, "Supplier cost")).toHaveTextContent("$2.87");
  });

  it("says why a failed run failed, in the catalogue's words, and that its price is not owed", async () => {
    await opened(RUN_FAILED_ID);
    const ended = region("How it ended");
    expect(
      within(rowBeside(ended, "Reason")).getByText("Upstream provider failed"),
    ).toBeInTheDocument();
    const money = region("What it cost and earned");
    expect(
      within(rowBeside(money, "Agreed price")).getByText(
        "$5.00 — not owed: the run did not deliver.",
      ),
    ).toBeInTheDocument();
  });

  // ⚠ THE CASE REVIEW FOUND: a piece of contained work carries no pinned price
  // of its own, so read off its own row the regime is "priced per event" and
  // revenue that does not apply renders as `$0.00`. The page must ask the run
  // containing it. Reading `soldAtOnePrice(detail)` instead of the parent's
  // turns the reading below into `figure` and this red.
  it("reads a piece of contained work's regime off the run containing it, and names that run", async () => {
    const piece = MOCK_CONTAINED[RUN_ACTIVE_ID]?.[0];
    if (!piece) throw new Error("the fixture holds no contained work");
    await opened(piece.task_id);
    expect(screen.getByRole("link", { name: `${RUN_ACTIVE_ID.slice(0, 8)}…` })).toHaveAttribute(
      "href",
      `/tasks/runs/${RUN_ACTIVE_ID}`,
    );
    const money = region("What it cost and earned");
    const price = readingBeside(money, "Customer price");
    expect(price).toHaveAttribute("data-reading", "not_applicable");
    expect(price).toHaveTextContent("Priced at the task");
    expect(money).not.toHaveTextContent("$0.00");
    // Its own cost is its own, and a real figure.
    expect(readingBeside(money, "Supplier cost")).toHaveAttribute("data-reading", "figure");
    expect(
      within(region("Contained work")).getByText(/Nothing is contained in this run/),
    ).toBeInTheDocument();
  });

  it("does not say owed to a workspace that meters without billing", async () => {
    const original = readMockTenantConfig();
    try {
      writeMockTenantConfig({ ...original, billing_mode: METERING_ONLY_BILLING_MODE });
      await opened(RUN_ACTIVE_ID);
      const money = region("What it cost and earned");
      const price = readingBeside(money, "Customer price");
      expect(price).toHaveAttribute("data-reading", "not_applicable");
      expect(price).toHaveTextContent("Metering only");
      const agreed = rowBeside(money, "Agreed price").textContent ?? "";
      expect(agreed).toMatch(/\$5\.00/);
      expect(agreed).not.toMatch(/owed/);
    } finally {
      writeMockTenantConfig(original);
    }
  });

  it("says so for an id nobody has", async () => {
    renderWithProviders(<RunDetailPage taskId="00000000-0000-4000-8000-00000000dead" />);
    expect(await screen.findByText("No run with that id")).toBeInTheDocument();
  });
});
