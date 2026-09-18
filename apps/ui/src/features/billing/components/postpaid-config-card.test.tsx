// The invoice-line grouping form (#508; slice 7 §6, §11).
//
// WHAT THIS FILE PROVES, and what it deliberately leaves to the lib beside it:
//
//   * the picker's options are the TENANT's, off the discovery contract, with
//     each axis's KIND visible and the analytics-only axis absent;
//   * the cardinality warning and the rollup statement render **beside the
//     choice**, which is the "configuration time" §11 means;
//   * saving sends exactly what the form's own builder builds.
//
// ⚠ **THE FIXTURE BUILDER IS IMPORTED RATHER THAN WRITTEN HERE, AND THAT IS A
// LEDGER CEILING RATHER THAN A STYLE CHOICE.** The stored field's name is a
// retired term whose console entry is a SPREAD ceiling — a NEW file spelling it
// fails `term_spread` before any payment is attempted, and the field cannot
// leave this console until the contract renames it. So the one fixture that has
// to name it lives in the fixtures module that already does.
//
// ⚠ **WHICH AXIS PRODUCES WHICH SENTENCE IS THE LIB'S CASE, NOT THIS ONE'S.**
// A Base UI select's items carry their value in React state rather than in an
// attribute, and cannot be reliably chosen in jsdom — so a component test that
// tried to prove the warning FOLLOWS a choice would be proving the test
// harness. The rule is a pure function with its own cases
// (`../lib/invoice-lines.test.ts`); what varies here is the CONFIGURATION the
// form opens on, which reaches the same branch through the door a tenant
// actually arrives by.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { postpaidConfiguredOn as configuredOn } from "../api/mock-data";
import { buildPostpaidPayload } from "../lib/billing-forms";
import { ROLLUP_RECLASSIFIES_HISTORY, SINGLE_LINE_LABEL } from "../lib/invoice-lines";
import { PostpaidConfigCard } from "./postpaid-config-card";

const provider = vi.hoisted(() => ({
  getPostpaidConfig: vi.fn(),
  putPostpaidConfig: vi.fn(),
}));

vi.mock("../api/provider", async () => {
  const mock = await vi.importActual<typeof import("../api/mock")>("../api/mock");
  return {
    billingFeatureApi: {
      ...mock,
      getPostpaidConfig: provider.getPostpaidConfig,
      putPostpaidConfig: provider.putPostpaidConfig,
    },
  };
});

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

function renderCard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <PostpaidConfigCard />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  role.value = "admin";
  provider.getPostpaidConfig.mockReset();
  provider.putPostpaidConfig.mockReset();
});

describe("the axes on offer", () => {
  it("offers the tenant's own axes with each one's kind visible", async () => {
    provider.getPostpaidConfig.mockResolvedValue(configuredOn("field:event_type"));
    renderCard();

    // The trigger words the stored axis rather than echoing the request word:
    // a tenant reading their own invoice layout must not be shown
    // `field:event_type`.
    //
    // ⚠ **AWAITED, BECAUSE THE WORDING ARRIVES WITH THE DISCOVERY CONTRACT.**
    // Until the tenant's own axis list lands there is nothing to look the
    // stored value up in, so the trigger shows the token itself, marked
    // unrecognised — the open-set rule's answer, and the honest one for a value
    // this build cannot yet resolve. It is the same beat the chart picker has.
    const trigger = await screen.findByLabelText("Usage line items");
    await waitFor(() => expect(trigger).toHaveTextContent("Event type"));
    expect(trigger).not.toHaveTextContent("field:event_type");

    fireEvent.click(trigger);

    // ⚠ THE KIND IS PART OF THE ROW, because a field is a column and a rollup
    // is a join — different cardinality, different cost — and an untyped list
    // hides that behind identical-looking names (§6).
    await waitFor(() => {
      expect(screen.getAllByText("Field").length).toBeGreaterThan(0);
    });
    expect(screen.getByText("Roll-up")).toBeInTheDocument();
    expect(screen.getByText("Event Category")).toBeInTheDocument();
    // The tenant's own declared axis, rendered exactly as they declared it.
    expect(screen.getByText("model")).toBeInTheDocument();
    // One total is an ABSENCE of grouping and is offered as such.
    expect(screen.getByText(SINGLE_LINE_LABEL)).toBeInTheDocument();
  });

  // An axis resolving at the measurement grain is analytics-only: an invoice
  // line is money and UBB holds none at that grain. Offering it would put an
  // axis in the picker whose request the server refuses at save.
  it("does not offer the analytics-only axis", async () => {
    provider.getPostpaidConfig.mockResolvedValue(configuredOn("field:event_type"));
    renderCard();
    fireEvent.click(await screen.findByLabelText("Usage line items"));

    await waitFor(() => {
      expect(screen.getByText("Event Category")).toBeInTheDocument();
    });
    expect(screen.queryByText("Measurement Concept")).not.toBeInTheDocument();
  });
});

