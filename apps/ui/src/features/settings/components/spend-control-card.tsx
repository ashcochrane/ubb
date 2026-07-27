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
import { SpendLimitsForm } from "./spend-limits-form";

export function SpendControlCard({
  config,
  isAdmin,
}: {
  config: TenantConfig;
  isAdmin: boolean;
}) {
  const enforcement = useUpdateTenantConfig();
  const arrival = useUpdateTenantConfig();
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
              Enforcing: real-time spend control — limit crossings fire stop
              and wind-down webhooks and are tracked, and work past a limit is
              refused or stopped. Off: that whole suite is disabled — no stop
              or wind-down webhooks, no past-limit tracking — but customers
              past the hard stop point are still suspended and refused new
              work.
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
            <p className="text-sm font-medium">Arrival signals</p>
            <p className="max-w-sm text-[13px] text-muted-foreground">
              Detect limit crossings the moment usage arrives (the fastest
              reaction). When off, crossings are detected slightly later, at
              settlement. This only changes reaction speed — never what
              customers are billed.
            </p>
          </div>
          <Switch
            checked={config.arrival_signals_enabled ?? true}
            disabled={!isAdmin || arrival.isPending}
            aria-label="Arrival signals"
            onCheckedChange={(checked: boolean) =>
              arrival.mutate(
                { arrival_signals_enabled: checked },
                {
                  onSuccess: () =>
                    toastSuccess(
                      checked
                        ? "Arrival signals enabled"
                        : "Arrival signals disabled",
                    ),
                  onError: toastOnError("Couldn't update arrival signals"),
                },
              )
            }
          />
        </div>

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
            : "Turn enforcement off?"
        }
        description={
          pendingMode === "enforcing"
            ? "UBB will start refusing new work for customers past their limits. Customers at a balance floor or over a task limit will be interrupted until they're back within bounds."
            : "UBB stops the real-time spend-control suite: no stop or wind-down-floor webhooks, no past-limit report entries, and running work is never stopped mid-flight. Customers past the hard stop point are instead suspended outright and refused new work — with no advance stop signal — until they top up or you unsuspend them. Budget caps and alerts keep working."
        }
        confirmLabel={pendingMode === "enforcing" ? "Turn on" : "Turn off"}
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
                    : "Enforcement is off",
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
