import { ListChecks } from "lucide-react";
import { useState } from "react";

import { DisabledHint } from "@/components/shared/disabled-hint";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useHasRole } from "@/hooks/use-current-role";

import { useKindsOfWork } from "../api/queries";
import { DeclareKindDialog } from "./declare-kind-dialog";
import { KindsTable } from "./kinds-table";
import { TasksNav } from "./tasks-nav";

/**
 * /tasks — the kinds of work this workspace sells.
 *
 * KINDS OF WORK ARE THE FRONT DOOR, AND RUNS ARE A SIBLING (#423, spec §25
 * Q2): a tenant looking here is looking at how their business sells, not at a
 * log of what ran. Runs are the sibling surface (#424), reached from the nav
 * under the header.
 *
 * Declaring is Admin-floored on the server (a declaration decides how usage
 * is costed, which makes it a pricing-rule change), and the button says so
 * rather than hiding.
 */
export function TasksPage() {
  const kinds = useKindsOfWork();
  const standing = kinds.data ?? [];
  const isAdmin = useHasRole("admin");
  const [declareOpen, setDeclareOpen] = useState(false);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Tasks"
        description="The kinds of work your business sells — how each one is sold, and what it may spend."
        actions={
          <DisabledHint disabled={!isAdmin} hint="Requires the Admin role.">
            <Button size="sm" onClick={() => setDeclareOpen(true)} disabled={!isAdmin}>
              Declare a kind of work
            </Button>
          </DisabledHint>
        }
      />
      <TasksNav current="kinds" />

      {kinds.isLoading ? (
        <Card size="sm" className="p-3">
          <div className="space-y-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        </Card>
      ) : kinds.isError ? (
        <ErrorCard
          error={kinds.error}
          onRetry={() => void kinds.refetch()}
          title="Couldn't load your kinds of work"
        />
      ) : standing.length === 0 ? (
        <EmptyState
          icon={ListChecks}
          title="No kinds of work yet"
          description="A kind of work is the unit your business sells — a render, a summary, a whole agent run. Declare one, and every run of it reports here."
          action={
            isAdmin
              ? { label: "Declare a kind of work", onClick: () => setDeclareOpen(true) }
              : undefined
          }
        />
      ) : (
        <KindsTable kinds={standing} />
      )}

      <DeclareKindDialog open={declareOpen} onOpenChange={setDeclareOpen} standing={standing} />
    </div>
  );
}
