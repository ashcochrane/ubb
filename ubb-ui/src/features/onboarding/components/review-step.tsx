// src/features/onboarding/components/review-step.tsx
import { useState } from "react";
import { useFormContext } from "react-hook-form";
import { Check, Loader2, AlertCircle } from "lucide-react";
import type { OnboardingFormValues } from "../lib/schema";
import { useActivateOnboarding } from "../api/queries";

interface ReviewStepProps {
  onActivated: () => void;
  onEditStep?: (step: number) => void;
}

export function ReviewStep({ onActivated, onEditStep }: ReviewStepProps) {
  const { watch, getValues } = useFormContext<OnboardingFormValues>();
  const mode = watch("mode");
  const activateMutation = useActivateOnboarding();
  const [error, setError] = useState<string | null>(null);

  const handleActivate = async () => {
    setError(null);
    try {
      const values = getValues();
      await activateMutation.mutateAsync({
        mode: values.mode,
        stripeKey: values.stripeKey,
        identifierMode: values.identifierMode,
        metadataKey: values.metadataKey,
        defaultMargin: mode === "billing" ? values.defaultMargin : undefined,
        alertThresholds: mode === "billing" ? {
          notifyAt: values.notifyAt,
          remindAt: values.remindAt,
          pauseAtZero: values.pauseAtZero,
        } : undefined,
      });
      onActivated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Activation failed. Please try again.");
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-[16px] font-semibold">Review and activate</h2>
        <p className="mt-1 text-[12px] text-muted-foreground">
          Everything looks good. Review your setup and activate when ready.
        </p>
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 dark:border-red-900/50 dark:bg-red-950/30">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-600" />
          <span className="text-label text-red-700 dark:text-red-400">{error}</span>
        </div>
      )}

      {/* Stripe connection */}
      <ReviewCard
        title="Stripe connection"
        onEdit={onEditStep ? () => onEditStep(1) : undefined}
        items={[
          { label: "API key", value: maskKey(watch("stripeKey") ?? "") },
          { label: "Permissions", value: mode === "billing" ? "Read + write (balance transactions)" : "Read-only" },
        ]}
      />

      {/* Customer mapping */}
      <ReviewCard
        title="Customer mapping"
        onEdit={onEditStep ? () => onEditStep(2) : undefined}
        items={[
          { label: "Identifier mode", value: formatIdentifierMode(watch("identifierMode")) },
          { label: "Status", value: watch("mappingComplete") ? "All customers mapped" : "Mapping incomplete" },
        ]}
      />

      {/* Billing config (billing only) */}
      {mode === "billing" && (
        <ReviewCard
          title="Billing configuration"
          onEdit={onEditStep ? () => onEditStep(3) : undefined}
          items={[
            { label: "Default margin", value: `${watch("defaultMargin")}%` },
            { label: "Effective multiplier", value: `${(1 + watch("defaultMargin") / 100).toFixed(2)}x` },
            { label: "Low balance alert", value: watch("notifyAt") > 0 ? `At $${watch("notifyAt")}` : "Off" },
            { label: "Customer reminder", value: watch("remindAt") > 0 ? `At $${watch("remindAt")}` : "Off" },
            { label: "Auto-pause at $0", value: watch("pauseAtZero") ? "On" : "Off" },
          ]}
        />
      )}

      {/* Sync settings */}
      <ReviewCard
        title="Data sync"
        items={[
          { label: "Sync frequency", value: "Every 6 hours" },
          { label: "Historical backfill", value: "Last 12 months of invoice data" },
          { label: "New customers", value: "Auto-detected on each sync" },
        ]}
      />

      {/* Checklist */}
      <div className="space-y-1.5">
        <CheckItem label="Stripe key validated with correct permissions" />
        <CheckItem label="All customers matched to SDK identifiers" />
        {mode === "billing" && <CheckItem label="Default margin configured" />}
      </div>

      <button
        type="button"
        onClick={handleActivate}
        disabled={activateMutation.isPending}
        className="w-full rounded-lg bg-foreground px-4 py-2.5 text-[12px] font-medium text-background hover:opacity-90 disabled:opacity-50"
      >
        {activateMutation.isPending ? (
          <span className="flex items-center justify-center gap-2">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Activating...
          </span>
        ) : (
          "Activate Stripe integration"
        )}
      </button>
    </div>
  );
}

function ReviewCard({ title, items, onEdit }: { title: string; items: { label: string; value: string }[]; onEdit?: () => void }) {
  return (
    <div className="rounded-xl border border-border px-4 py-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex h-4 w-4 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
            <Check className="h-2.5 w-2.5 text-green-600" />
          </div>
          <span className="text-[12px] font-medium">{title}</span>
        </div>
        {onEdit && (
          <button
            type="button"
            onClick={onEdit}
            className="text-label text-muted-foreground hover:text-foreground"
          >
            Edit
          </button>
        )}
      </div>
      <div className="space-y-1">
        {items.map((item) => (
          <div key={item.label} className="flex justify-between text-label">
            <span className="text-muted-foreground">{item.label}</span>
            <span className="font-mono">{item.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function CheckItem({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex h-4 w-4 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
        <Check className="h-2.5 w-2.5 text-green-600" />
      </div>
      <span className="text-label">{label}</span>
    </div>
  );
}

function maskKey(key: string): string {
  if (key.length < 10) return key;
  return key.slice(0, 8) + "..." + key.slice(-4);
}

function formatIdentifierMode(mode?: string): string {
  switch (mode) {
    case "stripe_id": return "Stripe customer ID";
    case "email": return "Email address";
    case "internal_id": return "Internal ID / slug";
    case "metadata": return "Stripe metadata field";
    default: return "Not selected";
  }
}
