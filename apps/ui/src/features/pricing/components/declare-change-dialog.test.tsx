import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import * as React from "react";
import { beforeEach, describe, expect, it } from "vitest";

import { resetPricingMockState } from "../api/mock";
import { MOCK_PRICING_BOOKS } from "../api/mock-data";
import { BookChangesPanel } from "./book-changes-panel";
import { DeclareChangeDialog } from "./declare-change-dialog";

const STANDARD = MOCK_PRICING_BOOKS[0]!;

beforeEach(resetPricingMockState);

/**
 * The dialog and the panel together, because the point of declaring a change is
 * that somebody reads its diff afterwards.
 *
 * A dialog test that asserted only "the mutation was called" would pass against
 * a console that sent the wrong body — the assertion that matters is what the
 * book's pending changes say about it once it is there.
 */
function Harness() {
  const [open, setOpen] = React.useState(true);
  return (
    <>
      <BookChangesPanel book={STANDARD} onDeclareChange={() => setOpen(true)} />
      <DeclareChangeDialog book={STANDARD} open={open} onOpenChange={setOpen} />
    </>
  );
}

/**
 * ⚠ THE DIALOG'S OPEN STATE IS REAL, NOT PINNED OPEN. An open dialog marks
 * everything behind it inert, so the panel is invisible to a role query while
 * it is up — and a harness that hard-coded `open` would leave the diff
 * permanently unreachable, which is the assertion these cases exist for.
 * Declaring closes it, which is also what a tenant experiences.
 */
function renderDialog() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>,
  );
}

/**
 * Fill the rule editor in the dialog and stage what it holds.
 *
 * ⚠ IT AWAITS THE TENANT'S SLOTS FIRST. The editor's grouping inputs are
 * driven off the tenant's declared registry, which arrives over the same
 * provider as everything else — a synchronous query would be asking for a slot
 * before the console knows the tenant has one, and would fail for a reason that
 * is never the subject of a case here.
 */
