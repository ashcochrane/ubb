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
  diagnosticCodeLabel,
  STALE_RESULT_WARNING,
  VERIFIED_SCOPE,
} from "../lib/code-builder-words";
import { GROUPING_FIELD_REQUIRED } from "../lib/verification";
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
  });
});

describe("Verify, run", () => {
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

    expect(await within(verify()).findByRole("alert")).toHaveTextContent("Not in the mock");
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
