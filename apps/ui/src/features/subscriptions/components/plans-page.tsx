import { Info } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { ProductUnavailable, Section } from "@/components/shared/data-states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { CreatePlanForm } from "./create-plan-form";
import { UpdatePlanForm } from "./update-plan-form";

export function PlansPage() {
  const { hasProduct } = useAuth();

  if (!hasProduct("subscriptions")) {
    return (
      <div className="space-y-6">
        <PageHeader title="Plans" />
        <ProductUnavailable product="Subscriptions" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Plans"
        description="Define the recurring access fees and per-seat prices customers subscribe to."
      />

      <Alert>
        <Info />
        <AlertTitle>Plans are write-only, keyed by plan key</AlertTitle>
        <AlertDescription>
          The API has no endpoint to list or read plans back — you can only create a plan or
          update one by its <span className="font-mono">key</span>. Keep a record of the keys you
          create; you'll need them to make changes here or to subscribe customers on the customer
          detail page.
        </AlertDescription>
      </Alert>

      <Section
        title="Create plan"
        description="Blind create — the returned plan summary is shown once on success."
      >
        <CreatePlanForm />
      </Section>

      <Section
        title="Update plan"
        description="Re-price an existing plan by key. Fees enter a new versioned Stripe price."
      >
        <UpdatePlanForm />
      </Section>
    </div>
  );
}
