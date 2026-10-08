// Seam D (#184 spec part 4): the Code Builder's Verify stage (#581) against
// the mock provider, whose Blueprints AND Verify answers are the platform's
// own (`api/mock-blueprints.ts`, `api/mock-verifications.ts`). A sample typed
// here is the sample the platform verified with, so what renders is what the
// platform answered — nothing in this file builds an answer.

import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { setMockMemberRole } from "@/hooks/use-current-role";
import { pricingStatusLabel } from "@/lib/customer-price";
import { formatDate } from "@/lib/format";
import { costingStatusLabel, unresolvedReasonLabel } from "@/lib/supplier-cost";
import { UNKNOWN_TOTAL } from "@/lib/total-reading";

import { loadBlueprintFixture } from "../api/mock-blueprints";
import { loadVerificationFixture } from "../api/mock-verifications";
import type { BlueprintVerification } from "../api/types";
import { credentialShapeIn } from "../lib/credential-shapes";
import type { CodeBuilderSearch } from "../lib/code-builder-search";
import {
  CURRENCY_SAMPLE,
  diagnosticCodeLabel,
  STALE_RESULT_WARNING,
  SUPPLIER_COST_SAMPLE,
  VERIFIED_SCOPE,
} from "../lib/code-builder-words";
import { CURRENCY_REQUIRED, GROUPING_FIELD_REQUIRED } from "../lib/verification";
import { renderCodeBuilder } from "../test-utils";
import { REPLAY_TASK_TOTALS } from "./acknowledgement-card";

const REPORTED: CodeBuilderSearch = { task_type: "web_research", event_types: ["web.search"] };
const CALCULATED: CodeBuilderSearch = { task_type: "report_generation", event_types: ["chat.completion"] };
const DIRECT: CodeBuilderSearch = { task_type: "support_reply", event_types: ["reply.sent", "search.run"] };
const SUBTASKS: CodeBuilderSearch = {
  task_type: "report_generation",
  subtask_types: ["summarise"],
  event_types: ["gemini.generate"],
};
const BLOCKED: CodeBuilderSearch = {
  task_type: "report_generation",
  event_types: ["chat.completion", "draft.only", "web.search"],
};
/** A supplier's cost read off the provider's response (#583). */
const READ_OFF: CodeBuilderSearch = { task_type: "grounded_answer", event_types: ["grounded.search"] };
const READ_OFF_COST = SUPPLIER_COST_SAMPLE.provider_response_cost_micros;

const stage = (name: string) => screen.getByRole("region", { name });
const verify = () => stage("Verify");

afterEach(() => setMockMemberRole("admin"));

/** The record's fieldset in the Verify form, once the Blueprint has resolved. */
async function recordFields(eventType: string): Promise<HTMLElement> {
  return within(await screen.findByRole("region", { name: "Verify" })).findByRole("group", {
    name: `Record usage · ${eventType}`,
  });
}

function type(scope: HTMLElement, label: string, value: string) {
  fireEvent.change(within(scope).getByLabelText(label), { target: { value } });
}

function send() {
  fireEvent.click(within(verify()).getByRole("button", { name: "Verify this Blueprint" }));
}

async function result(): Promise<HTMLElement> {
  return within(verify()).findByRole("region", { name: "Verify result" }, { timeout: 5000 });
}

async function answer(name: string): Promise<BlueprintVerification> {
  const fixture = await loadVerificationFixture(name);
  if (fixture.kind !== "answered") throw new Error(`${name} is an answer`);
  return fixture.answer;
}

function stat(scope: HTMLElement, label: string): string {
  return within(scope).getByText(label).closest("div")?.textContent ?? "";
}

/** The verified run: every selected Event Type, with the samples the platform used. */
async function verifyReportedCost() {
  const record = await recordFields("web.search");
  type(record, "searches", "3");
  type(record, "Supplier cost, in micros", "1250000");
  send();
  return result();
}

/** The same for a cost read off the response, as the platform verified it. */
async function verifyReadOffCost() {
  const record = await recordFields("grounded.search");
  type(record, "input_tokens", "1200");
  type(record, READ_OFF_COST.label, "4200");
  send();
  return result();
}

