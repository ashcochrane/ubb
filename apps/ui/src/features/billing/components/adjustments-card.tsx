import { Separator } from "@/components/ui/separator";
import { useHasRole } from "@/hooks/use-current-role";

import { CreditForm } from "./credit-form";
import { DebitForm } from "./debit-form";
import { SectionCard } from "./section-card";

export function AdjustmentsCard() {
  const isAdmin = useHasRole("admin");
  return (
    <SectionCard
      title="Manual ledger adjustments"
      description="Directly credit or debit a customer's wallet — for goodwill credit, corrections, or recovering a mistaken credit. These move real money the moment they're confirmed."
    >
      {!isAdmin && (
        <p className="mb-4 text-[11px] text-text-muted">
          These forms need the Admin role — they move real money.
        </p>
      )}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <CreditForm isAdmin={isAdmin} />
        <div className="lg:hidden">
          <Separator />
        </div>
        <DebitForm isAdmin={isAdmin} />
      </div>
    </SectionCard>
  );
}
