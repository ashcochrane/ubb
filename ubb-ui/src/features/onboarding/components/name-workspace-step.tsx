import { useFormContext } from "react-hook-form";
import type { OnboardingFormValues } from "../lib/schema";

interface Props {
  onSubmit: () => void;
  isSubmitting: boolean;
  error: string | null;
}

export function NameWorkspaceStep({ onSubmit, isSubmitting, error }: Props) {
  const { register, formState: { errors } } = useFormContext<OnboardingFormValues>();
  return (
    <div className="space-y-4">
      <div className="text-center">
        <h1 className="text-[18px] font-semibold">Name your workspace</h1>
        <p className="mt-1 text-[12px] text-muted-foreground">
          You can rename it anytime.
        </p>
      </div>
      <div>
        <input
          type="text"
          placeholder="e.g. Acme Corp"
          autoFocus
          disabled={isSubmitting}
          {...register("tenantName")}
          className="w-full rounded-lg border border-border px-3 py-2 text-[13px]"
        />
        {errors.tenantName && (
          <p className="mt-1 text-[11px] text-destructive">
            {errors.tenantName.message}
          </p>
        )}
        {error && <p className="mt-1 text-[11px] text-destructive">{error}</p>}
      </div>
      <button
        type="button"
        onClick={onSubmit}
        disabled={isSubmitting}
        className="w-full rounded-lg bg-foreground px-5 py-2 text-[12px] font-medium text-background hover:opacity-90 disabled:opacity-50"
      >
        {isSubmitting ? "Creating workspace…" : "Continue"}
      </button>
    </div>
  );
}