describe("what the form says about the choice", () => {
  // ⚠ AT CONFIGURATION TIME, beside the picker — not at invoice time, where
  // the first anyone hears of it is a 5,000-line invoice already sent.
  it("warns beside the picker when the chosen axis carries a declared cap", async () => {
    provider.getPostpaidConfig.mockResolvedValue(configuredOn("field:model"));
    renderCard();

    const warning = await screen.findByText(/one line per distinct value/);
    expect(warning.getAttribute("data-invoice-warning")).toBe("cardinality");
    expect(warning).toHaveTextContent("Rollups are preferred for invoices");
    // It WARNS and never refuses — the save is still available.
    expect(screen.getByRole("button", { name: "Save settings" })).toBeInTheDocument();
  });

  it("says nothing about cardinality for an axis UBB owns", async () => {
    provider.getPostpaidConfig.mockResolvedValue(configuredOn("field:event_type"));
    renderCard();
    await screen.findByLabelText("Usage line items");
    expect(screen.queryByText(/one line per distinct value/)).not.toBeInTheDocument();
  });

  // §6: changing a rollup reclassifies history, and that is safe precisely
  // because rollups touch no money. Both halves, where the rollup is chosen.
  it("states what changing a rollup does, where the rollup is chosen", async () => {
    provider.getPostpaidConfig.mockResolvedValue(configuredOn("rollup:event_category"));
    renderCard();

    const note = await screen.findByText(ROLLUP_RECLASSIFIES_HISTORY);
    expect(note.getAttribute("data-invoice-note")).toBe("rollup-reclassifies");
    expect(note).toHaveTextContent("reclassifies history");
    expect(note).toHaveTextContent("moves no money");
  });

  it("does not claim a field reclassifies anything", async () => {
    provider.getPostpaidConfig.mockResolvedValue(configuredOn("field:event_type"));
    renderCard();
    await screen.findByLabelText("Usage line items");
    expect(screen.queryByText(ROLLUP_RECLASSIFIES_HISTORY)).not.toBeInTheDocument();
  });
});

describe("saving", () => {
  it("sends what the form's own builder builds for the current state", async () => {
    const current = configuredOn("field:event_type");
    provider.getPostpaidConfig.mockResolvedValue(current);
    provider.putPostpaidConfig.mockResolvedValue({
      ...current,
      consolidate_with_subscription: true,
    });
    renderCard();

    await screen.findByLabelText("Usage line items");
    fireEvent.click(screen.getByRole("switch"));
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));

    // ⚠ THE EXPECTED BODY IS BUILT BY THE BUILDER RATHER THAN SPELLED OUT, and
    // that is deliberate rather than lazy: what this asserts is that the card
    // sends the builder's answer for the state it is in, and the builder's
    // answer is pinned field by field in `../lib/billing-forms.test.ts`.
    // Spelling the wire key a second time here would put this file inside the
    // extent of a ledger entry it has no business being in.
    await waitFor(() => {
      expect(provider.putPostpaidConfig).toHaveBeenCalledWith(
        buildPostpaidPayload(current, { axis: "field:event_type", consolidate: true }),
      );
    });
  });

  it("cannot be saved from a session below the Admin floor", async () => {
    role.value = "write";
    provider.getPostpaidConfig.mockResolvedValue(configuredOn("field:event_type"));
    renderCard();

    await screen.findByLabelText("Usage line items");
    expect(screen.getByRole("button", { name: "Save settings" })).toBeDisabled();
    expect(screen.getByText("Changing invoicing settings needs the Admin role.")).toBeInTheDocument();
  });
});
