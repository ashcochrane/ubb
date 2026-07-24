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

export function CostTaxCard({
  config,
  isAdmin,
}: {
  config: TenantConfig;
  isAdmin: boolean;
}) {
  const coverage = useUpdateTenantConfig();
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
              <p className="text-sm font-medium">Require cost card coverage</p>
              <p className="max-w-sm text-[13px] text-muted-foreground">
                Refuse to start work whose provider cost can't be derived from
                your cost rate cards — so no usage ever runs at an unknown
                cost.
              </p>
            </div>
            <Switch
              checked={config.require_cost_card_coverage}
              disabled={!isAdmin || coverage.isPending}
              aria-label="Require cost card coverage"
              onCheckedChange={(checked: boolean) =>
                coverage.mutate(
                  { require_cost_card_coverage: checked },
                  {
                    onSuccess: () =>
                      toastSuccess(
                        checked
                          ? "Cost card coverage is now required"
                          : "Cost card coverage requirement removed",
                      ),
                  },
                )
              }
            />
          </div>
          {coverage.isError && (
            <p className="text-xs text-destructive">
              {problemMessage(coverage.error)}
              {hasCode(coverage.error, "no_cost_cards") && (
                <>
                  {" "}
                  <a href="/pricing" className="underline">
                    Create a cost card in Pricing
                  </a>{" "}
                  first, then try again.
                </>
              )}
            </p>
          )}
        </div>

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