/** A currency read off the response beside the cost: the Blueprint binds it
 * at run time, so it is a sample (owner review of #608). */
const READ_CURRENCY: CodeBuilderSearch = { task_type: "grounded_answer", event_types: ["billed.search"] };

/** A run with the currency sample as the platform verified it with. */
async function verifyReadCurrency(currency: string) {
  const record = await recordFields("billed.search");
  type(record, READ_OFF_COST.label, "1250000");
  type(record, CURRENCY_SAMPLE.label, currency);
  send();
  return result();
}

describe("Verify, offered", () => {
  it("is not offered for a Blueprint that is not complete, and says why in the Blueprint's words", async () => {
    renderCodeBuilder(BLOCKED);
    const note = await within(await screen.findByRole("region", { name: "Verify" })).findByRole("note");
    const blocked = await loadBlueprintFixture("blocked");

    expect(note).toHaveTextContent("Verify runs a complete Blueprint only, and this one is Blocked.");
    const waiting = within(note).getByRole("list", { name: "What it is waiting for" });
    expect(within(waiting).getAllByRole("listitem")).toHaveLength(blocked.diagnostics.length);
    for (const diagnostic of blocked.diagnostics) {
      expect(waiting).toHaveTextContent(diagnosticCodeLabel(diagnostic.code));
    }
    expect(within(verify()).queryByRole("button")).toBeNull();
    expect(within(verify()).queryByRole("textbox")).toBeNull();
  });

  // Fail open, as the console's primary actions are: the server's floor is
  // what refuses, and a member whose role is known to be below it is told.
  it("tells a member known to be below the write floor, and offers no samples", async () => {
    setMockMemberRole("read");
    const page = renderCodeBuilder(REPORTED);
    await waitFor(() => expect(page.roleResolved()).toBe(true));

    expect(await within(verify()).findByText("Verifying needs the write role.")).toBeInTheDocument();
    expect(within(verify()).queryByRole("button", { name: "Verify this Blueprint" })).toBeNull();
  });

  it("is offered to a member whose role nobody resolved, and the floor refuses them cleanly", async () => {
    setMockMemberRole(null);
    const page = renderCodeBuilder(REPORTED);
    await waitFor(() => expect(page.roleResolved()).toBe(true));
    const record = await recordFields("web.search");
    type(record, "searches", "3");
    send();

    const refused = await within(verify()).findByRole("alert");
    expect(refused).toHaveTextContent("Verifying needs the write role, so nothing ran.");
    expect(within(verify()).queryByRole("region", { name: "Verify result" })).toBeNull();
  });

  it("asks for each Measurement with its declared facts, and for a supplier cost where the call reports one", async () => {
    renderCodeBuilder(REPORTED);
    const record = await recordFields("web.search");

    expect(within(record).getByLabelText("searches")).toBeInTheDocument();
    expect(within(record).getByLabelText("Supplier cost, in micros")).toBeInTheDocument();
    expect(within(record).getByText("Not required for a complete cost")).toBeInTheDocument();
    // This Blueprint starts no Subtask and requires no Grouping Field.
    expect(within(record).queryByLabelText("Recorded under")).toBeNull();
    expect(within(verify()).queryByRole("group", { name: "Grouping Field samples" })).toBeNull();
  });

  it("never asks a supplier cost of a call that does not report one", async () => {
    renderCodeBuilder(CALCULATED);
    const record = await recordFields("chat.completion");

    expect(within(record).getByLabelText("input_tokens")).toBeInTheDocument();
    expect(within(record).queryByLabelText("Supplier cost, in micros")).toBeNull();
    expect(within(record).queryByLabelText(READ_OFF_COST.label)).toBeNull();
  });

  // #583 D3: the sample is the cost generated code SENDS, already read and
  // converted, and the form says Verify tests nothing about the reading.
  it("asks a cost read off the response as the micros the code sends, and says what Verify does not test", async () => {
    renderCodeBuilder(READ_OFF);
    const record = await recordFields("grounded.search");

    expect(within(record).getByLabelText(READ_OFF_COST.label)).toBeInTheDocument();
    expect(within(record).queryByLabelText("Supplier cost, in micros")).toBeNull();
    expect(record).toHaveTextContent(
      "Verify supplies the resulting supplier cost in micros to test UBB recording and costing. " +
        "Generated-artifact execution tests the provider-response read and conversion.",
    );
    // Never the raw response: nothing here takes one.
    expect(within(record).queryByLabelText(/response/i)).toBe(within(record).getByLabelText(READ_OFF_COST.label));
  });

  // Owner review of #608: where the Blueprint binds `currency` at run time it
  // is a sample — the resulting code, never the tenant's made up in its place
  // — and a pinned currency, the Blueprint's own, asks for none.
  it("asks a currency read off the response as the code would send it, and only there", async () => {
    renderCodeBuilder(READ_CURRENCY);
    const record = await recordFields("billed.search");

    expect(within(record).getByLabelText(CURRENCY_SAMPLE.label)).toBeInTheDocument();
    expect(record).toHaveTextContent(CURRENCY_SAMPLE.hint);
    // Required, and never filled in for the developer.
    type(record, READ_OFF_COST.label, "1250000");
    send();
    expect(await within(record).findByText(CURRENCY_REQUIRED)).toBeInTheDocument();
    expect(within(verify()).queryByRole("region", { name: "Verify result" })).toBeNull();
  });

  it("asks no currency where the Blueprint pins one", async () => {
    renderCodeBuilder(READ_OFF);
    const record = await recordFields("grounded.search");

    expect(within(record).queryByLabelText(CURRENCY_SAMPLE.label)).toBeNull();
  });
});

