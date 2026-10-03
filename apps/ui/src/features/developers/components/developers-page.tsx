// /developers — API keys, the sandbox, the way into the Code Builder, and the
// send-test-event console. Thin composition; each section owns its own data
// and states.
//
// The API-basics card that sat beside the sandbox is gone (#579): what it
// taught is the Code Builder's onboarding state now, generated from the same
// Blueprint as the code, so the console no longer keeps a second, hand-written
// integration example that could drift from it.

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
import { TestEventConsole } from "./test-event-console";

export function DevelopersPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Developers"
        description="API keys, the sandbox, integration code, and a console for trying the metering API."
      />
      <ApiKeysSection />
      <div className="grid gap-6 lg:grid-cols-2">
        <SandboxSection />
        <CodeBuilderCard />
      </div>
      <TestEventConsole />
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
          from what you have declared — the start, every record, and the close.
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
