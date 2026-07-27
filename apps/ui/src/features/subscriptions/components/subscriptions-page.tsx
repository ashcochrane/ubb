import { Info } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { ProductUnavailable } from "@/components/shared/data-states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { SyncSection } from "./sync-section";
import { CustomerLookupSection } from "./customer-lookup-section";

export function SubscriptionsPage() {
  const { hasProduct } = useAuth();

  if (!hasProduct("subscriptions")) {
    return (
      <div className="space-y-6">
        <PageHeader title="Subscriptions" />
        <ProductUnavailable product="Subscriptions" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Subscriptions"
        description="Reconcile subscriptions from Stripe and inspect a customer's subscription and invoices."
      />

      <Alert>
        <Info />
        <AlertTitle>No account-wide subscription list</AlertTitle>
        <AlertDescription>
          The API exposes subscriptions per customer only — there is no endpoint to list every
          subscription. Look one up by customer ID below. Per-customer lifecycle actions
          (subscribe, set seats, cancel, pause, resume) live on the customer detail page.
        </AlertDescription>
      </Alert>

      <SyncSection />

      <CustomerLookupSection />
    </div>
  );
}
