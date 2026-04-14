// src/features/onboarding/components/customer-mapping-step.tsx
import { useState } from "react";
import { useFormContext } from "react-hook-form";
import { Loader2, CheckCircle, AlertCircle } from "lucide-react";
import type { OnboardingFormValues } from "../lib/schema";
import type { IdentifierMode } from "../api/types";
import { useMatchCustomers } from "../api/queries";
import { MatchResultsTable } from "./match-results-table";
import { cn } from "@/lib/utils";

const identifierModes: { value: IdentifierMode; title: string; subtitle: string; example: string }[] = [
  { value: "stripe_id", title: "Stripe customer ID", subtitle: "I already use cus_xxxxx in my code", example: "cus_R4kB9xPm2nQ" },
  { value: "email", title: "Email address", subtitle: "Identify users by email", example: "user@company.com" },
  { value: "internal_id", title: "Internal ID or slug", subtitle: "Your own identifier", example: "acme_corp, org_4521" },
  { value: "metadata", title: "Stripe metadata field", subtitle: "Stored in customer metadata", example: "metadata.platform_id" },
];

export function CustomerMappingStep() {
  const { watch, setValue } = useFormContext<OnboardingFormValues>();
  const identifierMode = watch("identifierMode");
  const metadataKey = watch("metadataKey") ?? "";
  const matchResult = watch("matchResult");
  const matchMutation = useMatchCustomers();
  const [error, setError] = useState<string | null>(null);

  const canMatch = identifierMode && (identifierMode !== "metadata" || metadataKey.length > 0);

  const handleMatch = async () => {
    if (!identifierMode) return;
    setError(null);
    try {
      const result = await matchMutation.mutateAsync({
        identifierMode,
        metadataKey: identifierMode === "metadata" ? metadataKey : undefined,
      });
      setValue("matchResult", result);

      if (result.needsManual === 0) {
        setValue("mappingComplete", true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to match customers. Please try again.");
    }
  };

  const handleManualUpdate = (stripeId: string, identifier: string) => {
    if (!matchResult) return;
    const updated = matchResult.customers.map((c) =>
      c.stripeId === stripeId ? { ...c, identifier, status: identifier ? "matched" as const : "manual" as const } : c,
    );
    const newResult = {
      ...matchResult,
      customers: updated,
      matched: updated.filter((c) => c.status === "matched").length,
      needsManual: updated.filter((c) => c.status !== "matched").length,
    };
    setValue("matchResult", newResult);

    if (newResult.needsManual === 0) {
      setValue("mappingComplete", true);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-[16px] font-semibold">How do you identify your customers?</h2>
        <p className="mt-1 text-[12px] text-muted-foreground">
          Your SDK will send a customer identifier with each API event. Tell us how you identify customers so we can match them to Stripe.
        </p>
      </div>

      {/* Identifier mode grid */}
      <div className="grid grid-cols-2 gap-2.5">
        {identifierModes.map((m) => (
          <button
            key={m.value}
            type="button"
            onClick={() => {
              setValue("identifierMode", m.value);
              setValue("matchResult", null);
              setValue("mappingComplete", false);
            }}
            className={cn(
              "rounded-xl border px-3.5 py-3 text-left transition-colors",
              identifierMode === m.value
                ? "border-2 border-foreground"
                : "border-border hover:border-muted-foreground hover:bg-accent",
            )}
          >
            <div className="text-[12px] font-medium">{m.title}</div>
            <div className="text-muted text-muted-foreground">{m.subtitle}</div>
            <div className="mt-1 font-mono text-muted text-muted-foreground">{m.example}</div>
          </button>
        ))}
      </div>

      {/* Metadata key input */}
      {identifierMode === "metadata" && (
        <div>
          <label className="mb-1 block text-label font-medium">Which metadata key do you use?</label>
          <input
            value={metadataKey}
            onChange={(e) => setValue("metadataKey", e.target.value)}
            placeholder="e.g. platform_id"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 font-mono text-[12px] outline-none focus:border-muted-foreground"
          />
          <p className="mt-0.5 text-muted text-muted-foreground">
            We'll look in each customer's metadata object for this key.
          </p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 dark:border-red-800 dark:bg-red-900/20">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-500" />
          <p className="text-label text-red-700 dark:text-red-400">{error}</p>
        </div>
      )}

      {/* Match button */}
      {identifierMode && !matchResult && (
        <button
          type="button"
          onClick={handleMatch}
          disabled={!canMatch || matchMutation.isPending}
          className="w-full rounded-lg bg-foreground px-4 py-2.5 text-[12px] font-medium text-background hover:opacity-90 disabled:opacity-50"
        >
          {matchMutation.isPending ? (
            <span className="flex items-center justify-center gap-2">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Matching customers...
            </span>
          ) : (
            "Match my Stripe customers"
          )}
        </button>
      )}

      {/* Match results */}
      {matchResult && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="text-[12px] font-medium">
              {matchResult.matched} of {matchResult.total} matched
            </span>
            {matchResult.needsManual === 0 ? (
              <span className="rounded-full bg-green-50 px-2 py-0.5 text-muted font-medium text-green-700 dark:bg-green-900/20 dark:text-green-400">
                All matched
              </span>
            ) : (
              <span className="rounded-full bg-amber-50 px-2 py-0.5 text-muted font-medium text-amber-700 dark:bg-amber-900/20 dark:text-amber-400">
                {matchResult.needsManual} need input
              </span>
            )}
          </div>

          <MatchResultsTable
            customers={matchResult.customers}
            onManualUpdate={handleManualUpdate}
          />

          {matchResult.needsManual === 0 && (
            <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-3 py-2 dark:border-green-800 dark:bg-green-900/20">
              <CheckCircle className="h-3.5 w-3.5 text-green-600" />
              <span className="text-label text-green-700 dark:text-green-400">Customer mapping complete</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
