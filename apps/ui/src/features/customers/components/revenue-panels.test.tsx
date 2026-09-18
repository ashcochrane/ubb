// The customer's revenue panels (#508; slice 7 §5, §9; Testing Decisions
// claims 10 and 11).
//
// WHAT THIS FILE IS FOR, in one sentence each:
//
//   * **Both postures are first class.** A tenant that supplies a figure gets
//     margin at the supplied scope; a tenant that supplies nothing gets revenue
//     UNKNOWN and margin unavailable — never a zero, and never a nudge toward
//     supplying. #153 §3.2 rules both legitimate and nothing else in this
//     console checks the second one.
//   * **Nothing silently distributes.** Every rendering of a supplied amount
//     carries its source reference and its recognition method, and says which
//     of the two views it is stated under.
//   * **The mid-period case is enterable.** The fourteenth of the month, by
//     name, without the tenant working out that it is seventeen days.
//   * **The write is at the ADMIN floor**, mirroring the route's.
//
// THE FIXTURES ARE THE FEATURE'S OWN MOCK, deliberately: the attribution rule
// is the mock's to apply, and a test that hand-built an answer would be
// checking the renderer against numbers it chose itself. What each test DOES
// assemble is the posture — which customer it asks about — because that is the
// thing under test.

import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CUS_LUNA, CUS_NOVA } from "../api/mock-data";
import { renderWithProviders } from "../test-utils";
import {
  MARGIN_UNAVAILABLE_NOT_ZERO,
  REVENUE_UNKNOWN_HERE,
  RevenuePanels,
  STATE_REVENUE_TITLE,
  SUPPLIED_REVENUE_TITLE,
} from "./revenue-panels";

const provider = vi.hoisted(() => ({
  getSuppliedRevenue: vi.fn(),
  recordSuppliedRevenue: vi.fn(),
}));

vi.mock("../api/provider", async () => {
  const mock = await vi.importActual<typeof import("../api/mock")>("../api/mock");
  provider.getSuppliedRevenue.mockImplementation(mock.getSuppliedRevenue);
  provider.recordSuppliedRevenue.mockImplementation(mock.recordSuppliedRevenue);
  return {
    customersApi: {
      ...mock,
      getSuppliedRevenue: provider.getSuppliedRevenue,
      recordSuppliedRevenue: provider.recordSuppliedRevenue,
    },
  };
});

// The role is a UX affordance the server enforces regardless, and it resolves
// to admin in mock mode — so the read-scoped session has to be stated.
const role = vi.hoisted(() => ({ value: "admin" as string | null }));
vi.mock("@/hooks/use-current-role", async () => {
  const actual =
    await vi.importActual<typeof import("@/hooks/use-current-role")>(
      "@/hooks/use-current-role",
    );
  return {
    ...actual,
    useCurrentRole: () => ({ role: role.value, resolved: true }),
    useHasRole: (floor: "read" | "write" | "admin") =>
      role.value === null
        ? true
        : ["read", "write", "admin"].indexOf(role.value)
          >= ["read", "write", "admin"].indexOf(floor),
  };
});

/** The window luna's fixture rows were written against. */
const JULY = { start_date: "2026-07-01", end_date: "2026-07-24" };

/**
 * The read panel, once the router has mounted.
 *
 * ⚠ **ASYNC BECAUSE THE FIRST QUERY OF EVERY TEST HAS TO BE**: these components
 * mount inside a real memory router, which resolves its route before anything
 * renders, so a synchronous `getBy` on a freshly rendered tree finds an empty
 * body rather than a missing panel.
 */
function supplied() {
  return screen.findByRole("region", { name: SUPPLIED_REVENUE_TITLE });
}

/** One of the write form's fields, once the router has mounted. */
function field(label: string | RegExp) {
  return screen.findByLabelText(label);
}

beforeEach(() => {
  role.value = "admin";
  provider.getSuppliedRevenue.mockClear();
  provider.recordSuppliedRevenue.mockClear();
});

