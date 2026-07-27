// /developers — API keys, sandbox, the send-test-event console, and API
// basics. Thin composition; each section owns its own data and states.

import { PageHeader } from "@/components/shared/page-header";

import { ApiBasicsCard } from "./api-basics-card";
import { ApiKeysSection } from "./api-keys-section";
import { SandboxSection } from "./sandbox-section";
import { TestEventConsole } from "./test-event-console";

export function DevelopersPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Developers"
        description="API keys, the sandbox, and a console for trying the metering API."
      />
      <ApiKeysSection />
      <div className="grid gap-6 lg:grid-cols-2">
        <SandboxSection />
        <ApiBasicsCard />
      </div>
      <TestEventConsole />
    </div>
  );
}
