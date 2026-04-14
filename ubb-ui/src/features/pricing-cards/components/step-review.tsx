import { useState } from "react";
import { useFormContext } from "react-hook-form";
import { Check, AlertTriangle } from "lucide-react";
import type { WizardFormValues } from "../lib/schema";
import { useNavigate } from "@tanstack/react-router";
import { useCreateCard } from "../api/queries";
import { DryRunSimulator } from "./dry-run-simulator";
import { IntegrationSnippet } from "./integration-snippet";
import { cn } from "@/lib/utils";
import { formatPrice } from "@/lib/format";

export function StepReview() {
  const { watch, getValues } = useFormContext<WizardFormValues>();
  const navigate = useNavigate();
  const createCard = useCreateCard();
  const [showConfirm, setShowConfirm] = useState(false);
  const [activated, setActivated] = useState(false);

  const name = watch("name");
  const provider = watch("provider");
  const cardId = watch("cardId");
  const dimensions = watch("dimensions");

  const checks = [
    { label: "All dimensions have non-zero prices", pass: dimensions.every((d) => d.price > 0) },
    { label: "No duplicate metric keys", pass: new Set(dimensions.map((d) => d.key)).size === dimensions.length },
    { label: "Unit prices within expected ranges", pass: dimensions.every((d) => d.type === "flat" ? d.price <= 100 : d.price <= 1) },
    { label: "Card ID is valid", pass: cardId.length > 0 && /^[a-z0-9_]+$/.test(cardId) },
  ];

  const buildRequest = (status: "active" | "draft") => {
    const values = getValues();
    return {
      name: values.name,
      cardId: values.cardId,
      provider: values.provider,
      pricingPattern: values.pricingPattern,
      dimensions: values.dimensions,
      description: values.description,
      pricingSourceUrl: values.pricingSourceUrl,
      product: values.product,
      status,
    };
  };

  const handleActivate = async () => {
    await createCard.mutateAsync(buildRequest("active"));
    setActivated(true);
    setShowConfirm(false);
  };

  const handleSaveDraft = async () => {
    await createCard.mutateAsync(buildRequest("draft"));
    navigate({ to: "/pricing-cards" });
  };

  if (activated) {
    return (
      <div className="space-y-5 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-green-light">
          <Check className="h-6 w-6 text-green-text" />
        </div>
        <h2 className="text-[16px] font-medium">{name} is live</h2>
        <p className="text-[12px] text-muted-foreground">
          Your card is now actively calculating costs for every event sent to{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-label">{cardId}</code>
        </p>
        <IntegrationSnippet />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-md border border-border bg-bg-surface px-4 py-3.5">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-[15px] font-medium">{name}</div>
            <div className="text-label text-muted-foreground">
              {provider} <span className="font-mono">{cardId}</span>
            </div>
          </div>
          <span className="rounded-full bg-amber-light px-2 py-0.5 text-muted text-amber-text">
            Draft v1
          </span>
        </div>

        <div className="my-3 border-t border-border" />

        <div className="mb-1 text-label text-muted-foreground">
          Cost dimensions ({dimensions.length})
        </div>
        <div className="divide-y divide-border">
          {dimensions.map((d) => (
            <div key={d.key} className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-4 py-1.5">
              <span className="font-mono text-label">{d.key}</span>
              <span className="rounded-full bg-muted px-2 py-0.5 text-muted">{d.type === "per_unit" ? "per unit" : "flat"}</span>
              <span className="text-label text-muted-foreground">{d.unit}</span>
              <span className="font-mono text-[12px] font-medium">{d.displayPrice || formatPrice(d.price * 1_000_000, d.type === "per_unit" ? 1_000_000 : 1, d.unit)}</span>
            </div>
          ))}
        </div>
      </div>

      <DryRunSimulator />

      <div className="space-y-1.5">
        {checks.map((c) => (
          <div key={c.label} className="flex items-center gap-2">
            <div className={cn(
              "flex h-4 w-4 items-center justify-center rounded-full",
              c.pass ? "bg-green-light" : "bg-amber-light",
            )}>
              {c.pass
                ? <Check className="h-2.5 w-2.5 text-green-text" />
                : <AlertTriangle className="h-2.5 w-2.5 text-amber-text" />}
            </div>
            <span className="text-[12px]">{c.label}</span>
          </div>
        ))}
      </div>

      <IntegrationSnippet />

      {!showConfirm && (
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={handleSaveDraft}
            disabled={createCard.isPending}
            className="rounded-md border border-border px-4 py-1.5 text-[12px] text-muted-foreground hover:bg-accent disabled:opacity-50"
          >
            {createCard.isPending ? "Saving..." : "Save as draft"}
          </button>
          <button
            type="button"
            onClick={() => setShowConfirm(true)}
            className="rounded-md bg-green px-5 py-1.5 text-[12px] font-medium text-text-inverse hover:opacity-90"
          >
            Activate card
          </button>
        </div>
      )}

      {showConfirm && (
        <div className="rounded-md border-2 border-green p-4 text-center">
          <h3 className="text-[14px] font-medium">Activate this card?</h3>
          <p className="mt-1 text-label text-muted-foreground">
            Once active, this card will calculate real costs for every matching usage event. You can create new versions later.
          </p>
          <div className="mt-3 flex justify-center gap-2">
            <button
              type="button"
              onClick={() => setShowConfirm(false)}
              className="rounded-md border border-border px-4 py-1.5 text-[12px] text-muted-foreground hover:bg-accent"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleActivate}
              disabled={createCard.isPending}
              className="rounded-md bg-green px-4 py-1.5 text-[12px] font-medium text-text-inverse hover:opacity-90 disabled:opacity-50"
            >
              {createCard.isPending ? "Activating..." : "Yes, activate"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
