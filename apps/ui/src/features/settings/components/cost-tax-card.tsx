import { ApiProblem, problemMessage } from "@/api/problem";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { toastSuccess } from "@/lib/mutations";

import { useUpdateTenantConfig } from "../api/queries";
import type { TenantConfig } from "../api/types";

function hasCode(error: unknown, code: string): boolean {
  return error instanceof ApiProblem && error.code === code;
}

// A strict-cost-coverage toggle sat above the tax switch until #321. It armed
// a wall — with it on, an event UBB could not cost was refused rather than
// recorded — and the wall is gone: an uncostable event is now recorded with
// its cost unresolved and the gaps named, so there is nothing left to turn on.
// The card keeps its name because tax is still a cost-side setting.
export function CostTaxCard({
  config,
  isAdmin,
}: {
  config: TenantConfig;
  isAdmin: boolean;
}) {
  const tax = useUpdateTenantConfig();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Cost & tax</CardTitle>
        <CardDescription>
          How UBB treats provider costs and sales tax.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium">Automatic tax</p>
              <p className="max-w-sm text-[13px] text-muted-foreground">
                Let Stripe Tax calculate and add sales tax on the invoices UBB
                pushes to Stripe. Requires Stripe Tax to be active on your
                connected account.
              </p>
            </div>
            <Switch
              checked={config.automatic_tax_enabled}
              disabled={!isAdmin || tax.isPending}
              aria-label="Automatic tax"
              onCheckedChange={(checked: boolean) =>
                tax.mutate(
                  { automatic_tax_enabled: checked },
                  {
                    onSuccess: () =>
                      toastSuccess(
                        checked
                          ? "Automatic tax enabled"
                          : "Automatic tax disabled",
                      ),
                  },
                )
              }
            />
          </div>
          {tax.isError && (
            <p className="text-xs text-destructive">
              {problemMessage(tax.error)}
              {hasCode(tax.error, "stripe_tax_not_active") && (
                <>
                  {" "}
                  <a
                    href="https://dashboard.stripe.com/settings/tax"
                    target="_blank"
                    rel="noreferrer"
                    className="underline"
                  >
                    Activate Stripe Tax
                  </a>{" "}
                  on your Stripe account, then try again.
                </>
              )}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