describe("Verify, run", () => {
  // The mock answers only the exact request the platform verified, which sent
  // the sample on `provider_response_cost_micros`: a page that sent it on the
  // caller's field would be told it is not in the mock.
  it("verifies a cost read off the response, sent on the field that says so", async () => {
    renderCodeBuilder(READ_OFF);
    const shown = await verifyReadOffCost();

    expect(within(shown).getByRole("status")).toHaveTextContent(/^Verified:/);
    expect(shown).toHaveTextContent((await answer("response-cost")).configuration_fingerprint);
  });

  // The mock answers only the requests the platform verified, each of which
  // sent the currency sample as the event's: a page that dropped it, or sent
  // the tenant's in its place, would be told it is not in the mock.
  it("verifies a currency read off the response with your UBB currency", async () => {
    renderCodeBuilder(READ_CURRENCY);
    const shown = await verifyReadCurrency("usd");

    expect(within(shown).getByRole("status")).toHaveTextContent(/^Verified:/);
    expect(shown).toHaveTextContent((await answer("response-cost-read-currency")).configuration_fingerprint);
  });

  it("shows UBB's own refusal of a foreign currency read off the response, and never says verified", async () => {
    renderCodeBuilder(READ_CURRENCY);
    const shown = await verifyReadCurrency("eur");

    expect(within(shown).getByRole("status")).not.toHaveTextContent(/Verified:/);
    expect(within(shown).getByRole("status")).toHaveTextContent("The run was refused before it finished.");
    expect(within(shown).getByRole("alert")).toHaveTextContent("currency mismatch");
  });

  it("verifies the Blueprint on screen and names where it ran", async () => {
    renderCodeBuilder(REPORTED);
    const shown = await verifyReportedCost();
    const answered = await answer("reported-cost");

    const verdict = within(shown).getByRole("status");
    expect(verdict).toHaveTextContent(
      "Verified: every Event Type and Subtask kind this Blueprint selects was recorded and costed completely.",
    );
    // ⚠ `verified` never reads as a price: the scope is said beside it.
    expect(verdict).toHaveTextContent(VERIFIED_SCOPE);
    const where = shown.querySelector('dl[aria-label="Where it ran"]');
    expect(where).toHaveTextContent("then discarded");
    expect(where).toHaveTextContent(answered.environment.customer_external_id);
    expect(where).toHaveTextContent(formatDate(answered.environment.rules_effective_at));
    expect(where).toHaveTextContent(answered.configuration_fingerprint);
    expect(shown).toHaveTextContent("Every id below names a record that no longer exists");
  });

  it("renders each acknowledgement as given, and a replay's empty totals as expected", async () => {
    renderCodeBuilder(REPORTED);
    const shown = await verifyReportedCost();
    const [record] = (await answer("reported-cost")).records;
    const ack = record?.acknowledgement;
    if (!ack) throw new Error("the platform recorded web.search");
    const recorded = within(shown).getByRole("article", { name: "Record usage · web.search" });
    const acknowledgement = within(recorded).getByRole("group", { name: "Acknowledgement" });
    const replay = within(recorded).getByRole("group", { name: "Replay of the same request" });

    // Statuses exactly as the platform answered them — a price it did not
    // resolve is named, never zeroed, beside a cost it did.
    expect(stat(acknowledgement, "Costing status")).toContain(costingStatusLabel(ack.costing_status));
    expect(stat(acknowledgement, "Price status")).toContain(pricingStatusLabel(ack.pricing_status));
    expect(stat(acknowledgement, "Billed cost")).not.toMatch(/[$£€]\s*-?[\d,]/);
    expect(stat(acknowledgement, "Provider cost")).toContain("$1.25");
    expect(stat(replay, "Task totals")).toContain(REPLAY_TASK_TOTALS);
    expect(recorded).toHaveTextContent("The replay names the same event as the acknowledgement");
  });

  it("renders no credential anywhere", async () => {
    renderCodeBuilder(REPORTED);
    await verifyReportedCost();

    expect(credentialShapeIn(document.body.textContent ?? "")).toBeNull();
  });

  // ⚠ A PARTIAL RUN IS NEVER PRESENTED AS VERIFIED (owner ruling on #599).
  it("says what a partial run left out, and never that it verified the Blueprint", async () => {
    renderCodeBuilder(DIRECT);
    const replies = await recordFields("reply.sent");
    const searches = await recordFields("search.run");
    fireEvent.click(within(searches).getByLabelText("Include in this run"));
    type(replies, "replies", "1");
    send();
    const shown = await result();

    const verdict = within(shown).getByRole("status");
    expect(verdict).toHaveAttribute("data-verified", "false");
    expect(verdict).toHaveTextContent(/^Not verified\./);
    expect(within(verdict).getByRole("list", { name: "Why it is not verified" })).toHaveTextContent(
      "This run left out Event Type search.run",
    );
    expect(shown).not.toHaveTextContent(/Verified:/);
  });

  // ⚠ #537: NO AMOUNT NOBODY KNOWS RENDERS AS A ZERO. The platform answered a
  // cost rate missing: the cost is unresolved, and every total over it is
  // unknown, never `$0.00`.
  it("names a missing Cost Rate as the gap, and draws no zero for what nobody knows", async () => {
    renderCodeBuilder(CALCULATED);
    const record = await recordFields("chat.completion");
    type(await within(verify()).findByRole("group", { name: "Grouping Field samples" }), "environment", "staging");
    type(record, "input_tokens", "1200");
    type(record, "output_tokens", "300");
    type(record, "searches", "2");
    send();
    const shown = await result();

    const recorded = within(shown).getByRole("article", { name: "Record usage · chat.completion" });
    expect(within(recorded).getByText("Incomplete")).toBeInTheDocument();
    const acknowledgement = within(recorded).getByRole("group", { name: "Acknowledgement" });
    expect(stat(acknowledgement, "Missing input")).toContain(unresolvedReasonLabel("cost_rate_missing"));
    const work = within(shown).getByRole("article", { name: /report_generation/ });
    expect(stat(work, "Total provider cost")).toContain(UNKNOWN_TOTAL);
    expect(shown.textContent).not.toMatch(/\$0\.00(?!\d)/);
  });

  it("asks a Subtask kind's Grouping Field only once a record is placed under it, and sends nothing without it", async () => {
    const page = renderCodeBuilder(SUBTASKS);
    const record = await recordFields("gemini.generate");
    const samples = () => within(verify()).getByRole("group", { name: "Grouping Field samples" });
    expect(within(samples()).getByLabelText("environment")).toBeInTheDocument();
    expect(within(samples()).queryByLabelText("phase")).toBeNull();

    fireEvent.change(within(record).getByLabelText("Recorded under"), { target: { value: "summarise" } });
    expect(await within(samples()).findByLabelText("phase")).toBeInTheDocument();
    type(samples(), "environment", "staging");
    type(record, "prompt_tokens", "900");
    type(record, "candidate_tokens", "250");
    send();

    // The phase sample is missing: refused here, before anything is sent.
    expect(await within(samples()).findByText(GROUPING_FIELD_REQUIRED)).toBeInTheDocument();
    expect(within(verify()).queryByRole("region", { name: "Verify result" })).toBeNull();

    type(samples(), "phase", "draft");
    send();
    const shown = await result();
    expect(within(shown).getByRole("article", { name: "Subtask · summarise" })).toBeInTheDocument();
    expect(
      within(shown).getByRole("article", { name: "Record usage · gemini.generate · under summarise" }),
    ).toBeInTheDocument();

    // ⚠ SAMPLES ARE NOT URL STATE (§12): the address never carried one.
    expect(page.current()).toEqual(SUBTASKS);
    expect(JSON.stringify(page.searches)).not.toMatch(/staging|draft|900|250/);
  });

  it("says a request the platform never verified is not in the mock", async () => {
    renderCodeBuilder(REPORTED);
    const record = await recordFields("web.search");
    type(record, "searches", "4");
    send();

    // Mock mode's own answer, shown as the failure it is (as the Blueprint
    // stage shows its "Not in the mock") rather than as a platform refusal.
    expect(await within(verify()).findByText("Couldn't verify the Blueprint")).toBeInTheDocument();
    expect(verify()).toHaveTextContent("the platform verified no request like this one");
    expect(within(verify()).queryByRole("alert")).toBeNull();
  });
});

