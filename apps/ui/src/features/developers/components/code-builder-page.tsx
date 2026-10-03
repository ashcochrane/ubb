// /developers/code-builder — Configure → Blueprint → Generate (#579).
//
// A route under Developers, not a thirteenth nav entry (§12). The page holds
// no state of its own: its selections are the URL's (`lib/code-builder-search`),
// so a deep link, the browser's history and the configuration round trip all
// return to the same builder. Strictly read-and-generate: nothing on this page
// creates, edits or publishes configuration, even for an admin (#156 §9).
//
// THE STAGES ARE `CODE_BUILDER_STAGES`, rendered in order from the two records
// below. #581 adds Verify by appending its id there; `tsc` then asks for its
// title and its body here, and nothing else on the page moves.

import { Link } from "@tanstack/react-router";
import { useMemo, type ReactNode } from "react";

import { PageHeader } from "@/components/shared/page-header";
import { ProductGate } from "@/components/shared/product-gate";
import { Section } from "@/components/shared/section";
import { roleIsKnownToMeet, useCurrentRole } from "@/hooks/use-current-role";

import { useBlueprint } from "../api/queries";
import { CODE_BUILDER_STAGES, type CodeBuilderStage } from "../lib/blueprint";
import { selectionOf, type CodeBuilderSearch } from "../lib/code-builder-search";
import { BlueprintStage } from "./blueprint-stage";
import { ConfigureStage } from "./configure-stage";
import { GenerateStage } from "./generate-stage";
import { LifecycleScaffold } from "./lifecycle-scaffold";

const STAGES: Readonly<Record<CodeBuilderStage, { title: string; description: string }>> = {
  configure: {
    title: "Configure",
    description: "What the integration does. Everything else is read from what you have declared.",
  },
  blueprint: {
    title: "Blueprint",
    description:
      "Every call the code makes, each value it sends, and the declaration each value was read from.",
  },
  generate: {
    title: "Generate",
    description: "The files, written in your browser from the Blueprint above.",
  },
};

export interface CodeBuilderPageProps {
  search: CodeBuilderSearch;
  onSearchChange: (next: CodeBuilderSearch) => void;
}

export function CodeBuilderPage(props: CodeBuilderPageProps) {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Code Builder"
        description="Integration code for your kinds of work and Event Types, generated from what you have declared."
        actions={
          <Link to="/developers" className="text-[13px] underline underline-offset-2">
            Developers
          </Link>
        }
      />
      {/* The Blueprint routes are metering's. */}
      <ProductGate product="metering">
        <CodeBuilder {...props} />
      </ProductGate>
    </div>
  );
}

function CodeBuilder({ search, onSearchChange }: CodeBuilderPageProps) {
  const selection = useMemo(() => selectionOf(search), [search]);
  const blueprint = useBlueprint(selection);
  const { role } = useCurrentRole();

  const bodies: Readonly<Record<CodeBuilderStage, ReactNode>> = {
    configure: (
      <ConfigureStage
        search={search}
        onSearchChange={onSearchChange}
        offersDraftPreview={roleIsKnownToMeet(role, "admin")}
      />
    ),
    blueprint: (
      <BlueprintStage
        query={blueprint}
        draftRequested={selection.draft_preview === true}
        onLeaveDraftPreview={() => onSearchChange({ ...search, draft_preview: undefined })}
      />
    ),
    generate: (
      <GenerateStage
        query={blueprint}
        held={search.held}
        onTaken={(fingerprint) => {
          if (fingerprint !== search.held) onSearchChange({ ...search, held: fingerprint });
        }}
      />
    ),
  };

  return (
    <div className="space-y-6">
      {blueprint.data?.readiness === "scaffold" && <LifecycleScaffold blueprint={blueprint.data} />}
      <ol className="space-y-6">
        {CODE_BUILDER_STAGES.map((stage) => (
          <li key={stage}>
            <Section title={STAGES[stage].title} description={STAGES[stage].description}>
              {bodies[stage]}
            </Section>
          </li>
        ))}
      </ol>
    </div>
  );
}
