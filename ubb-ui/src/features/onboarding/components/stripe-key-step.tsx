// src/features/onboarding/components/stripe-key-step.tsx
import { useState } from "react";
import { useFormContext } from "react-hook-form";
import { CheckCircle, AlertCircle, Loader2 } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import type { OnboardingFormValues } from "../lib/schema";
import type { StripeSyncPreview, StripePermission } from "../api/types";
import { useValidateStripeKey } from "../api/queries";
import { PermissionsTable } from "./permissions-table";
import { READ_PERMISSIONS, BILLING_PERMISSIONS } from "../lib/constants";

export function StripeKeyStep() {
  const { watch, setValue } = useFormContext<OnboardingFormValues>();
  const mode = watch("mode");
  const stripeKey = watch("stripeKey") ?? "";
  const keyValidated = watch("keyValidated");
  const validateMutation = useValidateStripeKey();
  const [preview, setPreview] = useState<StripeSyncPreview | null>(null);
  const [validatedPermissions, setValidatedPermissions] = useState<StripePermission[]>([]);
  const [error, setError] = useState<string | null>(null);

  const isBilling = mode === "billing";
  const requiredPermissions = isBilling ? BILLING_PERMISSIONS : READ_PERMISSIONS;

  const handleValidate = async () => {
    setError(null);
    try {
      const result = await validateMutation.mutateAsync({
        apiKey: stripeKey,
        mode: mode,
      });

      if (result.validation.valid) {
        setValue("keyValidated", true);
        setPreview(result.preview);
        setValidatedPermissions(result.validation.permissions);
      } else {
        setError(result.validation.error ?? "Key validation failed.");
        setValue("keyValidated", false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to validate key. Please try again.");
      setValue("keyValidated", false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-[16px] font-semibold">Connect your Stripe account</h2>
        <p className="mt-1 text-[12px] text-muted-foreground">
          Create a restricted API key in your Stripe dashboard with these permissions:
        </p>
      </div>

      <PermissionsTable permissions={requiredPermissions} />

      {isBilling && (
        <Alert className="border-purple-200 bg-purple-50 text-purple-700 dark:border-purple-800 dark:bg-purple-900/20 dark:text-purple-400">
          <AlertDescription className="text-label text-purple-700 dark:text-purple-400">
            Billing mode requires one additional write permission: Customer balance transactions. This allows debiting customer balances — it cannot create charges, modify customer data, or access payment methods.
          </AlertDescription>
        </Alert>
      )}

      {/* Key input */}
      <div>
        <label className="mb-1 block text-label font-medium">Restricted API key</label>
        <div className="flex gap-2">
          <input
            value={stripeKey}
            onChange={(e) => {
              setValue("stripeKey", e.target.value);
              if (keyValidated) {
                setValue("keyValidated", false);
                setPreview(null);
                setError(null);
              }
            }}
            placeholder="rk_live_..."
            className="flex-1 rounded-lg border border-border bg-background px-3 py-2 font-mono text-[12px] outline-none focus:border-muted-foreground"
          />
          <button
            type="button"
            onClick={handleValidate}
            disabled={!stripeKey || validateMutation.isPending}
            className="rounded-lg bg-foreground px-4 py-2 text-[12px] font-medium text-background hover:opacity-90 disabled:opacity-50"
          >
            {validateMutation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              "Validate key"
            )}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <Alert
          variant="destructive"
          className="border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-900/20"
        >
          <AlertCircle />
          <AlertDescription className="text-label text-red-700 dark:text-red-400">
            {error}
          </AlertDescription>
        </Alert>
      )}

      {/* Success + preview */}
      {keyValidated && preview && (
        <div className="space-y-3">
          <Alert className="border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-900/20 dark:text-green-400 [&>svg]:text-green-600">
            <CheckCircle />
            <AlertDescription className="text-label text-green-700 dark:text-green-400">
              Key validated successfully. All required permissions confirmed.
            </AlertDescription>
          </Alert>

          {validatedPermissions.length > 0 && (
            <PermissionsTable permissions={validatedPermissions} />
          )}

          <div className="grid grid-cols-3 gap-3 rounded-lg bg-accent/50 px-4 py-3">
            <div>
              <div className="text-[18px] font-semibold">{preview.customerCount}</div>
              <div className="text-muted text-muted-foreground">Customers</div>
            </div>
            <div>
              <div className="text-[18px] font-semibold">{preview.activeSubscriptions}</div>
              <div className="text-muted text-muted-foreground">Active subscriptions</div>
            </div>
            <div>
              <div className="text-[18px] font-semibold">${preview.revenue30d.toLocaleString()}</div>
              <div className="text-muted text-muted-foreground">Revenue (last 30d)</div>
            </div>
          </div>
        </div>
      )}

      <p className="text-muted text-muted-foreground">
        Your key is encrypted at rest and never stored in plain text.
      </p>
    </div>
  );
}