describe("a result and the Blueprint it ran against", () => {
  // ⚠ A RESULT BELONGS TO ITS FINGERPRINT. The same kind of work and Event
  // Type resolved for the other target is another stored Blueprint; the last
  // result says so, cause-neutrally, and is never shown as the current one's.
  it("is about a different Blueprint once the page resolves another, and current again on return", async () => {
    renderCodeBuilder(REPORTED);
    await verifyReportedCost();
    const python = await loadBlueprintFixture("reported-cost");
    const shell = await loadBlueprintFixture("shell-reported-cost");

    fireEvent.click(within(stage("Configure")).getByRole("radio", { name: /Shell/ }));
    // While the new selection resolves, the Blueprint on screen is the last
    // one's, and nothing is sent for it.
    expect(within(verify()).getByRole("button", { name: "Verify this Blueprint" })).toBeDisabled();

    const stale = await within(verify()).findByText(STALE_RESULT_WARNING);
    expect(stale.parentElement).toHaveTextContent(python.configuration_fingerprint ?? "");
    expect(stale.parentElement).toHaveTextContent(shell.configuration_fingerprint ?? "");
    expect(stale.parentElement).not.toHaveTextContent(/configuration|selection|changed/i);
    expect(within(verify()).queryByRole("region", { name: "Verify result" })).toBeNull();
    expect(verify()).not.toHaveTextContent(/Verified:/);

    fireEvent.click(within(stage("Configure")).getByRole("radio", { name: "Python SDK" }));
    expect(await within(verify()).findByRole("region", { name: "Verify result" })).toHaveTextContent(/Verified:/);
    // It is current again because the samples it ran with came back with it.
    const record = await recordFields("web.search");
    expect(within(record).getByLabelText("searches")).toHaveValue("3");
    expect(within(record).getByLabelText("Supplier cost, in micros")).toHaveValue("1250000");
  });

  it("says Verify proves the Blueprint on screen, not files taken from another", async () => {
    const other = await loadBlueprintFixture("calculated-cost");
    renderCodeBuilder({ ...REPORTED, held: other.configuration_fingerprint ?? undefined });
    await recordFields("web.search");

    const note = verify().querySelector("[data-held-differs]");
    expect(note).toHaveTextContent("so a result here says nothing about them");
    expect(note).toHaveTextContent(other.configuration_fingerprint ?? "");
  });
});

