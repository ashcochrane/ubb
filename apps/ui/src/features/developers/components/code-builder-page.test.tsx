// Seam D (#184 spec part 4): the Code Builder page against the mock provider,
// whose Blueprints are the platform's own (`api/mock-blueprints.ts`).

import { focusManager } from "@tanstack/react-query";
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setMockMemberRole } from "@/hooks/use-current-role";
import { formatDate } from "@/lib/format";

import {
  loadBlueprintFixture,
  resetMockConfiguration,
  reviseMockConfiguration,
  THE_REVISION,
} from "../api/mock-blueprints";
import type { CodeBuilderSearch } from "../lib/code-builder-search";
import { diagnosticCodeLabel, objectKindLabel } from "../lib/code-builder-words";
import { renderCodeBuilder } from "../test-utils";

const EXPLICIT_SUBTASKS: CodeBuilderSearch = {
  task_type: "report_generation",
  subtask_types: ["summarise"],
  event_types: ["gemini.generate"],
};
const BLOCKED: CodeBuilderSearch = {
  task_type: "report_generation",
  event_types: ["chat.completion", "draft.only", "web.search"],
};
const COMPLETE: CodeBuilderSearch = { task_type: "report_generation", event_types: ["chat.completion"] };
const SHELL_COMPLETE: CodeBuilderSearch = {
  target: "shell_http",
  task_type: "support_reply",
  event_types: ["reply.sent", "search.run"],
};
const REVISED: CodeBuilderSearch = {
  target: "shell_http",
  task_type: "report_generation",
  event_types: [THE_REVISION.eventType],
};

const stage = (name: string) => screen.getByRole("region", { name });

async function resolved(readiness: RegExp) {
  await waitFor(() => expect(within(stage("Blueprint")).getAllByText(readiness).length).toBeGreaterThan(0));
}

const writeText = vi.fn<(text: string) => Promise<void>>();

beforeEach(() => {
  writeText.mockReset().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
});

afterEach(() => {
  resetMockConfiguration();
  setMockMemberRole("admin");
});

describe("the Code Builder page", () => {
  it("is Configure, Blueprint, Generate and Verify, in that order", async () => {
    renderCodeBuilder(COMPLETE);
    await resolved(/^Complete$/);

    const stages = [...document.querySelectorAll("ol > li > section")];
    expect(stages.map((section) => section.getAttribute("aria-label"))).toEqual([
      "Configure",
      "Blueprint",
      "Generate",
      "Verify",
    ]);
    // Verify is a stage of its own, and nothing else on the page verifies:
    // the one button is in it, and no link anywhere leads to a verifier.
    const verifying = screen.getAllByRole("button", { name: /verif/i });
    expect(verifying.every((button) => stage("Verify").contains(button))).toBe(true);
    expect(screen.queryByRole("link", { name: /verif/i })).toBeNull();
  });
});

