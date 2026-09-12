import * as React from "react";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { toastOnError, toastSuccess } from "@/lib/mutations";

import { useUpdateTenantConfig } from "../api/queries";
import type { TenantConfig } from "../api/types";
import { AdmissionControlForm } from "./admission-control-form";
import { SpendLimitsForm } from "./spend-limits-form";

/**
 * The words for the switch's two positions (slice 6 §10, #462). The
 * position the wire spells `off` is "no customer-wide enforcement" — never
 * "off", because the switch governs the customer-wide family only: every
 * ceiling and window declared on a kind of work still stops the unit it is
 * declared on, and the hourly sweep still repairs it, whatever the switch
 * says. Copy that said "off" invited the reading that nothing happens. The
 * card's test spells both itself, so the page and its assertion cannot
 * move together.
 */
const ENFORCING_LABEL = "Enforcing";
const NO_CUSTOMER_WIDE_ENFORCEMENT_LABEL = "No customer-wide enforcement";

export function SpendControlCard({
  config,
  isAdmin,
}: {
  config: TenantConfig;
  isAdmin: boolean;
}) {
  const enforcement = useUpdateTenantConfig();
  const maintenance = useUpdateTenantConfig();
  const [pendingMode, setPendingMode] = React.useState<
    "off" | "enforcing" | null
  >(null);

  const enforcing = config.enforcement_mode === "enforcing";

  return (
    <Card>
      <CardHeader>
        <CardTitle>Spend control</CardTitle>
        <CardDescription>
          These settings decide when UBB interrupts your customers' usage.
          They apply to every customer that doesn't have its own override.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium">Enforcement</p>
            <p className="max-w-sm text-[13px] text-muted-foreground">
              {ENFORCING_LABEL}: customer-wide spend control — the wallet
              floors' stop and wind-down signals, the customer spend pool's
              stop and the customer-wide stop flag fire and are tracked, and
              work past one of those lines is refused or stopped.{" "}
              {NO_CUSTOMER_WIDE_ENFORCEMENT_LABEL}: none of those signals
              fire and nothing is tracked, but customers past the hard stop
              point are still suspended and refused new work, and every
              ceiling and window declared on a kind of work still stops the
              unit it is declared on.
            </p>
          </div>
          <Switch
            checked={enforcing}
            disabled={!isAdmin || enforcement.isPending}
            aria-label="Enforcement"
            onCheckedChange={(checked: boolean) =>
              setPendingMode(checked ? "enforcing" : "off")
            }
          />
        </div>

        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium">Live spend counters</p>
            <p className="max-w-sm text-[13px] text-muted-foreground">
              Keep each customer's running spend up to date as you report
              usage, so the reply to a usage call already tells you whether
              they've been stopped. When this is not kept up, UBB skips that
              work and catches crossings on its durable path instead — the
              same stops, a little later, and the lag grows the faster a
              customer is spending. This only changes reaction speed — never
              what customers are billed.
            </p>
          </div>
          <Switch
            checked={config.live_counter_maintenance_enabled ?? true}
            disabled={!isAdmin || maintenance.isPending}
            aria-label="Live spend counters"
            onCheckedChange={(checked: boolean) =>
              maintenance.mutate(
                { live_counter_maintenance_enabled: checked },
                {
                  onSuccess: () =>
                    toastSuccess(
                      checked
                        ? "Live spend counters enabled"
                        : "Live spend counters disabled",
                    ),
                  onError: toastOnError(
                    "Couldn't update live spend counters",
                  ),
                },
              )
            }
          />
        </div>

        <Separator />

        <AdmissionControlForm config={config} isAdmin={isAdmin} />

        <Separator />

        <SpendLimitsForm config={config} isAdmin={isAdmin} />
      </CardContent>

      <ConfirmDialog
        open={pendingMode !== null}
        onOpenChange={(open) => {
          if (!open) setPendingMode(null);
        }}
        title={
          pendingMode === "enforcing"
            ? "Turn enforcement on?"
            : "Switch to no customer-wide enforcement?"
        }
        description={
          pendingMode === "enforcing"
            ? "UBB will start refusing new work for customers past a wallet floor or over their customer spend pool, and will stop their running work until they're back within bounds."
            : "UBB stops the customer-wide signal suite: no stop or wind-down webhooks, no customer-wide stop flag, and running work is never stopped mid-flight on a customer-wide line. Customers past the hard stop point are instead suspended outright and refused new work — with no advance stop signal — until they top up or you unsuspend them. Ceilings and windows declared on kinds of work, customer spend pool alerts and the new-work rate keep working."
        }
        confirmLabel={pendingMode === "enforcing" ? "Turn on" : "Stop enforcing"}
        pending={enforcement.isPending}
        onConfirm={() => {
          if (!pendingMode) return;
          enforcement.mutate(
            { enforcement_mode: pendingMode },
            {
              onSuccess: () => {
                setPendingMode(null);
                toastSuccess(
                  pendingMode === "enforcing"
                    ? "Enforcement is on"
                    : NO_CUSTOMER_WIDE_ENFORCEMENT_LABEL,
                );
              },
              onError: (error) => {
                setPendingMode(null);
                toastOnError("Couldn't change enforcement")(error);
              },
            },
          );
        }}
      />
    </Card>
  );
}