// ⚠ A RESULT IS EVIDENCE ABOUT THE EXACT REQUEST THAT PRODUCED IT (owner review
// of #601). The fingerprint names the configuration, not the samples, and the
// samples change what Verify observes: so an edit that changes the request
// clears the result, and it does not come back.
describe("a result and the samples it ran with", () => {
  const isGone = () =>
    waitFor(() => expect(within(verify()).queryByRole("region", { name: "Verify result" })).toBeNull());

  // The owner's case, on the Blueprint whose run needs a Grouping Field.
  it("clears the result once a Grouping Field sample is edited", async () => {
    const page = renderCodeBuilder(CALCULATED);
    const record = await recordFields("chat.completion");
    const samples = await within(verify()).findByRole("group", { name: "Grouping Field samples" });
    type(samples, "environment", "staging");
    type(record, "input_tokens", "1200");
    type(record, "output_tokens", "300");
    type(record, "searches", "2");
    send();
    await result();

    type(samples, "environment", "production");

    await isGone();
    expect(page.current()).toEqual(CALCULATED);
  });

  it.each<[string, (record: HTMLElement) => void]>([
    ["a Measurement sample", (record) => type(record, "searches", "4")],
    ["the supplier cost", (record) => type(record, "Supplier cost, in micros", "1250001")],
    ["the Event Type left out", (record) => fireEvent.click(within(record).getByLabelText("Include in this run"))],
  ])("clears a Verified result once %s changes", async (_edit, edit) => {
    renderCodeBuilder(REPORTED);
    await verifyReportedCost();

    edit(await recordFields("web.search"));

    await isGone();
    expect(verify()).not.toHaveTextContent(/Verified:/);
  });

  // #583 D3: the cost read off the response is part of the request, so a
  // green result cannot survive its edit — as ruled for every sample on #581.
  it("clears a Verified result once the cost read off the response changes", async () => {
    renderCodeBuilder(READ_OFF);
    await verifyReadOffCost();

    type(await recordFields("grounded.search"), READ_OFF_COST.label, "4201");

    await isGone();
    expect(verify()).not.toHaveTextContent(/Verified:/);
  });

  // The currency sample is part of the request too (owner review of #608).
  it("clears a Verified result once the currency read off the response changes", async () => {
    renderCodeBuilder(READ_CURRENCY);
    await verifyReadCurrency("usd");

    type(await recordFields("billed.search"), CURRENCY_SAMPLE.label, "eur");

    await isGone();
    expect(verify()).not.toHaveTextContent(/Verified:/);
  });

  // Clearing, not hiding: putting the old value back is a new request, which
  // has not been verified, whatever an earlier one said.
  it("does not bring a cleared result back when the edit is undone", async () => {
    renderCodeBuilder(REPORTED);
    await verifyReportedCost();
    const record = await recordFields("web.search");

    type(record, "searches", "4");
    await isGone();
    type(record, "searches", "3");

    expect(within(verify()).queryByRole("region", { name: "Verify result" })).toBeNull();
  });

  it("clears a refusal the same way", async () => {
    renderCodeBuilder(REPORTED);
    const record = await recordFields("web.search");
    type(record, "searches", "4");
    send();
    expect(await within(verify()).findByText("Couldn't verify the Blueprint")).toBeInTheDocument();

    type(record, "searches", "5");

    await waitFor(() => expect(within(verify()).queryByText("Couldn't verify the Blueprint")).toBeNull());
  });

  // The request is the canonical one: a sample is sent trimmed, so space
  // around it changes nothing that was sent.
  it("keeps the result for an edit that leaves the request as it was", async () => {
    renderCodeBuilder(REPORTED);
    await verifyReportedCost();

    type(await recordFields("web.search"), "searches", " 3 ");

    expect(within(verify()).getByRole("region", { name: "Verify result" })).toHaveTextContent(/Verified:/);
  });

  it("locks the samples while a run is in flight, so its answer is about what is on screen", async () => {
    renderCodeBuilder(REPORTED);
    const record = await recordFields("web.search");
    type(record, "searches", "3");
    type(record, "Supplier cost, in micros", "1250000");
    send();

    await waitFor(() => expect(within(record).getByLabelText("searches")).toBeDisabled());
    await result();
    expect(within(record).getByLabelText("searches")).toBeEnabled();
  });
});
