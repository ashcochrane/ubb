import { describe, expect, it } from "vitest";

import { TENANT_PRODUCT_VALUES } from "@/lib/vocabulary";

import { navSections, visibleNavSections } from "./nav-config";

function titles(products: readonly string[] | undefined): string[] {
  return visibleNavSections(products).flatMap((section) =>
    section.items.map((item) => item.title),
  );
}

/**
 * The Tasks tab is UNGATED and sits beside Events (#423, spec §25 Q6).
 *
 * Work is a kernel concept no product owns, so what a tenant's business sells
 * is visible to every tenant rather than only to billing ones. The claim is
 * held two ways: structurally (the entry declares no product) and through the
 * same filter the shell renders with, over every product set a tenant can
 * have — including none, which is also what the config looks like before it
 * has loaded.
 */
describe("the Tasks tab", () => {
  it("declares no product flag and sits beside Events in the ungated group", () => {
    const ungated = navSections.find((section) =>
      section.items.some((item) => item.title === "Events"),
    );
    expect(ungated).toBeDefined();
    expect(ungated?.label).toBeUndefined();

    const items = ungated?.items ?? [];
    const events = items.findIndex((item) => item.title === "Events");
    const tasks = items.findIndex((item) => item.title === "Tasks");
    expect(tasks).toBe(events + 1);
    expect(items[tasks]?.url).toBe("/tasks");
    expect(items[tasks]?.product).toBeUndefined();
  });

  it("is visible for every single-product tenant, an empty product list, and a config still loading", () => {
    for (const product of TENANT_PRODUCT_VALUES) {
      expect(titles([product])).toContain("Tasks");
    }
    expect(titles([])).toContain("Tasks");
    expect(titles(undefined)).toContain("Tasks");
  });

  it("is filtered by a mechanism that really hides gated tabs", () => {
    // A control on the filter itself: were it a no-op, the case above would
    // pass over a tab that only happened to be visible. Billing gates on the
    // billing product, so a metering-only product list must lose it — and
    // keep Tasks in the same breath.
    const meteringOnly = titles(["metering"]);
    expect(meteringOnly).not.toContain("Billing");
    expect(meteringOnly).not.toContain("Plans");
    expect(meteringOnly).toContain("Tasks");
    expect(meteringOnly).toContain("Events");
  });
});
