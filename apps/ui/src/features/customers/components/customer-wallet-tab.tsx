import { CustomerBillingPanel } from "@/features/billing-ops/components/customer-billing-panel";
import { CustomerGrantsSection } from "./customer-grants-section";
import {
  CustomerBudgetForm,
  CustomerBillingProfileForm,
} from "./customer-billing-config";

/**
 * Full customer billing surface: wallet (balance, top-up/withdraw, auto top-up,
 * ledger — from the billing-ops feature), grants, spend budget, and the
 * minimum-balance billing profile.
 */
export function CustomerWalletTab({ customerId }: { customerId: string }) {
  return (
    <div className="space-y-6">
      <CustomerBillingPanel customerId={customerId} />
      <CustomerGrantsSection customerId={customerId} />
      <CustomerBudgetForm customerId={customerId} />
      <CustomerBillingProfileForm customerId={customerId} />
    </div>
  );
}
