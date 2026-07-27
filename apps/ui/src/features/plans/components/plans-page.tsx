// /plans — a plan's whole commercial offer (access fee, per-seat fee, and
// markup on metered compute) in one table. Replaces the old two-page split
// (fees on /subscriptions, markup on /pricing).
//
// Gating is inlined here rather than using the shared <ProductGate> — that
// component currently has a broken import (@/lib/labels, a pre-existing gap
// unrelated to this feature; see apps/ui's known lib/ gitignore issue) that
// would poison this page's whole module graph. `useTenantConfig` itself is
// safe: it only imports the `Product` type (erased at build time), never a
// value, from that module.

import { useState } from "react";

import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useTenantConfig } from "@/hooks/use-tenant-config";

import { usePlans } from "../api/queries";
import type { Plan } from "../api/types";
import { PlanFormDialog } from "./plan-form-dialog";
import { PlansTable } from "./plans-table";

export function PlansPage() {
  const config = useTenantConfig();
  const { data, isLoading, error } = usePlans();
  const [dialogPlan, setDialogPlan] = useState<Plan | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  if (config.isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!config.data?.products.includes("billing")) {
    return (
      <div className="mx-auto max-w-md rounded-lg border border-border bg-bg-surface p-8 text-center">
        <h2 className="text-base font-semibold text-text-primary">Billing isn't enabled</h2>
        <p className="mt-2 text-sm text-text-secondary">
          Plans require the billing product for this workspace. Enable it in Settings → Products.
        </p>
      </div>
    );
  }

  function openCreate() {
    setDialogPlan(null);
    setDialogOpen(true);
  }

  function openEdit(plan: Plan) {
    setDialogPlan(plan);
    setDialogOpen(true);
  }

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Plans"
        description="What you sell: an access fee, a per-seat fee, and a markup on metered compute."
        actions={<Button onClick={openCreate}>New plan</Button>}
      />
      <Card size="sm">
        <CardContent>
          {isLoading && <p className="text-sm text-muted-foreground">Loading plans…</p>}
          {error && <p className="text-sm text-destructive">Could not load plans.</p>}
          {data && <PlansTable plans={data.plans} onEdit={openEdit} />}
        </CardContent>
      </Card>
      <PlanFormDialog open={dialogOpen} onOpenChange={setDialogOpen} plan={dialogPlan} />
    </div>
  );
}
