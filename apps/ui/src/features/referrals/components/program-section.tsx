import { useState } from "react";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { DetailList, type DetailItem } from "@/components/shared/detail-list";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useHasRole } from "@/hooks/use-current-role";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { formatDate, formatMicros, formatPercent } from "@/lib/format";
import { referralProgramStatusLabel } from "@/lib/labels";
import { toastSuccess } from "@/lib/mutations";

import {
  useCreateProgram,
  useDeactivateProgram,
  useProgram,
  useReactivateProgram,
  useUpdateProgram,
} from "../api/queries";
import type { ProgramOut } from "../api/types";
import { looseDate } from "../lib/dates";
import {
  programToFormValues,
  rewardSummary,
  toProgramCreateRequest,
  toProgramUpdateRequest,
} from "../lib/program-form";
import { ProgramForm } from "./program-form";

function programItems(program: ProgramOut, currency: string): DetailItem[] {
  return [
    { label: "Reward", value: rewardSummary(program.reward_type, program.reward_value, currency) },
    { label: "Attribution window", value: `${program.attribution_window_days} days` },
    {
      label: "Reward window",
      value: program.reward_window_days === null ? "No end" : `${program.reward_window_days} days`,
    },
    {
      label: "Lifetime cap per referral",
      value:
        program.max_reward_micros === null
          ? "No cap"
          : formatMicros(program.max_reward_micros, currency),
    },
    {
      label: "Estimated cost",
      value:
        program.estimated_cost_percentage === null
          ? "—"
          : `${formatPercent(program.estimated_cost_percentage)} of referred spend`,
    },
    {
      label: "Daily referral limit",
      value:
        program.max_referrals_per_day === null ? "No limit" : `${program.max_referrals_per_day} per day`,
    },
    {
      label: "Minimum customer age",
      value:
        program.min_customer_age_hours === null ? "None" : `${program.min_customer_age_hours} hours`,
    },
    { label: "Program ID", value: program.id, mono: true },
    { label: "Created", value: looseDate(program.created_at, formatDate) },
    { label: "Last updated", value: looseDate(program.updated_at, formatDate) },
  ];
}

export function ProgramSection() {
  const currency = useTenantCurrency();
  const program = useProgram();
  const canAdmin = useHasRole("admin");

  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deactivateOpen, setDeactivateOpen] = useState(false);

  const createMutation = useCreateProgram();
  const updateMutation = useUpdateProgram();
  const deactivateMutation = useDeactivateProgram();
  const reactivateMutation = useReactivateProgram();

  if (program.isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-56 w-full" />
      </div>
    );
  }

  if (program.isError) {
    return (
      <ErrorCard
        error={program.error}
        onRetry={() => void program.refetch()}
        title="Couldn't load the referral program"
      />
    );
  }

  const data = program.data ?? null;
  const adminTitle = canAdmin ? undefined : "Requires the Admin role";

  if (data === null) {
    return (
      <>
        <EmptyState
          title="No referral program yet"
          description="The program defines how referrers earn — a flat fee per referral, or a share of referred revenue or profit. Referrals snapshot the settings when they're attributed, so later edits never apply retroactively."
          action={{ label: "Create program", onClick: () => setCreateOpen(true) }}
        />
        <Dialog
          open={createOpen}
          onOpenChange={(open) => {
            setCreateOpen(open);
            if (!open) createMutation.reset();
          }}
        >
          <DialogContent className="sm:max-w-xl">
            <DialogHeader>
              <DialogTitle>Create referral program</DialogTitle>
              <DialogDescription>
                One program per workspace. You can edit or deactivate it later.
              </DialogDescription>
            </DialogHeader>
            {!canAdmin && (
              <p className="text-xs text-muted-foreground">
                Creating a program requires the Admin role — the server will refuse otherwise.
              </p>
            )}
            <ProgramForm
              mode="create"
              currency={currency}
              pending={createMutation.isPending}
              error={createMutation.error}
              submitLabel="Create program"
              onSubmit={(values) =>
                createMutation.mutate(toProgramCreateRequest(values), {
                  onSuccess: () => {
                    toastSuccess("Referral program created");
                    setCreateOpen(false);
                  },
                })
              }
            />
          </DialogContent>
        </Dialog>
      </>
    );
  }

  const isDeactivated = data.status === "deactivated";

  return (
    <Card>
      <CardHeader className="border-b">
        <CardTitle className="flex items-center gap-2">
          Referral program
          <Badge variant={isDeactivated ? "secondary" : "outline"}>
            {referralProgramStatusLabel(data.status)}
          </Badge>
        </CardTitle>
        <CardAction className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setEditOpen(true)}
            disabled={!canAdmin}
            title={adminTitle}
          >
            Edit
          </Button>
          {isDeactivated ? (
            <Button
              size="sm"
              disabled={!canAdmin || reactivateMutation.isPending}
              title={adminTitle}
              onClick={() =>
                reactivateMutation.mutate(undefined, {
                  onSuccess: () => toastSuccess("Program reactivated"),
                })
              }
            >
              {reactivateMutation.isPending ? "Working…" : "Reactivate"}
            </Button>
          ) : (
            <Button
              variant="destructive"
              size="sm"
              onClick={() => setDeactivateOpen(true)}
              disabled={!canAdmin}
              title={adminTitle}
            >
              Deactivate
            </Button>
          )}
        </CardAction>
      </CardHeader>
      <CardContent>
        <DetailList items={programItems(data, currency)} />
      </CardContent>

      <Dialog
        open={editOpen}
        onOpenChange={(open) => {
          setEditOpen(open);
          if (!open) updateMutation.reset();
        }}
      >
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Edit referral program</DialogTitle>
            <DialogDescription>
              Changes apply to future referrals only — existing referrals keep the settings they
              were attributed under.
            </DialogDescription>
          </DialogHeader>
          <ProgramForm
            mode="edit"
            currency={currency}
            defaultValues={programToFormValues(data)}
            pending={updateMutation.isPending}
            error={updateMutation.error}
            submitLabel="Save changes"
            onSubmit={(values) =>
              updateMutation.mutate(toProgramUpdateRequest(values), {
                onSuccess: () => {
                  toastSuccess("Program updated");
                  setEditOpen(false);
                },
              })
            }
          />
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deactivateOpen}
        onOpenChange={setDeactivateOpen}
        title="Deactivate the referral program?"
        description="New attributions and reward accrual stop immediately. Existing referral records are kept, and you can reactivate the program at any time."
        confirmLabel="Deactivate"
        destructive
        pending={deactivateMutation.isPending}
        onConfirm={() =>
          deactivateMutation.mutate(undefined, {
            onSuccess: () => {
              toastSuccess("Program deactivated");
              setDeactivateOpen(false);
            },
          })
        }
      />
    </Card>
  );
}
