// The unprofitable-customers alert says which revenue view its margins were
// taken over (#548; W5 owner ruling 15).
//
// The alerting record's margins include revenue a tenant supplied, which is a
// whole figure under `recorded` and a slice of a period under `recognised`.
// The server states which on the answer, and the mock answers `recognised` —
// so the answer here is re-stated under each value, and an alert that wrote
// either word itself (`recognised` is the tempting one) fails the other.
//
// ⚠ This file stubs the alerting CALL and never names its hook:
// `snapshot-severance.test.ts` holds the alert card to being the only surface
// in this feature that holds the alerting hook, and a test is a surface there.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { revenueBasisNote } from "@/lib/supplied-revenue";
import { REVENUE_BASIS_VALUES } from "@/lib/vocabulary";

import { MOCK_UNPROFITABLE } from "../api/mock-data";
import { dashboardApi } from "../api/provider";
import { UnprofitableAlert } from "./unprofitable-alert";

vi.mock("@tanstack/react-router", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-router")>();
  return {
    ...actual,
    Link: (props: { to?: string; children?: ReactNode; className?: string }) => (
      <a className={props.className} href={props.to ?? "#"}>
        {props.children}
      </a>
    ),
  };
});

describe("UnprofitableAlert", () => {
  it.each(REVENUE_BASIS_VALUES)("states the %s basis its answer names", async (basis) => {
    vi.spyOn(dashboardApi, "getUnprofitable").mockResolvedValueOnce({
      ...MOCK_UNPROFITABLE,
      basis,
    });

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={client}>
        <UnprofitableAlert currency="usd" />
      </QueryClientProvider>,
    );

    expect(
      await screen.findByText("2 customers are unprofitable this period"),
    ).toBeInTheDocument();
    const notes = container.querySelectorAll("[data-revenue-basis]");
    expect(notes).toHaveLength(1);
    expect(notes[0]).toHaveAttribute("data-revenue-basis", basis);
    expect(notes[0]).toHaveTextContent(revenueBasisNote(basis));
  });
});