describe("Configure", () => {
  it("asks the four questions the request publishes, an admin's switch, and nothing else", async () => {
    renderCodeBuilder();
    const configure = await screen.findByRole("region", { name: "Configure" });
    await waitFor(() => within(configure).getByRole("combobox", { name: "Kind of work" }));
    await waitFor(() => within(configure).getByRole("group", { name: "Event Types" }));
    // Mock mode's member is an admin, so the fifth field is on screen too.
    await within(configure).findByRole("checkbox", { name: "Draft preview — not production-ready" });

    expect(within(configure).getByRole("radio", { name: "Python SDK" })).toBeChecked();
    expect(within(configure).getByRole("radio", { name: "Shell / raw HTTP · requires curl, jq" })).not.toBeChecked();
    // Everything Configure asks, however it asks it: each group by its legend,
    // each control outside a group by its label. The Subtask question is here
    // because this tenant declares a Subtask kind. Never which Measurements to
    // send, and never how to read a supplier's response.
    const questions = [
      ...[...configure.querySelectorAll("legend")].map((legend) => legend.textContent),
      ...[...configure.querySelectorAll("select, input")]
        .filter((control) => control.closest("fieldset") === null)
        .map((control) => {
          const label = control.closest("label");
          return label?.querySelector("span")?.textContent ?? label?.textContent;
        }),
    ];
    expect(questions).toEqual([
      "Target",
      "Subtask kinds it starts itself",
      "Event Types",
      "Kind of work",
      "Draft preview — not production-ready",
    ]);
    expect(within(configure).queryAllByRole("textbox")).toEqual([]);
    expect(within(configure).queryAllByRole("spinbutton")).toEqual([]);
  });

  it("carries every choice into the URL as a declared key", async () => {
    const page = renderCodeBuilder();
    const configure = await screen.findByRole("region", { name: "Configure" });
    const kind = await within(configure).findByRole("combobox", { name: "Kind of work" });

    fireEvent.click(within(configure).getByRole("radio", { name: /Shell/ }));
    fireEvent.change(kind, { target: { value: "report_generation" } });
    fireEvent.click(await within(configure).findByRole("checkbox", { name: /chat\.completion/ }));
    fireEvent.click(await within(configure).findByRole("checkbox", { name: /summarise/ }));

    expect(page.current()).toEqual({
      target: "shell_http",
      task_type: "report_generation",
      event_types: ["chat.completion"],
      subtask_types: ["summarise"],
    });
  });

  it("shows a selected key the tenant no longer offers, rather than dropping it", async () => {
    renderCodeBuilder({ task_type: "gone_kind", event_types: ["gone.event"] });
    const configure = await screen.findByRole("region", { name: "Configure" });

    const kind = await within(configure).findByRole("combobox", { name: "Kind of work" });
    expect(kind).toHaveValue("gone_kind");
    expect(within(kind).getByRole("option", { name: "gone_kind (not declared)" })).toBeInTheDocument();
    expect(await within(configure).findByRole("checkbox", { name: /gone\.event/ })).toBeChecked();
  });
});

