import { Info } from "lucide-react";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { CustomerBillingPanel } from "@/features/billing-ops/components/customer-billing-panel";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { CustomerGrantsSection } from "./customer-grants-section";
import {
  CustomerBudgetForm,
  CustomerBillingProfileForm,
} from "./customer-billing-config";

/**
 * Full customer billing surface: wallet (balance, top-up/withdraw, auto top-up,
 * ledger — from the billing-ops feature), grants, spend budget, and the
 * minimum-balance billing profile.
 *
 * Under postpaid the wallet isn't the billing mechanism — drawdown skips
 * postpaid customers entirely and both balance floors are skipped at the
 * spend-control gate (apps/billing/handlers.py, .../gating/services/risk_service.py).
 * So prepaid-only credit flows (top-up, withdraw, auto top-up, grants) are
 * hidden rather than rendered inert; the balance figure and transaction
 * ledger stay, since manual adjustments still move a postpaid wallet.
 */
export function CustomerWalletTab({ customerId }: { customerId: string }) {
  const { isPostpaid } = useAuth();

  return (
    <div className="space-y-6">
      {isPostpaid && (
        <Alert>
          <Info />
          <AlertTitle>Postpaid: the wallet isn't the billing mechanism</AlertTitle>
          <AlertDescription>
            This customer is billed postpaid — usage is invoiced at period close, not drawn from
            this wallet. Top-up, withdrawal, auto top-up, and grants are hidden because they have
            no billing effect here; the balance and transaction history below still reflect manual
            adjustments.
          </AlertDescription>
        </Alert>
      )}
      <CustomerBillingPanel customerId={customerId} isPostpaid={isPostpaid} />
      {!isPostpaid && <CustomerGrantsSection customerId={customerId} />}
      <CustomerBudgetForm customerId={customerId} />
      <CustomerBillingProfileForm customerId={customerId} />
    </div>
  );
}
