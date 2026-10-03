// The cases no platform-written Blueprint holds, assembled in the test.
//
// ⚠ A MOCK THAT RETURNS ITS FIXTURE CANNOT SHOW A DEFECT ITS FIXTURES NEVER
// CARRY. No fixture holds a diagnostic about a kind of work with a key, and
// none holds a document the renderer refuses — so the first is rendered from
// a diagnostic built here, and the second from a provider stubbed to answer a
// shape this console does not read.

import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { BlueprintDiagnostic } from "../api/types";
import { renderCodeBuilder, renderInRouter } from "../test-utils";
import { DiagnosticsList } from "./diagnostics-list";

vi.mock("../api/provider", async () => {
  const mock = await vi.importActual<typeof import("../api/mock")>("../api/mock");
  return {
    developersApi: {
      ...mock,
      // A Blueprint of a shape this renderer was not written to read.
      resolveBlueprint: async (...args: Parameters<typeof mock.resolveBlueprint>) => ({
        ...(await mock.resolveBlueprint(...args)),
        schema_version: 2,
      }),
    },
  };
});

function aDiagnostic(overrides: Partial<BlueprintDiagnostic>): BlueprintDiagnostic {
  return {
    severity: "blocking",
    code: "task_type_retired",
    object_kind: "task_type",
    key: "report_generation",
    field: null,
    remediation_request: null,
    ...overrides,
  };
}

describe("a diagnostic about a kind of work", () => {
  it("links to the kind's own page, which the console has", async () => {
    renderInRouter(
      <DiagnosticsList
        diagnostics={[
          aDiagnostic({ code: "task_type_retired", key: "report_generation" }),
          aDiagnostic({ code: "task_type_retired", object_kind: "subtask_type", key: "summarise" }),
        ]}
      />,
    );

    expect(await screen.findByRole("link", { name: "Open the kind of work report_generation" })).toHaveAttribute(
      "href",
      "/tasks/kinds/report_generation",
    );
    expect(screen.getByRole("link", { name: "Open the kind of work summarise" })).toHaveAttribute(
      "href",
      "/tasks/kinds/summarise",
    );
    expect(screen.queryByRole("button", { name: "Copy request" })).toBeNull();
  });

  it("links a kind that is not declared to Tasks, where kinds are declared", async () => {
    renderInRouter(<DiagnosticsList diagnostics={[aDiagnostic({ code: "task_type_not_declared", key: "gone" })]} />);

    expect(await screen.findByRole("link", { name: "Kinds of work and workspace defaults" })).toHaveAttribute(
      "href",
      "/tasks",
    );
  });

  it("asks for a choice where nothing is selected, and links nowhere", async () => {
    renderInRouter(<DiagnosticsList diagnostics={[aDiagnostic({ code: "task_type_not_selected", key: null })]} />);

    expect(await screen.findByText("Choose one under Configure.")).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
  });
});

describe("a Blueprint this console's renderer cannot read", () => {
  it("is shown as refused, in place, and the rest of the page still works", async () => {
    renderCodeBuilder({ task_type: "report_generation", event_types: ["chat.completion"] });
    const generate = await screen.findByRole("region", { name: "Generate" });

    const refusal = await within(generate).findByRole("alert");
    expect(refusal).toHaveTextContent("This console cannot turn this Blueprint into files.");
    expect(refusal).toHaveTextContent("given 2");
    expect(within(generate).queryByRole("button", { name: /Copy/ })).toBeNull();
    // The Blueprint stage is the API's answer, and renders whatever the
    // renderer makes of it.
    await waitFor(() =>
      expect(within(screen.getByRole("region", { name: "Blueprint" })).getAllByRole("article").length).toBeGreaterThan(0),
    );
  });
});
