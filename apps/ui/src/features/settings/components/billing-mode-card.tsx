import * as React from "react";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  BILLING_MODES,
  billingModeDescription,
  billingModeLabel,
  type BillingMode,
} from "@/lib/labels";
import { toastOnError, toastSuccess } from "@/lib/mutations";

import { useUpdateTenantConfig } from "../api/queries";
import type { TenantConfig } from "../api/types";

const MODE_CONSEQUENCE: Record<BillingMode, string> = {
  meter_only:
    "UBB stops moving money: no wallets, no spend gates — usage tracking, cost, and margin only.",
  prepaid:
    "Customers will hold prepaid credit; usage draws balances down in real time and spend-control floors apply.",
  postpaid:
    "Usage accrues per period and is pushed to Stripe as invoice line items when the period closes.",
};

export function BillingModeCard({
  config,
  isAdmin,
}: {
  config: TenantConfig;
  isAdmin: boolean;
}) {
  const mutation = useUpdateTenantConfig();
  const [pendingMode, setPendingMode] = React.useState<BillingMode | null>(
    null,
  );
  const billingEnabled = config.products.includes("billing");

  const confirm = () => {
    if (!pendingMode) return;
    const mode = pendingMode;
    mutation.mutate(
      { billing_mode: mode },
      {
        onSuccess: () => {
          setPendingMode(null);
          toastSuccess(`Billing mode is now ${billingModeLabel(mode)}`);
        },
        onError: (error) => {
          setPendingMode(null);
          toastOnError("Couldn't change the billing mode")(error);
        },
      },
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Billing mode</CardTitle>
        <CardDescription>
          How money moves (or doesn't) between your customers and you. This
          shapes the whole console.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {BILLING_MODES.map((mode) => {
          const isCurrent = config.billing_mode === mode;
          const needsBilling = mode === "prepaid" || mode === "postpaid";
          const blocked = needsBilling && !billingEnabled;
          return (
            <div
              key={mode}
              className={
                "flex items-start justify-between gap-4 rounded-lg border p-3 " +
                (isCurrent ? "border-foreground/40" : "border-border")
              }
            >
              <div>
                <p className="flex items-center gap-2 text-sm font-medium">
                  {billingModeLabel(mode)}
                  {isCurrent && <Badge variant="secondary">Current</Badge>}
                </p>
                <p className="max-w-md text-[13px] text-muted-foreground">
                  {billingModeDescription(mode)}
                </p>
                {blocked && (
                  <p className="mt-1 text-[12px] text-muted-foreground">
                    Requires the Billing product — enable it below first.
                  </p>
                )}
              </div>
              {!isCurrent && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!isAdmin || blocked || mutation.isPending}
                  onClick={() => setPendingMode(mode)}
                >
                  Switch
                </Button>
              )}
            </div>
          );
        })}
      </CardContent>

      <ConfirmDialog
        open={pendingMode !== null}
        onOpenChange={(open) => {
          if (!open) setPendingMode(null);
        }}
        title={
          pendingMode
            ? `Switch to ${billingModeLabel(pendingMode)}?`
            : "Switch billing mode?"
        }
        description={
          pendingMode
            ? `${MODE_CONSEQUENCE[pendingMode]} Existing data is preserved.`
            : ""
        }
        confirmLabel="Switch mode"
        pending={mutation.isPending}
        onConfirm={confirm}
      />
    </Card>
  );
}
