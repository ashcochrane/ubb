import { describe, expect, it } from "vitest";

import { resolveLabel } from "@/lib/localisation";
import {
  ACTOR_KIND_KNOWN_VALUES,
  AUDIT_ACTION_VALUES,
  AUDIT_RESOURCE_TYPE_VALUES,
} from "@/lib/vocabulary";

import {
  ACTOR_KIND_LABELS,
  auditActionLabel,
  auditResourceTypeLabel,
} from "./audit-vocabulary";

// The audit feed's words are the catalogue's (R10-W4). The action was split on
// the dot and humanised, and the resource type humanised outright; both were
// the defect ADR-0008 §4.3 names, and both pins below would pass against the
// humaniser for exactly none of their cases.

describe("the audit feed's words", () => {
  it("words an action from the catalogue, not from its spelling", () => {
    expect(auditActionLabel("member.role_changed")).toBe("Member role changed");
    expect(auditActionLabel("connect.started")).toBe("Stripe Connect started");
    expect(auditActionLabel("wallet.withdrawn")).toBe("Withdrawn from wallet");
  });

  it("words a resource type from the catalogue", () => {
    expect(auditResourceTypeLabel("grouping_field_registry")).toBe("Grouping Fields");
    expect(auditResourceTypeLabel("pricing_book_publish")).toBe("Pricing Book change");
  });

  it("renders a token the registry never declared as itself, never title-cased", () => {
    expect(auditActionLabel("config.updated")).toBe("config.updated");
    expect(auditResourceTypeLabel("tenant_config")).toBe("tenant_config");
  });

  it("has a word for every declared action, resource type and known actor kind", () => {
    for (const action of AUDIT_ACTION_VALUES) {
      expect(resolveLabel({}, action).kind).toBe("unfamiliar");
      expect(auditActionLabel(action)).not.toBe(action);
    }
    for (const resourceType of AUDIT_RESOURCE_TYPE_VALUES) {
      expect(auditResourceTypeLabel(resourceType)).not.toBe(resourceType);
    }
    for (const kind of ACTOR_KIND_KNOWN_VALUES) {
      expect(resolveLabel(ACTOR_KIND_LABELS, kind).kind).toBe("labelled");
    }
  });
});