describe("the Blueprint stage", () => {
  // ⚠ EVERY INFERRED FACT, WITH ITS DECLARATION — held to the platform-written
  // document rather than to a list here, so a dropped row, a dropped
  // provenance or a dropped revision is a red test whichever fact it is.
  it("shows every token of every call with the declaration it was read from", async () => {
    renderCodeBuilder(EXPLICIT_SUBTASKS);
    await resolved(/^Complete$/);
    const blueprint = await loadBlueprintFixture("explicit-subtasks");
    const calls = within(stage("Blueprint")).getAllByRole("article");

    expect(calls).toHaveLength(blueprint.calls.length);
    blueprint.calls.forEach((call, index) => {
      const article = calls[index];
      if (!article) throw new Error(`no article for call ${index}`);
      const rows = article.querySelectorAll("tr[data-token]");
      expect([...rows].map((row) => row.getAttribute("data-token"))).toEqual(
        call.arguments.map((argument) => argument.name),
      );
      call.arguments.forEach((argument, position) => {
        const declaredBy = rows[position]?.querySelector("[data-provenance]")?.textContent ?? "";
        const provenance = argument.provenance;
        if (provenance == null) {
          expect(declaredBy).toBe("—");
          return;
        }
        expect(declaredBy).toContain(objectKindLabel(provenance.object_kind));
        expect(declaredBy).toContain(provenance.key);
        if (provenance.published_revision != null) {
          expect(declaredBy).toContain(`published revision ${provenance.published_revision}`);
        }
        if (provenance.published_at != null) {
          expect(declaredBy).toContain(formatDate(provenance.published_at));
        }
      });
    });
  });

  it("names the facts a developer needs, in words", async () => {
    renderCodeBuilder(EXPLICIT_SUBTASKS);
    await resolved(/^Complete$/);
    // The VALUE cell of one token's row: the declaration cell names the same
    // keys, so a row-wide query could find either.
    const row = (call: string, token: string) => {
      const article = within(stage("Blueprint")).getByRole("article", { name: call });
      const value = article.querySelector(`tr[data-token="${token}"] td:nth-child(2)`);
      if (!(value instanceof HTMLElement)) throw new Error(`no ${token} under ${call}`);
      return within(value);
    };

    // The kind's frozen pricing mode and its declared ceiling.
    expect(row("Start the work · report_generation", "task_type.pricing_mode").getByText("Event priced")).toBeInTheDocument();
    expect(row("Start the work · report_generation", "task_type.task_cogs_ceiling_micros").getByText("$5.00")).toBeInTheDocument();
    expect(row("Start a Subtask · summarise", "task_type.uncapped").getByText("Uncapped")).toBeInTheDocument();
    // The provider, the costing method, a Measurement's type, unit and flag.
    const record = "Record usage · gemini.generate";
    expect(row(record, "provider").getByText("google")).toBeInTheDocument();
    expect(row(record, "event_type.costing_method").getByText("Calculated from Cost Rates")).toBeInTheDocument();
    expect(row(record, "measurements.candidate_tokens.value_type").getByText("Integer")).toBeInTheDocument();
    expect(row(record, "measurements.candidate_tokens.unit").getByText("Token")).toBeInTheDocument();
    expect(row(record, "measurements.candidate_tokens.required_for_costing").getByText("Required for a complete cost")).toBeInTheDocument();
    // A credential is a variable's name, never a value.
    expect(row(record, "api_key").getByText("UBB_API_KEY")).toBeInTheDocument();
  });

  it("links a fact to the console screen that owns it", async () => {
    renderCodeBuilder(EXPLICIT_SUBTASKS);
    await resolved(/^Complete$/);
    const blueprint = stage("Blueprint");

    expect(within(blueprint).getByRole("link", { name: "Open the kind of work report_generation" })).toHaveAttribute(
      "href",
      "/tasks/kinds/report_generation",
    );
    expect(within(blueprint).getByRole("link", { name: "Open the kind of work summarise" })).toHaveAttribute(
      "href",
      "/tasks/kinds/summarise",
    );
    expect(within(blueprint).getAllByRole("link", { name: "Cost Rates" })[0]).toHaveAttribute("href", "/pricing");
  });

  // That the page CANNOT send one is the feature-wide source check in
  // `developers-feature.test.ts`; this is what the page offers instead.
  it("offers each blocking diagnostic's request to copy, with its reference, and nothing that sends", async () => {
    renderCodeBuilder(BLOCKED);
    await resolved(/^Blocked$/);
    const blocked = await loadBlueprintFixture("blocked");
    const diagnostics = within(stage("Blueprint")).getByRole("list", { name: "Diagnostics" });
    const blocks = [...diagnostics.querySelectorAll<HTMLElement>("[data-remediation]")];

    expect(blocks).toHaveLength(blocked.diagnostics.length);
    for (const diagnostic of blocked.diagnostics) {
      const request = diagnostic.remediation_request;
      if (!request) throw new Error("every diagnostic in this fixture carries a request");
      // Two diagnostics can share an operation; the route names the object.
      const block = blocks.find((candidate) =>
        candidate.textContent?.includes(`${request.method} ${request.route}`),
      );
      if (block === undefined) throw new Error(`no request for ${diagnostic.code}`);
      expect(block).toHaveAttribute("data-remediation", request.operation_id);
      expect(within(block).getByRole("link", { name: `API reference: ${request.operation_id}` })).toHaveAttribute(
        "href",
        expect.stringContaining(`/api/v1/docs#/default/${request.operation_id}`),
      );
      expect(within(diagnostics).getAllByText(diagnosticCodeLabel(diagnostic.code)).length).toBeGreaterThan(0);
      // A copy and a link to read: no control here does anything else.
      expect(within(block).getAllByRole("button").map((button) => button.getAttribute("aria-label"))).toEqual([
        "Copy request",
      ]);
      expect(within(block).getAllByRole("link")).toHaveLength(1);
    }

    const [copy] = within(diagnostics).getAllByRole("button", { name: "Copy request" });
    if (!copy) throw new Error("a request to copy");
    fireEvent.click(copy);
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(writeText.mock.calls[0]?.[0]).toMatch(/^# operation_id = "api_v1_[a-z_]+"\n(PUT|POST|PATCH) \/api\/v1\//);
  });

  it("names what each kind's limits can announce, and where to subscribe", async () => {
    renderCodeBuilder(EXPLICIT_SUBTASKS);
    await resolved(/^Complete$/);
    const announcements = within(stage("Blueprint")).getByRole("region", { name: "When nobody is calling" });

    for (const event of ["task.killed", "task.expired", "subtask.killed", "subtask.expired"]) {
      expect(within(announcements).getByText(event)).toBeInTheDocument();
    }
    expect(within(announcements).getByRole("link", { name: "Webhooks" })).toHaveAttribute("href", "/webhooks");
  });
});

describe("Generate", () => {
  it.each([
    ["a scaffold", {}, /^Scaffold, not ready to run$/],
    ["a blocked Blueprint", BLOCKED, /^Blocked$/],
  ] as const)("says Copy scaffold for %s", async (_name, search, readiness) => {
    renderCodeBuilder(search);
    await resolved(readiness);
    const generate = stage("Generate");

    expect(within(generate).getAllByRole("button", { name: "Copy scaffold" }).length).toBeGreaterThan(0);
    expect(within(generate).queryByRole("button", { name: "Copy integration" })).toBeNull();
  });

  it("says Copy integration only once the verdict is complete", async () => {
    renderCodeBuilder(COMPLETE);
    await resolved(/^Complete$/);
    const generate = stage("Generate");

    expect(within(generate).getAllByRole("button", { name: "Copy integration" }).length).toBeGreaterThan(0);
    expect(within(generate).queryByRole("button", { name: "Copy scaffold" })).toBeNull();
  });

  it("shows the Python files, with an environment that asks for the API's address", async () => {
    renderCodeBuilder(COMPLETE);
    await resolved(/^Complete$/);
    const generate = stage("Generate");

    for (const path of ["ubb_integration.py", ".env.example", "verify_integration.py"]) {
      expect(within(generate).getByRole("article", { name: path })).toBeInTheDocument();
    }
    const environment = within(generate).getByRole("article", { name: ".env.example" });
    expect(environment.querySelector("pre")?.textContent).toMatch(/^UBB_BASE_URL=$/m);
    expect(within(generate).queryByRole("region", { name: "The request each call sends" })).toBeNull();
  });

  it("previews each Shell request beside its call, with no verdict beside it", async () => {
    renderCodeBuilder(SHELL_COMPLETE);
    await resolved(/^Complete$/);
    const blueprint = await loadBlueprintFixture("shell-direct-task-events");
    const previews = within(stage("Generate")).getByRole("region", { name: "The request each call sends" });

    expect(within(previews).getAllByRole("article")).toHaveLength(blueprint.calls.length);
    expect(within(previews).getAllByRole("button", { name: "Copy request preview" })).toHaveLength(blueprint.calls.length);
    expect(within(previews).queryByText(/complete|scaffold|blocked/i)).toBeNull();
    expect(within(previews).queryByRole("button", { name: /Copy (scaffold|integration)/ })).toBeNull();
  });

  it("records the fingerprint of the files taken, and nothing for a preview", async () => {
    const page = renderCodeBuilder(SHELL_COMPLETE);
    await resolved(/^Complete$/);
    const blueprint = await loadBlueprintFixture("shell-direct-task-events");
    const generate = stage("Generate");

    fireEvent.click(within(previews(generate)).getAllByRole("button", { name: "Copy request preview" })[0] as HTMLElement);
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(page.current().held).toBeUndefined();

    const module = within(generate).getByRole("article", { name: "ubb_integration.sh" });
    fireEvent.click(within(module).getByRole("button", { name: "Copy integration" }));
    await waitFor(() => expect(page.current().held).toBe(blueprint.configuration_fingerprint));
    expect(await within(generate).findByText(/These are the files you took/)).toBeInTheDocument();
  });

  it("downloads a file under its own name, as the files taken", async () => {
    // jsdom has neither; both are put back exactly as they were.
    const createObjectURL = vi.fn(() => "blob:mock");
    const revokeObjectURL = vi.fn();
    const saved = {
      create: Object.getOwnPropertyDescriptor(URL, "createObjectURL"),
      revoke: Object.getOwnPropertyDescriptor(URL, "revokeObjectURL"),
    };
    Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURL, configurable: true });
    const clicked: string[] = [];
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        clicked.push(this.download);
      });
    try {
      const page = renderCodeBuilder(COMPLETE);
      await resolved(/^Complete$/);
      const blueprint = await loadBlueprintFixture("calculated-cost");
      const callSite = within(stage("Generate"))
        .getAllByRole("article")
        .find((article) => article.getAttribute("aria-label")?.startsWith("call_sites/"));
      if (!callSite) throw new Error("a call-site block");

      fireEvent.click(within(callSite).getByRole("button", { name: "Download" }));

      expect(clicked).toEqual([callSite.getAttribute("aria-label")?.replace("call_sites/", "")]);
      expect(createObjectURL).toHaveBeenCalledTimes(1);
      await waitFor(() => expect(page.current().held).toBe(blueprint.configuration_fingerprint));
      await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock"));
    } finally {
      click.mockRestore();
      for (const [name, descriptor] of [
        ["createObjectURL", saved.create],
        ["revokeObjectURL", saved.revoke],
      ] as const) {
        if (descriptor) Object.defineProperty(URL, name, descriptor);
        else Reflect.deleteProperty(URL, name);
      }
    }
  });

  // ⚠ THE ROUND TRIP'S OTHER HALF. The configuration changes somewhere else;
  // coming back to the page resolves again, and the files already taken say
  // they are stale because their fingerprint is not the one resolved now.
  it("refreshes the Blueprint and the code when the configuration changes, and shows held files stale", async () => {
    const page = renderCodeBuilder(REVISED);
    await resolved(/^Blocked$/);
    const before = await loadBlueprintFixture(THE_REVISION.before);
    const after = await loadBlueprintFixture(THE_REVISION.after);
    const generate = stage("Generate");
    fireEvent.click(
      within(within(generate).getByRole("article", { name: "ubb_integration.sh" })).getByRole("button", {
        name: "Copy scaffold",
      }),
    );
    await waitFor(() => expect(page.current().held).toBe(before.configuration_fingerprint));
    const moduleBefore = writeText.mock.calls[0]?.[0];

    reviseMockConfiguration();
    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });

    await resolved(/^Complete$/);
    const stale = await within(stage("Generate")).findByText("The files you took are stale for the current Blueprint.");
    expect(stale.parentElement).toHaveTextContent(before.configuration_fingerprint ?? "");
    expect(stale.parentElement).toHaveTextContent(after.configuration_fingerprint ?? "");
    // ⚠ CAUSE-NEUTRAL (owner ruling on #600): here the configuration did
    // change, but a mismatch can as well be the developer's own new selection,
    // and the page knows only that two fingerprints differ.
    expect(stale.parentElement).not.toHaveTextContent(/configuration|selection|changed/i);
    const module = within(stage("Generate")).getByRole("article", { name: "ubb_integration.sh" });
    expect(module.querySelector("pre")?.textContent).not.toBe(moduleBefore);
    expect(within(module).getByRole("button", { name: "Copy integration" })).toBeInTheDocument();
    // The selection itself survived the change untouched.
    expect(page.current()).toMatchObject(REVISED);
  });
});