describe("a tenant that supplies revenue", () => {
  it("shows every amount with its source reference and recognition method", async () => {
    renderWithProviders(<RevenuePanels customerId={CUS_LUNA} range={JULY} />);

    const panel = await supplied();
    // The July invoice — the row a straight-line method is stated on.
    const july = await within(panel).findByText("INV-2026-07");
    const row = july.closest("li");
    expect(row).not.toBeNull();
    // ITS METHOD IS ON THE ROW, not in a tooltip and not implied by the shape
    // of the figure: two records in one answer may be spread differently. The
    // reference and the method are one sentence made of several nodes, so the
    // assertion is on the row's text — which is what a reader sees.
    expect(row).toHaveTextContent("INV-2026-07");
    expect(row).toHaveTextContent("Straight line");

    // And the up-front fee is a DIFFERENT method on the same screen, which is
    // what makes the per-row rendering load-bearing rather than decorative.
    const fee = within(panel).getByText("SETUP-FEE-114").closest("li");
    expect(fee).toHaveTextContent("On receipt");
  });

  it("labels the figures with the basis they are stated under, and asks for that basis", async () => {
    renderWithProviders(<RevenuePanels customerId={CUS_LUNA} range={JULY} />);
    const panel = await supplied();
    await within(panel).findByText("INV-2026-07");

    // Recorded is the view that distributes nothing, and the panel opens on it.
    expect(within(panel).getAllByText(/recorded/i).length).toBeGreaterThan(0);
    expect(provider.getSuppliedRevenue).toHaveBeenCalledWith(
      CUS_LUNA,
      expect.anything(),
      "recorded",
    );

    fireEvent.click(screen.getByRole("button", { name: "Recognised" }));

    await waitFor(() => {
      expect(provider.getSuppliedRevenue).toHaveBeenCalledWith(
        CUS_LUNA,
        expect.anything(),
        "recognised",
      );
    });
  });

  // ⚠ THE DIVISION IS SHOWN, NEVER INFERRED. Under `recognised` the July
  // invoice contributes 23 of its 31 days to this window, so the figure on
  // screen is smaller than the one the tenant supplied — and a reader who
  // could not see that would take the smaller number for what was earned.
  it("says a figure was spread rather than showing a smaller number", async () => {
    renderWithProviders(<RevenuePanels customerId={CUS_LUNA} range={JULY} />);
    const panel = await supplied();
    await within(panel).findByText("INV-2026-07");
    fireEvent.click(screen.getByRole("button", { name: "Recognised" }));

    await waitFor(() => {
      const spread = within(panel).getByText("INV-2026-07").closest("li");
      expect(spread?.getAttribute("data-distributed")).toBe("yes");
    });
    const row = within(panel).getByText("INV-2026-07").closest("li");
    // 900.00 supplied, 23/31 of it attributed here — BOTH figures on the row,
    // so the smaller one cannot be read as what the tenant stated.
    expect(row).toHaveTextContent("spread across its period");
    expect(row).toHaveTextContent("$900.00");
    expect(row).toHaveTextContent("$667.74");

    // The up-front fee is NOT spread under the same basis, because its own
    // method says so — so the mark is per record and not per view.
    const fee = within(panel).getByText("SETUP-FEE-114").closest("li");
    expect(fee?.getAttribute("data-distributed")).toBe("no");
  });
});

describe("a cost-tracking-only tenant", () => {
  // ⚠ THE ANSWER IS AN ABSENCE AND IT MUST NOT BE A ZERO. `$0.00` here would
  // be a claim that this customer earned nothing, which is a different fact
  // from UBB not knowing what they earned — and it is the claim the deleted
  // switch used to make.
  it("is told revenue is unknown and margin unavailable, never zero", async () => {
    renderWithProviders(<RevenuePanels customerId={CUS_NOVA} range={JULY} />);

    const panel = await supplied();
    expect(await within(panel).findByText(REVENUE_UNKNOWN_HERE)).toBeInTheDocument();
    expect(within(panel).getByText(MARGIN_UNAVAILABLE_NOT_ZERO)).toBeInTheDocument();
    expect(within(panel).queryByText("$0.00")).not.toBeInTheDocument();
    expect(within(panel).queryByText("0")).not.toBeInTheDocument();
  });

  // Supplying is a CAPABILITY, not an obligation. The form is there for a
  // tenant who wants it and the panel says nothing urging them into it.
  it("is not pushed toward supplying a figure", async () => {
    renderWithProviders(<RevenuePanels customerId={CUS_NOVA} range={JULY} />);
    const panel = await supplied();
    await within(panel).findByText(REVENUE_UNKNOWN_HERE);

    // No call to action inside the answer — the write surface is its own
    // section beside it, reached because the tenant went looking.
    expect(within(panel).queryByRole("button", { name: /record revenue/i })).toBeNull();
    expect(
      screen.getByRole("region", { name: STATE_REVENUE_TITLE }),
    ).toBeInTheDocument();
  });
});

