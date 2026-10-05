// The Verify stage's refusals, rendered from what the platform refused with
// (#581; amendment §3).
//
// A page never provokes these: it offers Verify only for a stored, complete
// Blueprint, asks for every required sample, and claims only the Event Types
// the Blueprint records. So the provider is stubbed — the
// `features/events/components/event-receipt-price.test.tsx` shape — and each
// stub answers with a problem body, or a run, THE PLATFORM WROTE
// (`api/verifications/`). Nothing here is a refusal somebody imagined.
//
// ⚠ EVERY ONE IS A PRECONDITION, NOT A MAPPING FAILURE: each says nothing ran
// and why, and none falls through to the console's generic error card.

import { useQuery } from "@tanstack/react-query";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { toApiProblem } from "@/api/problem";

import { loadBlueprintFixture } from "../api/mock-blueprints";
import { loadVerificationFixture } from "../api/mock-verifications";
import { taskOutcomeLabel } from "../lib/code-builder-words";
import { renderInRouter } from "../test-utils";
import { VerifyStage } from "./verify-stage";

const verifyBlueprint = vi.hoisted(() => vi.fn());

vi.mock("../api/provider", () => ({
  // Only what this stage asks for: the page's Blueprint comes from the harness.
  developersApi: { verifyBlueprint },
}));

const resolutions = vi.fn();

/** The page's one Blueprint query, answered with the platform's `calculated-cost`. */
function Harness() {
  const query = useQuery({
    queryKey: ["code-builder", "blueprints", "harness"],
    queryFn: () => {
      resolutions();
      return loadBlueprintFixture("calculated-cost");
    },
  });
  return <VerifyStage query={query} held={undefined} />;
}

async function refusedWith(name: string) {
  const fixture = await loadVerificationFixture(name);
  if (fixture.kind !== "refused") throw new Error(`${name} is a refusal`);
  verifyBlueprint.mockImplementation(async () => {
    throw toApiProblem(structuredClone(fixture.problem));
  });
  return fixture.problem;
}

/** Send a request the form accepts; the stub decides the answer. */
async function sendValidSamples(): Promise<HTMLElement> {
  renderInRouter(<Harness />);
  const record = await screen.findByRole("group", { name: "Record usage · chat.completion" });
  const samples = screen.getByRole("group", { name: "Grouping Field samples" });
  fireEvent.change(within(samples).getByLabelText("environment"), { target: { value: "staging" } });
  fireEvent.change(within(record).getByLabelText("input_tokens"), { target: { value: "1200" } });
  fireEvent.click(screen.getByRole("button", { name: "Verify this Blueprint" }));
  await waitFor(() => expect(verifyBlueprint).toHaveBeenCalledTimes(1));
  return screen.findByRole("alert");
}

beforeEach(() => {
  verifyBlueprint.mockReset();
  resolutions.mockReset();
});

