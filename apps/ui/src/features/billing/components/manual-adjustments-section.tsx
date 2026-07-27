import { Section } from "@/components/shared/data-states";
import { CreditDialog } from "./credit-dialog";
import { DebitDialog } from "./debit-dialog";

export function ManualAdjustmentsSection() {
  return (
    <Section
      title="Manual adjustments"
      description="Directly credit or debit a customer's wallet. Every adjustment moves money and is confirmed before it runs."
      actions={
        <div className="flex items-center gap-2">
          <CreditDialog />
          <DebitDialog />
        </div>
      }
    >
      <p className="text-sm text-muted-foreground">
        Use <span className="font-medium text-foreground">Issue credit</span> to add
        funds (e.g. goodwill or promo) and{" "}
        <span className="font-medium text-foreground">Record debit</span> to remove
        funds from a customer's wallet. An idempotency key is generated
        automatically per submission. The new balance is shown on success.
      </p>
    </Section>
  );
}
