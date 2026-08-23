import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resetPricingMockState } from "../api/mock";
import { BookDetailPage } from "./book-detail-page";

const OPENAI_COST_BOOK = "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e01";
const STANDARD_PRICING_BOOK = "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e03";
const EMPTY_PRICING_BOOK = "0b1e6a4e-9c1d-4f2a-8f3b-1a2b3c4d5e04";

const onShowAuditTrail = vi.fn();

// ⚠ THE MOCK'S STATE IS THIS FILE'S SUBJECT, so it is put back between
// cases. Declaring, publishing and discarding all move module-level state
// and vitest isolates modules per FILE rather than per test — without this,
// "discard leaves the book unchanged" would run against a book an earlier
// case had already changed, and would pass or fail on the order the file
// happens to be written in.
beforeEach(resetPricingMockState);

/** Publish the earliest scheduled draft on the page, through its confirmation. */
async function publishFirstScheduled() {
  const scheduled = screen
    .getAllByText("Scheduled")[0]!
    .closest("[data-slot='card']") as HTMLElement;
  fireEvent.click(within(scheduled).getByRole("button", { name: "Publish" }));
  const confirm = within(await screen.findByRole("dialog"));
  fireEvent.click(confirm.getByRole("button", { name: "Publish" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
}

function renderPage(bookId: string) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <BookDetailPage bookId={bookId} onShowAuditTrail={onShowAuditTrail} />
    </QueryClientProvider>,
  );
}

describe("BookDetailPage", () => {
  it("renders a cost book's header and only its active rules by default", async () => {
    renderPage(OPENAI_COST_BOOK);
    expect(await screen.findByText("OpenAI provider costs")).toBeInTheDocument();
    expect(screen.getByText("v3")).toBeInTheDocument();
    expect(screen.getByText("Cost book")).toBeInTheDocument();
    // A cost book names the supplier it records and the currency that
    // supplier bills in (#368).
    expect(screen.getByText("Default for openai")).toBeInTheDocument();
    expect(screen.getByText("usd")).toBeInTheDocument();
    // Active rules with formatted prices.
    expect(await screen.findByText("gpt4o_input_tokens")).toBeInTheDocument();
    expect(screen.getByText("$2.5 / 1M")).toBeInTheDocument();
    expect(screen.getByText("image_generation")).toBeInTheDocument();
    expect(screen.getByText("Fixed component")).toBeInTheDocument();
    // The superseded $5/1M version is history — hidden in the default view.
    expect(screen.queryByText("$5 / 1M")).not.toBeInTheDocument();
  });

  it("files the audit trail under the record the ledger actually uses", async () => {
    // ⚠ THE FILTER NAMES THE KIND OF BOOK (#368). The two are two records with
    // two sets of audit actions, so a page that sent one word for both would
    // walk half its books to an empty trail. The page derives it; the route
    // navigates with whatever it is handed.
    renderPage(OPENAI_COST_BOOK);
    expect(await screen.findByText("OpenAI provider costs")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Who changed this book?" }));

    expect(onShowAuditTrail).toHaveBeenCalledWith({
      resource_type: "cost_book",
      resource_id: OPENAI_COST_BOOK,
    });
  });

  it("renders a pricing book's header, which names neither of those", async () => {
    // ⚠ THE DISCRIMINATING HALF (#368). A header that merely rendered would
    // pass the case above whether or not the two entities differ; what makes
    // the split visible is that the supplier and the currency are ABSENT here,
    // because a Pricing Book has no such columns.
    renderPage(STANDARD_PRICING_BOOK);

    expect(await screen.findByText("Standard price list")).toBeInTheDocument();
    expect(screen.getByText("Pricing book")).toBeInTheDocument();
    expect(screen.getByText("Default")).toBeInTheDocument();
    expect(screen.queryByText("Default for openai")).not.toBeInTheDocument();
    expect(screen.queryByText("usd")).not.toBeInTheDocument();
  });

  it("shows an empty state for a book without rules", async () => {
    renderPage(EMPTY_PRICING_BOOK);
    expect(await screen.findByText("Enterprise 2026 negotiated")).toBeInTheDocument();
    expect(await screen.findByText("No rules yet")).toBeInTheDocument();
    expect(await screen.findByText("No changes pending")).toBeInTheDocument();
  });

  // ⚠ ALL TEN SLOTS, IN THE TENANT'S OWN WORDS (#366 ruling 15, #277). A rule
  // pinned on the seventh slot was writable server-side and unreachable
  // through the API until this slice; a console that walked the six the
  // contract used to publish would still be showing that gap.
  it("shows a rule pinned on the seventh slot, labelled with the declared key", async () => {
    renderPage(STANDARD_PRICING_BOOK);

    expect(await screen.findByText("Standard price list")).toBeInTheDocument();
    expect(await screen.findByText("premium")).toBeInTheDocument();
    expect(screen.getAllByText("tier=").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText(/grouping_field_7/)).not.toBeInTheDocument();
  });
});

/**
 * The changes pending on a book: what is about to happen to its prices.
 */
describe("a book's pending changes", () => {
  it("renders the series, with the dated ones counted", async () => {
    // ⚠ A SERIES, NOT ONE PENDING ITEM. There is no limit on how many changes a
    // book may have scheduled at once; a panel showing "the next change" would
    // hide every one after it, which is precisely what a tenant dating changes
    // forward is trying to see.
    renderPage(STANDARD_PRICING_BOOK);

    expect(await screen.findByText("Changes")).toBeInTheDocument();
    expect(
      await screen.findByText(/3 changes are waiting, 2 of them dated ahead/i),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Scheduled")).toHaveLength(2);
    expect(screen.getAllByText("Takes effect now")).toHaveLength(1);
  });

  it("shows the diff of each draft before it is committed to", async () => {
    renderPage(STANDARD_PRICING_BOOK);

    // ⚠ AWAIT THE DRAFTS, NOT THE HEADING. "Changes" is the panel's title and
    // is on the screen before the query resolves, so awaiting it would assert
    // against an empty panel and fail for a reason that is not the subject.
    expect(await screen.findByText("Adds a rule")).toBeInTheDocument();
    // One draft carries TWO changes — a tenant agreeing a repricing does not
    // agree it one rule at a time, and the diff they read has to be the
    // decision they actually made.
    // Scoped to the panel: the rules table below renders the same amounts for
    // the same rules, which is what a diff IS — so an unscoped query cannot say
    // which of the two it found.
    const changes = within(
      screen.getByRole("region", { name: "Changes to this book" }),
    );
    expect(changes.getAllByText("Reprices").length).toBeGreaterThanOrEqual(2);
    expect(changes.getAllByText("$5 / 1M").length).toBeGreaterThanOrEqual(1);
    expect(changes.getByText("$5.5 / 1M")).toBeInTheDocument();
  });

  // ⚠ A REVERSAL IS A SECOND PUBLISH IN THE SERIES, NOT A REMOVAL. The
  // contract admits a change landing exactly on a boundary already scheduled
  // and says outright that this is how a scheduled change is reversed. Both
  // rows stay: a declaration somebody made is not un-made by changing their
  // mind about it, and the pair reads as "we put it up and then we put it back".
  it("renders a reversal as a further change, leaving the one it undoes in place", async () => {
    renderPage(STANDARD_PRICING_BOOK);

    await screen.findByText("Adds a rule");
    const changes = within(
      screen.getByRole("region", { name: "Changes to this book" }),
    );

    // The rise is still there — twice, in fact: as the `after` of the change
    // that raises the price and as the `before` of the one that puts it back.
    // That is what makes the pair readable as a reversal rather than as a
    // correction somebody made to their own draft.
    expect(changes.getAllByText("$24 / 1M")).toHaveLength(2);
    expect(changes.getAllByText("$20 / 1M").length).toBeGreaterThanOrEqual(2);
    // Two scheduled rows at the one instant, not one row that changed its mind.
    expect(changes.getAllByText("Scheduled")).toHaveLength(2);
  });

  // ⚠ AND ONCE BOTH ARE PUBLISHED, THE HISTORY SAYS THE SAME THING. The case
  // above is about the SERIES — two declarations, both visible. This one is
  // about what a tenant sees afterwards, which is where "not a removal" is
  // actually falsifiable: a superseded rule keeps its row and gains an end
  // date, so putting a price back leaves THREE versions in one lineage with
  // the middle one closed. A console that showed two, or that dropped the
  // reversed one, would be reporting that the rise never happened.
  it("leaves the reversed change in the history, as a closed version", async () => {
    renderPage(STANDARD_PRICING_BOOK);
    await screen.findByText("Adds a rule");

    // Publish the rise, then the change that puts it back. One at a time, each
    // waited on by the count the panel prints: the two share an effective
    // instant, so "the first scheduled row" is only a stable thing to click
    // once the previous publish has actually left the list.
    await publishFirstScheduled();
    await waitFor(() =>
      expect(
        screen.getByText(/2 changes are waiting, 1 of them dated ahead/i),
      ).toBeInTheDocument(),
    );
    await publishFirstScheduled();
    await waitFor(() =>
      expect(screen.getByText(/1 change is waiting/i)).toBeInTheDocument(),
    );

    // History on: the lineage reads $20 → $24 → $20, and the middle version is
    // closed rather than gone.
    fireEvent.click(screen.getByRole("switch", { name: "Include history" }));

    await waitFor(() =>
      expect(
        screen
          .getAllByRole("row")
          .filter((row) => (row.textContent ?? "").includes("gpt4o_output_tokens")),
      ).toHaveLength(3),
    );
    const rows = screen
      .getAllByRole("row")
      .map((row) => row.textContent ?? "")
      .filter((text) => text.includes("gpt4o_output_tokens"));

    // Three versions of the one rule, not two — nothing was removed.
    expect(rows).toHaveLength(3);
    expect(rows.filter((text) => text.includes("$24 / 1M"))).toHaveLength(1);
    expect(rows.filter((text) => text.includes("$20 / 1M"))).toHaveLength(2);
    // And exactly one of the three is the live one.
    expect(rows.filter((text) => text.includes("Active"))).toHaveLength(1);
  });

  it("publishes a draft, and the rules it opened appear in the book", async () => {
    renderPage(STANDARD_PRICING_BOOK);

    const immediate = (await screen.findByText("Takes effect now"))
      .closest("[data-slot='card']") as HTMLElement;
    fireEvent.click(within(immediate).getByRole("button", { name: "Publish" }));

    // CONFIRMED FIRST, AND THE CONSEQUENCE IS ON THE DIALOG. Publishing is not
    // undone by publishing again — what undoes it is a FURTHER change — so it
    // goes through the console's confirmation the way every act of that shape
    // does.
    const confirm = within(await screen.findByRole("dialog"));
    expect(
      confirm.getByText(/the only way to undo it is to publish a further change/i),
    ).toBeInTheDocument();
    fireEvent.click(confirm.getByRole("button", { name: "Publish" }));

    // The draft leaves the pending series, and what it did is in the rules.
    await waitFor(() =>
      expect(screen.getByText(/2 changes are waiting/i)).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.getAllByText("$5.5 / 1M").length).toBeGreaterThanOrEqual(1),
    );
  });

  // ⚠ DISCARDING LEAVES THE BOOK UNCHANGED, WHICH IS THE WHOLE POINT OF A
  // DRAFT. It closed nothing, so it reopens nothing — and the assertion is on
  // the RULES rather than on the draft disappearing, because a draft
  // disappearing is also what publishing looks like.
  it("discards a draft and leaves the book exactly as it stood", async () => {
    renderPage(STANDARD_PRICING_BOOK);

    // Both the rules table and the pending drafts have to be on the screen
    // before "unchanged" means anything.
    await screen.findByText("Adds a rule");
    const before = screen
      .getAllByRole("row")
      .map((row) => row.textContent ?? "")
      .join("|");

    const immediate = screen
      .getByText("Takes effect now")
      .closest("[data-slot='card']") as HTMLElement;
    fireEvent.click(within(immediate).getByRole("button", { name: "Discard" }));

    // The confirmation says what actually goes: the book keeps its rules, and
    // the DECLARATION is what is lost.
    const confirm = within(await screen.findByRole("dialog"));
    expect(
      confirm.getByText(/the book keeps exactly the rules it has now/i),
    ).toBeInTheDocument();
    fireEvent.click(confirm.getByRole("button", { name: "Discard" }));

    await waitFor(() =>
      expect(screen.getByText(/2 changes are waiting/i)).toBeInTheDocument(),
    );
    const after = screen
      .getAllByRole("row")
      .map((row) => row.textContent ?? "")
      .join("|");
    expect(after).toEqual(before);
    // And specifically: the rule the discarded draft would have opened is not
    // in the book, and the one it would have superseded still is.
    expect(screen.queryByText("$5.5 / 1M")).not.toBeInTheDocument();
    expect(screen.getAllByText("$5 / 1M").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("v2")).toBeInTheDocument();
  });
});