describe("a refusal before anything ran", () => {
  it("says a fingerprint no longer stored can come back only by resolving identically", async () => {
    await refusedWith("not-found");
    const refused = await sendValidSamples();

    expect(refused).toHaveTextContent("This Blueprint is not stored any more, so nothing ran.");
    expect(refused).toHaveTextContent("kept for 30 days after it was last resolved");
    expect(refused).toHaveTextContent("only if your configuration still resolves to exactly this Blueprint");
    expect(refused).toHaveTextContent("otherwise generate the files again");
    expect(resolutions).toHaveBeenCalledTimes(1);

    fireEvent.click(within(refused).getByRole("button", { name: "Resolve again" }));
    await waitFor(() => expect(resolutions).toHaveBeenCalledTimes(2));
  });

  it("names each Event Type the stored Blueprint does not publish", async () => {
    const problem = await refusedWith("event-type-not-available");
    const refused = await sendValidSamples();

    expect(refused).toHaveTextContent("does not publish every Event Type this run claims, so nothing ran");
    const unavailable = within(refused).getByRole("list", { name: "Not available" });
    expect(within(unavailable).getAllByRole("listitem").map((item) => item.textContent)).toEqual(
      problem["event_types"],
    );
  });

  it("says a stored Blueprint that is not complete cannot be verified, in the platform's words", async () => {
    const problem = await refusedWith("blocked");
    const refused = await sendValidSamples();

    expect(refused).toHaveTextContent("The stored Blueprint is not complete, so it cannot be verified and nothing ran.");
    expect(refused).toHaveTextContent(String(problem["detail"]));
  });

  it("says a request refused before the run was refused, in the platform's words", async () => {
    const problem = await refusedWith("missing-grouping-field-sample");
    const refused = await sendValidSamples();

    expect(refused).toHaveTextContent("The request was refused before anything ran.");
    expect(refused).toHaveTextContent(String(problem["detail"]));
  });

  it.each(["not-found", "event-type-not-available", "blocked", "missing-grouping-field-sample"])(
    "renders %s as a precondition and never as a failure to verify",
    async (name) => {
      await refusedWith(name);
      await sendValidSamples();

      expect(screen.queryByText("Couldn't verify the Blueprint")).toBeNull();
      expect(screen.queryByRole("region", { name: "Verify result" })).toBeNull();
    },
  );
});

describe("a verdict the answer contradicts", () => {
  // ⚠ ASSEMBLED, AND SAYS SO: no platform answer contradicts itself, so this
  // takes the platform's partial run and sets its `verified` true. The page
  // must still not say "verified" — the whole-Blueprint scope is read off the
  // answer's own lists, not off one field.
  it("is never presented as verified over a run that left part of the Blueprint out", async () => {
    const fixture = await loadVerificationFixture("direct-task-events-partial");
    if (fixture.kind !== "answered") throw new Error("the platform answered this run");
    const blueprint = await loadBlueprintFixture("calculated-cost");
    verifyBlueprint.mockResolvedValue({
      ...structuredClone(fixture.answer),
      configuration_fingerprint: blueprint.configuration_fingerprint,
      verified: true,
    });

    renderInRouter(<Harness />);
    const record = await screen.findByRole("group", { name: "Record usage · chat.completion" });
    const samples = screen.getByRole("group", { name: "Grouping Field samples" });
    fireEvent.change(within(samples).getByLabelText("environment"), { target: { value: "staging" } });
    fireEvent.change(within(record).getByLabelText("input_tokens"), { target: { value: "1200" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify this Blueprint" }));
    const shown = await screen.findByRole("region", { name: "Verify result" });

    expect(within(shown).getByRole("status")).toHaveAttribute("data-verified", "false");
    expect(shown).not.toHaveTextContent(/Verified:/);
  });
});

describe("a refusal inside the run", () => {
  // The run stopped at the recording the platform refused; what ran before it
  // is still the answer, rendered as given, after the refusal.
  it("is rendered first, beside what had already run", async () => {
    const fixture = await loadVerificationFixture("calculated-cost-refused-recording");
    if (fixture.kind !== "answered") throw new Error("the platform answered this run");
    verifyBlueprint.mockResolvedValue(structuredClone(fixture.answer));
    const refusal = fixture.answer.refusal;
    if (!refusal) throw new Error("the platform refused a call of this run");

    const refused = await sendValidSamples();
    const shown = screen.getByRole("region", { name: "Verify result" });

    expect(refused).toHaveTextContent(`The run stopped at its first refusal, at ${refusal.operation_id}.`);
    expect(refused).toHaveTextContent(refusal.problem.code);
    const work = within(shown).getByText("The work it started");
    expect(refused.compareDocumentPosition(work) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(shown).getByRole("status")).toHaveTextContent("The run was refused before it finished.");
    expect(within(shown).getByText("Not recorded: the run stopped before it.")).toBeInTheDocument();
    const closed = fixture.answer.task.close;
    if (!closed) throw new Error("the platform closed the work it started");
    expect(within(shown).getByRole("article", { name: /report_generation/ })).toHaveTextContent(
      taskOutcomeLabel(closed.outcome),
    );
  });
});
