import { useState } from "react";
import { Pencil, Power, PowerOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Section,
  DetailGrid,
  DetailRow,
  LoadingRows,
} from "@/components/shared/data-states";
import { StatusBadge } from "@/components/shared/status-badge";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { formatDate, formatDollars, formatPercent } from "@/lib/format";
import { formatRewardValue } from "../lib/reward";
import { useProgram, useDeactivateProgram, useReactivateProgram } from "../api/queries";
import { ProgramForm } from "./program-form";
import type { Program } from "../api/types";

export function ProgramTab() {
  const query = useProgram();

  if (query.isLoading) return <LoadingRows rows={4} />;

  // No program configured yet surfaces as an error — offer to create one.
  if (query.isError || !query.data) {
    return (
      <Section
        title="Create a referral program"
        description="Set up how referrers earn rewards. You can edit or deactivate the program at any time."
      >
        <ProgramForm />
      </Section>
    );
  }

  return <ProgramView program={query.data} />;
}

function ProgramView({ program }: { program: Program }) {
  const [editOpen, setEditOpen] = useState(false);
  const deactivate = useDeactivateProgram();
  const reactivate = useReactivateProgram();
  const isActive = program.status.toLowerCase() === "active";

  return (
    <Section
      title="Referral program"
      description="How referrers earn rewards for the customers they bring in."
      actions={
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
            <Pencil />
            Edit
          </Button>
          {isActive ? (
            <ConfirmDialog
              destructive
              title="Deactivate referral program?"
              description="Referrers stop earning new rewards. Existing referrals are unaffected. You can reactivate later."
              confirmLabel="Deactivate"
              onConfirm={async () => {
                await deactivate.mutateAsync();
              }}
              trigger={
                <Button variant="destructive" size="sm">
                  <PowerOff />
                  Deactivate
                </Button>
              }
            />
          ) : (
            <Button
              variant="outline"
              size="sm"
              disabled={reactivate.isPending}
              onClick={() => reactivate.mutate()}
            >
              <Power />
              Reactivate
            </Button>
          )}
        </div>
      }
    >
      <DetailGrid>
        <DetailRow label="Status">
          <StatusBadge value={program.status} />
        </DetailRow>
        <DetailRow label="Reward model">
          <StatusBadge value={program.reward_type} tone="neutral" />
        </DetailRow>
        <DetailRow label="Reward value">
          {formatRewardValue(program.reward_type, program.reward_value)}
        </DetailRow>
        <DetailRow label="Attribution window">
          {program.attribution_window_days} days
        </DetailRow>
        <DetailRow label="Reward window">
          {program.reward_window_days != null
            ? `${program.reward_window_days} days`
            : "—"}
        </DetailRow>
        <DetailRow label="Max reward">
          {program.max_reward_micros != null
            ? formatDollars(program.max_reward_micros / 1_000_000)
            : "—"}
        </DetailRow>
        <DetailRow label="Estimated cost">
          {program.estimated_cost_percentage != null
            ? formatPercent(program.estimated_cost_percentage)
            : "—"}
        </DetailRow>
        <DetailRow label="Max referrals / day">
          {program.max_referrals_per_day ?? "—"}
        </DetailRow>
        <DetailRow label="Min customer age">
          {program.min_customer_age_hours != null
            ? `${program.min_customer_age_hours} hours`
            : "—"}
        </DetailRow>
        <DetailRow label="Created">{formatDate(program.created_at)}</DetailRow>
        <DetailRow label="Updated">{formatDate(program.updated_at)}</DetailRow>
      </DetailGrid>

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Edit referral program</DialogTitle>
            <DialogDescription>
              Changes apply to new referrals. Leave optional caps blank to remove them.
            </DialogDescription>
          </DialogHeader>
          <ProgramForm existing={program} onDone={() => setEditOpen(false)} />
        </DialogContent>
      </Dialog>
    </Section>
  );
}
