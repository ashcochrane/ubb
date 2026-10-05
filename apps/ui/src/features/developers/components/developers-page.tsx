// /developers — API keys, the sandbox, and the way into the Code Builder.
// Thin composition; each section owns its own data and states.
//
// The API-basics card that sat beside the sandbox is gone (#579): what it
// taught is the Code Builder's onboarding state now, generated from the same
// Blueprint as the code, so the console no longer keeps a second, hand-written
// integration example that could drift from it. The form that sent one usage
// event by hand is gone too (#581, #559): the Code Builder's Verify stage runs
// the whole lifecycle the generated code makes, with only the fields the
// contract publishes.

import { Link } from "@tanstack/react-router";

import { PageHeader } from "@/components/shared/page-header";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import { ApiKeysSection } from "./api-keys-section";
import { SandboxSection } from "./sandbox-section";

export function DevelopersPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Developers"
        description="API keys, the sandbox, and integration code you can verify before it runs."
      />
      <ApiKeysSection />
      <div className="grid gap-6 lg:grid-cols-2">
        <SandboxSection />
        <CodeBuilderCard />
      </div>
    </div>
  );
}

function CodeBuilderCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Code Builder</CardTitle>
        <CardDescription>
          Integration code for your kinds of work and Event Types, generated
          from what you have declared — the start, every record, and the close
          — and a Verify run of it before it ships.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Link
          to="/developers/code-builder"
          className="text-[13px] font-medium underline underline-offset-2 hover:text-text-primary"
        >
          Open the Code Builder
        </Link>
      </CardContent>
    </Card>
  );
}