describe("stating a figure", () => {
  // THE CASE THE AFFORDANCE EXISTS FOR, BY NAME (#153 §19(f)). A customer that
  // began on the fourteenth is entered as the fourteenth; the SPAN is derived,
  // and the seventeen days are never asked for.
  it("takes a mid-period start as a partial period without the tenant computing it", async () => {
    renderWithProviders(<RevenuePanels customerId={CUS_LUNA} range={JULY} />);

    fireEvent.change(await field("Month this covers"), { target: { value: "2026-06" } });
    fireEvent.change(
      await field("Day it started, if part-way through the month"),
      { target: { value: "2026-06-14" } },
    );

    // The derived span is on screen before anything is saved, so the tenant
    // can see what they are about to state.
    const derived = await screen.findByText(/Part period/);
    expect(derived).toHaveTextContent("17 days");
    expect(derived.getAttribute("data-derived-period")).toBe("partial");

    fireEvent.change(await field(/^Amount/), { target: { value: "510" } });
    fireEvent.change(await field("Where it came from"), {
      target: { value: "INV-2026-06-part" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Record revenue" }));

    await waitFor(() => {
      expect(provider.recordSuppliedRevenue).toHaveBeenCalledWith(
        CUS_LUNA,
        expect.objectContaining({
          amount_micros: 510_000_000,
          period_start: "2026-06-14",
          // EXCLUSIVE, and the first of the NEXT month — the part period runs
          // to the end of the month it started in.
          period_end: "2026-07-01",
          source_reference: "INV-2026-06-part",
        }),
      );
    });
  });

  it("treats a month with no start day as the whole month", async () => {
    renderWithProviders(<RevenuePanels customerId={CUS_LUNA} range={JULY} />);
    fireEvent.change(await field("Month this covers"), { target: { value: "2026-06" } });
    const derived = await screen.findByText(/Whole month/);
    expect(derived).toHaveTextContent("30 days");
    expect(derived.getAttribute("data-derived-period")).toBe("whole");
  });

  // ⚠ A ZERO IS A STATEMENT AND THE FORM HAS TO ACCEPT ONE. A free month
  // earned nothing, which produces a real negative margin against known cost —
  // and it is not the same fact as supplying nothing, which this panel serves
  // as an absence. A "greater than zero" rule would make it unsayable.
  it("accepts a deliberate zero", async () => {
    renderWithProviders(<RevenuePanels customerId={CUS_LUNA} range={JULY} />);
    fireEvent.change(await field("Month this covers"), { target: { value: "2026-08" } });
    fireEvent.change(await field(/^Amount/), { target: { value: "0" } });
    fireEvent.change(await field("Where it came from"), {
      target: { value: "FREE-TRIAL-AUG" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Record revenue" }));

    await waitFor(() => {
      expect(provider.recordSuppliedRevenue).toHaveBeenCalledWith(
        CUS_LUNA,
        expect.objectContaining({ amount_micros: 0, source_reference: "FREE-TRIAL-AUG" }),
      );
    });
  });

  it("refuses a start day outside the month it names", async () => {
    renderWithProviders(<RevenuePanels customerId={CUS_LUNA} range={JULY} />);
    fireEvent.change(await field("Month this covers"), { target: { value: "2026-06" } });
    fireEvent.change(
      await field("Day it started, if part-way through the month"),
      { target: { value: "2026-07-14" } },
    );
    fireEvent.change(await field(/^Amount/), { target: { value: "510" } });
    fireEvent.change(await field("Where it came from"), { target: { value: "INV-OOPS" } });
    fireEvent.click(screen.getByRole("button", { name: "Record revenue" }));

    expect(
      await screen.findByText("Pick a day inside the month this covers"),
    ).toBeInTheDocument();
    expect(provider.recordSuppliedRevenue).not.toHaveBeenCalled();
  });

  // The write is ADMIN and the read is at the READ floor, mirroring the
  // route's own pair. A read-scoped session still SEES what has been supplied.
  it("cannot be written from a read-scoped session", async () => {
    role.value = "read";
    renderWithProviders(<RevenuePanels customerId={CUS_LUNA} range={JULY} />);

    await within(await supplied()).findByText("INV-2026-07");
    expect(screen.getByRole("button", { name: "Record revenue" })).toBeDisabled();
    expect(await field("Month this covers")).toBeDisabled();
  });
});
