import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { resetPricingMockState } from "../api/mock";
import { MOCK_OVERRIDE_CUSTOMER_ID } from "../api/mock-data";
import { CustomerPricingTab } from "./customer-pricing-tab";

beforeEach(resetPricingMockState);

function renderTab(customerId = MOCK_OVERRIDE_CUSTOMER_ID) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <CustomerPricingTab customerId={customerId} />
    </QueryClientProvider>,
  );
}

/** Ask what this customer inherits for the usage the mock's story prices. */
async function lookUpTheInheritedRule() {
  fireEvent.change(screen.getByLabelText("Measurement"), {
    target: { value: "gpt4o_input_tokens" },
  });
  fireEvent.change(screen.getByLabelText("Provider"), {
    target: { value: "openai" },
  });
  fireEvent.change(screen.getByLabelText("Event type"), {
    target: { value: "chat.completion" },
  });
  // ⚠ AND THE GROUPING VALUE, BECAUSE IT IS PART OF THE QUESTION. This
  // tenant's catalogue prices `gpt-4o` specifically, so a lookup that named
  // only the measurement and the provider would correctly answer "nothing is
  // inherited" — the rule pins a model and the question did not.
  await screen.findByLabelText("model");
  fireEvent.change(screen.getByLabelText("model"), {
    target: { value: "gpt-4o" },
  });
}

describe("one customer's own pricing rules", () => {
  it("shows what they inherit today — the amount, the shape and the method", async () => {
    // ⚠ THE STARTING POINT IS A RULE, NOT A NUMBER. The route answers the same
    // ladder one rung shorter, so what a tenant reads here cannot drift from
    // what they are about to replace.
    renderTab();
    await lookUpTheInheritedRule();

    expect(await screen.findByText("$5 / 1M")).toBeInTheDocument();
    expect(screen.getByText("Per unit")).toBeInTheDocument();
    expect(screen.getByText("Direct event price")).toBeInTheDocument();
  });

  it("opens the editor pre-filled from the inherited rule", async () => {
    renderTab();
    await lookUpTheInheritedRule();
    expect(await screen.findByText("$5 / 1M")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Write their own rule from this" }),
    );

    // ⚠ EVERY FIELD, BECAUSE THE BODY INHERITS NOTHING. `CustomerOverrideIn`
    // takes the model's defaults for anything left out — never the superseded
    // rule's value — so a form pre-filled with half of what it inherits would
    // send a rule the tenant never saw.
    const amount = (await screen.findByLabelText(/^Amount \(/)) as HTMLInputElement;
    expect(amount.value).toBe("5");
    expect(
      (screen.getAllByLabelText("Measurement")[1] as HTMLInputElement).value,
    ).toBe("gpt4o_input_tokens");
    // The method is PRESELECTED from what they inherit, rather than defaulted.
    expect(
      screen.getByRole("radio", { name: /Direct event price/i }),
    ).toBeChecked();
    expect(screen.getByRole("radio", { name: /Margin over cost/i })).not.toBeChecked();
  });

  // ⚠ THE CASE SPEC §21 SAYS IS USUALLY MISSED. The override editor is a RULE
  // editor: changing the method has to stay possible, and it has to be an act a
  // tenant takes deliberately rather than a side effect of typing a number.
  // A dialog offering only an amount would make this change unreachable while
  // looking complete.
  it("lets a tenant change the method through the UI, deliberately", async () => {
    renderTab();
    await lookUpTheInheritedRule();
    expect(await screen.findByText("$5 / 1M")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Write their own rule from this" }),
    );
    await screen.findByLabelText(/^Amount \(/);

    // Both options and what each does to the deal are on the screen; the
    // tenant picks the other one.
    expect(
      screen.getByText(/What the customer pays moves when your supplier's price moves/i),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: /Margin over cost/i }));

    expect(screen.getByRole("radio", { name: /Margin over cost/i })).toBeChecked();
    // And the console stops offering to work out a figure, because a margin's
    // basis is the particular call's cost and is not on this form.
    expect(
      await screen.findByText(/settled per event from the supplier’s own figure/i),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Declare this deal" }));

    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Declare this deal" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("says declaring writes no rule, because it does not", async () => {
    // The two-step is the whole model: an override is declared as a draft on
    // the customer's own book, and publishing that draft is what puts the deal
    // in force. A tab that said "saved" would be claiming a charge changed.
    renderTab();
    await lookUpTheInheritedRule();
    expect(await screen.findByText("$5 / 1M")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Write their own rule from this" }),
    );

    expect(
      await screen.findByText(/Declaring writes no rule/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/publishing that draft is what puts the deal in force/i))
      .toBeInTheDocument();
  });

  // ⚠ NOTHING INHERITED IS AN ORDINARY STATE, NOT AN ERROR. A quantity no book
  // in play prices falls to the tenant's markup rung; a tab that refused to
  // open its editor there would make the one case where a customer has no
  // price at all the one case a tenant cannot fix.
  it("offers to write a rule even where nothing is inherited", async () => {
    renderTab();
    fireEvent.change(screen.getByLabelText("Measurement"), {
      target: { value: "nothing_prices_this" },
    });

    expect(await screen.findByText("Nothing inherited")).toBeInTheDocument();
    expect(
      screen.getByText(/falls to your default markup rung/i),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Write their own rule" }));

    expect(
      await screen.findByText(/this rule starts from nothing/i),
    ).toBeInTheDocument();
    // And the editor still opened on the usage they asked about, so the rule
    // they write prices the thing they were looking at.
    expect(
      (screen.getAllByLabelText("Measurement")[1] as HTMLInputElement).value,
    ).toBe("nothing_prices_this");
  });

  it("offers every slot this tenant declared, so a deal can pin any of them", async () => {
    renderTab();
    await lookUpTheInheritedRule();
    expect(await screen.findByText("$5 / 1M")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Write their own rule from this" }),
    );
    const editor = within(
      (await screen.findByLabelText(/^Amount \(/)).closest("form") as HTMLElement,
    );

    for (const key of ["model", "tier", "cohort"]) {
      expect(editor.getByLabelText(key)).toBeInTheDocument();
    }
  });
});