function previews(generate: HTMLElement): HTMLElement {
  return within(generate).getByRole("region", { name: "The request each call sends" });
}

describe("the draft preview", () => {
  it("is offered to an admin, labelled, and shows no fingerprint anywhere", async () => {
    // Files taken earlier, so the page has a fingerprint it could show.
    const published = await loadBlueprintFixture("calculated-cost");
    const page = renderCodeBuilder({ ...COMPLETE, held: published.configuration_fingerprint ?? undefined });
    await resolved(/^Complete$/);
    const toggle = await within(stage("Configure")).findByRole("checkbox", {
      name: "Draft preview — not production-ready",
    });

    fireEvent.click(toggle);

    expect(page.current().draft_preview).toBe(true);
    expect(await within(stage("Blueprint")).findByText("None — a draft preview is stored nowhere")).toBeInTheDocument();
    expect(await within(stage("Generate")).findByText(/This is a draft preview/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/sha256:/);
    // A draft preview can never be verified (#567 point 3): the stage says so
    // and offers nothing.
    expect(within(stage("Verify")).getByRole("note")).toHaveTextContent(
      "A draft preview cannot be verified",
    );
    expect(screen.queryByRole("button", { name: /verif/i })).toBeNull();
  });

  // ⚠ ABSENT BECAUSE OF THE ROLE, NOT BECAUSE IT HAS NOT ARRIVED YET: each
  // case waits for the role to resolve before it looks.
  it("is offered to nobody below admin", async () => {
    setMockMemberRole("write");
    const page = renderCodeBuilder(COMPLETE);
    await resolved(/^Complete$/);
    await waitFor(() => expect(page.roleResolved()).toBe(true));

    expect(within(stage("Configure")).queryByRole("checkbox", { name: /Draft preview/ })).toBeNull();
  });

  it("is offered to nobody whose role could not be resolved", async () => {
    setMockMemberRole(null);
    const page = renderCodeBuilder(COMPLETE);
    await resolved(/^Complete$/);
    await waitFor(() => expect(page.roleResolved()).toBe(true));

    expect(within(stage("Configure")).queryByRole("checkbox", { name: /Draft preview/ })).toBeNull();
  });

  it("is refused below admin, and the page offers the published Blueprint instead", async () => {
    setMockMemberRole("read");
    const page = renderCodeBuilder({ ...COMPLETE, draft_preview: true });

    const back = await within(await screen.findByRole("region", { name: "Blueprint" })).findByRole("button", {
      name: "Show the published Blueprint",
    });
    expect(within(stage("Blueprint")).getByText("A draft preview needs the admin role.")).toBeInTheDocument();
    fireEvent.click(back);

    expect(page.current().draft_preview).toBeUndefined();
    await resolved(/^Complete$/);
  });
});

describe("where an integration starts", () => {
  it("teaches the lifecycle as a scaffold, and names what must be configured", async () => {
    renderCodeBuilder();
    await resolved(/^Scaffold, not ready to run$/);
    const start = stage("Start here");

    expect(within(start).getByText("Scaffold, not ready to run")).toBeInTheDocument();
    for (const part of ["Authenticate.", "Start the work.", "Record usage.", "Close the work."]) {
      expect(within(start).getByText(part)).toBeInTheDocument();
    }
    expect(within(start).getByText("UBB_API_KEY")).toBeInTheDocument();
    expect(within(start).getByText("UBB_BASE_URL")).toBeInTheDocument();
    const missing = within(start).getByRole("list", { name: "What must be configured" });
    expect(within(missing).getByText(diagnosticCodeLabel("task_type_not_selected"))).toBeInTheDocument();
    expect(within(missing).getByText(diagnosticCodeLabel("event_type_not_selected"))).toBeInTheDocument();
  });

  it("is gone once the Blueprint is more than a scaffold", async () => {
    renderCodeBuilder(COMPLETE);
    await resolved(/^Complete$/);

    expect(screen.queryByRole("region", { name: "Start here" })).toBeNull();
  });
});