async function fillRule(fields: {
  measurement: string;
  eventType?: string;
  method?: "Margin over cost" | "Direct event price";
  amount?: string;
  pins?: Record<string, string>;
}) {
  await screen.findByLabelText("model");
  const dialog = within(screen.getByRole("dialog"));
  fireEvent.change(dialog.getByLabelText("Measurement"), {
    target: { value: fields.measurement },
  });
  if (fields.eventType !== undefined) {
    fireEvent.change(dialog.getByLabelText("Event type"), {
      target: { value: fields.eventType },
    });
  }
  if (fields.method !== undefined) {
    fireEvent.click(dialog.getByRole("radio", { name: new RegExp(fields.method, "i") }));
  }
  if (fields.amount !== undefined) {
    fireEvent.change(dialog.getByLabelText(/^Amount \(/), {
      target: { value: fields.amount },
    });
  }
  for (const [key, value] of Object.entries(fields.pins ?? {})) {
    fireEvent.change(dialog.getByLabelText(key), { target: { value } });
  }
  fireEvent.click(dialog.getByRole("button", { name: "Add to this draft" }));
  // Staging goes through the form's async resolver, so the list it lands in is
  // one tick behind the click.
  await within(screen.getByRole("dialog")).findByText(fields.measurement);
}

describe("declaring a change to a book", () => {
  it("offers every slot this tenant declared, not the six the contract used to name", async () => {
    renderDialog();
    await screen.findByLabelText("model");
    const dialog = within(screen.getByRole("dialog"));

    // ⚠ TEN, AND THE SEVENTH IS THE ONE THAT MATTERS (#366 ruling 15). A rule
    // could be pinned on the seventh slot server-side and never repriced
    // through the API, because the published contract named six. The editor
    // reads the tenant's registry rather than a list written here, so a
    // console built against the old contract fails this.
    for (const key of [
      "model",
      "region",
      "environment",
      "team",
      "workflow",
      "channel",
      "tier",
      "deployment",
      "pipeline",
      "cohort",
    ]) {
      expect(dialog.getByLabelText(key)).toBeInTheDocument();
    }
  });

  it("assembles several changes into one draft, with one diff", async () => {
    // ⚠ ONE DRAFT, NOT ONE PER RULE. A tenant agreeing a repricing does not
    // agree it one rule at a time; a console that declared a draft per rule
    // would record one decision as several, and the diff read before committing
    // would never be the decision that was actually made.
    renderDialog();
    await screen.findByRole("dialog");

    await fillRule({
      measurement: "claude_input_tokens",
      eventType: "chat.completion",
      method: "Direct event price",
      amount: "6",
    });
    await fillRule({
      measurement: "claude_output_tokens",
      eventType: "chat.completion",
      method: "Margin over cost",
    });

    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByText("claude_input_tokens")).toBeInTheDocument();
    expect(dialog.getByText("claude_output_tokens")).toBeInTheDocument();

    fireEvent.click(dialog.getByRole("button", { name: /Declare 2 changes/ }));

    const changes = within(
      await screen.findByRole("region", { name: "Changes to this book" }),
    );
    await waitFor(() =>
      expect(changes.getByText(/4 changes are waiting/i)).toBeInTheDocument(),
    );
    // ONE new row carrying BOTH — a draft, not two drafts.
    const newRow = changes.getByText("claude_input_tokens").closest("li")
      ?.parentElement as HTMLElement;
    expect(within(newRow).getByText("claude_output_tokens")).toBeInTheDocument();
  });

  it("pins a rule on the seventh slot and shows it in the diff", async () => {
    renderDialog();
    await screen.findByRole("dialog");

    await fillRule({
      measurement: "claude_input_tokens",
      eventType: "chat.completion",
      method: "Direct event price",
      amount: "6",
      pins: { tier: "premium" },
    });
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: /Declare 1 change/,
      }),
    );

    const changes = within(
      await screen.findByRole("region", { name: "Changes to this book" }),
    );
    await waitFor(() =>
      expect(changes.getByText("claude_input_tokens")).toBeInTheDocument(),
    );
    expect(changes.getByText("premium")).toBeInTheDocument();
    expect(changes.getAllByText("tier=").length).toBeGreaterThanOrEqual(1);
  });

  it("names the method and the arithmetic on the rule it adds", async () => {
    renderDialog();
    await screen.findByRole("dialog");

    await fillRule({
      measurement: "claude_input_tokens",
      eventType: "chat.completion",
      method: "Margin over cost",
    });
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: /Declare 1 change/,
      }),
    );

    const changes = within(
      await screen.findByRole("region", { name: "Changes to this book" }),
    );
    await waitFor(() =>
      expect(changes.getByText("claude_input_tokens")).toBeInTheDocument(),
    );
    expect(changes.getAllByText(/Margin over cost/).length).toBeGreaterThanOrEqual(1);
  });

  // ⚠ THE HORIZON IS A NAMED REFUSAL AND HAS TO REACH THE TENANT AS ONE. The
  // platform coins `effective_at_too_far_ahead` precisely so that "that date is
  // a typo" is distinguishable from every other reason a body is refused; a
  // console rendering the generic validation message would throw that away at
  // the last step.
  it("surfaces the 366-day refusal in words a tenant can act on", async () => {
    renderDialog();
    await screen.findByRole("dialog");

    await fillRule({
      measurement: "claude_input_tokens",
      eventType: "chat.completion",
      method: "Direct event price",
      amount: "6",
    });

    const dialog = within(screen.getByRole("dialog"));
    fireEvent.click(dialog.getByRole("switch", { name: "Date this change ahead" }));
    const twoYearsOut = new Date(Date.now() + 730 * 86_400_000)
      .toISOString()
      .slice(0, 16);
    fireEvent.change(dialog.getByLabelText("Takes effect"), {
      target: { value: twoYearsOut },
    });
    fireEvent.click(dialog.getByRole("button", { name: /Declare 1 change/ }));

    expect(
      await screen.findByText(/more than 366 days away/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/no setting moves it/i),
    ).toBeInTheDocument();
    // The dialog stays open, which is the right behaviour: a refused date is
    // something to correct, not something to start again.
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    // And nothing was declared. The panel is inert behind an open dialog, so
    // the assertion is made after closing it — which is also the only way a
    // tenant would see it.
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }),
    );
    const changes = within(
      await screen.findByRole("region", { name: "Changes to this book" }),
    );
    expect(changes.getByText(/3 changes are waiting/i)).toBeInTheDocument();
  });

  it("schedules a change inside the horizon, and it renders as scheduled", async () => {
    // The admitted move beside the refusal: a refusal test on its own is
    // satisfied by a console that refused everything.
    renderDialog();
    await screen.findByRole("dialog");

    await fillRule({
      measurement: "claude_input_tokens",
      eventType: "chat.completion",
      method: "Direct event price",
      amount: "6",
    });

    const dialog = within(screen.getByRole("dialog"));
    fireEvent.click(dialog.getByRole("switch", { name: "Date this change ahead" }));
    const inSixtyDays = new Date(Date.now() + 60 * 86_400_000)
      .toISOString()
      .slice(0, 16);
    fireEvent.change(dialog.getByLabelText("Takes effect"), {
      target: { value: inSixtyDays },
    });
    fireEvent.click(dialog.getByRole("button", { name: /Declare 1 change/ }));

    const changes = within(
      await screen.findByRole("region", { name: "Changes to this book" }),
    );
    await waitFor(() =>
      expect(changes.getByText(/4 changes are waiting, 3 of them dated ahead/i))
        .toBeInTheDocument(),
    );
    expect(changes.getAllByText("Scheduled")).toHaveLength(3);
  });
});
