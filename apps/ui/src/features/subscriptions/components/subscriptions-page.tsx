// Tenant-level subscriptions surface: plans + Stripe sync. Per-customer
// subscription actions (subscribe, seats, pause, cancel) live on the customer
// pages. Honest about the contract gap: there is no plans-list endpoint.

import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";

import { PageHeader } from "@/components/shared/page-header";
import { ProductGate } from "@/components/shared/product-gate";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

import { ConnectStatusSection } from "./connect-status-section";
import { CreatePlanCard } from "./create-plan-card";
import { EditPlanCard } from "./edit-plan-card";
import { StripeSyncCard } from "./stripe-sync-card";

export function SubscriptionsPage() {
  return (
    <ProductGate product="subscriptions">
      <div className="flex flex-col gap-4">
        <PageHeader
          title="Subscriptions"
          description="Billing plans and the Stripe subscription mirror."
        />

        <Card size="sm">
          <CardHeader>
            <CardTitle>What lives here</CardTitle>
            <CardDescription>
              Stripe owns the subscription lifecycle — invoicing, payment collection, dunning,
              trials, and coupons. UBB defines your billing plans (a flat access fee plus an
              optional per-seat fee), provisions them as Stripe Prices, keeps seat counts in sync,
              and mirrors subscription state back for margin and reporting.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Subscribing, changing seats, pausing, or canceling happens per customer —{" "}
              <Link
                to="/customers"
                className="inline-flex items-center gap-1 font-medium text-foreground underline underline-offset-2 hover:text-muted-foreground"
              >
                open a customer's page
                <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.5} />
              </Link>{" "}
              to manage their subscription.
            </p>
          </CardContent>
        </Card>

        <ConnectStatusSection />

        <div className="grid items-start gap-4 lg:grid-cols-2">
          <CreatePlanCard />
          <EditPlanCard />
        </div>

        <div className="rounded-lg border border-dashed border-border px-4 py-3 text-xs text-muted-foreground">
          The API can't list plans back yet: plans you create are provisioned in Stripe, but there
          is no endpoint to fetch them again, so this page can't show a plan table. Keep a record of
          your plan keys — the forms above work from a known key.
        </div>

        <StripeSyncCard />
      </div>
    </ProductGate>
  );
}
