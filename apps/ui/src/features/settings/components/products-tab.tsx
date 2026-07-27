import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Section } from "@/components/shared/data-states";
import { StatusBadge } from "@/components/shared/status-badge";
import { CheckboxRow } from "./checkbox-row";
import { useUpdateConfig } from "../api/queries";
import type { TenantConfig } from "../api/types";

const AVAILABLE_PRODUCTS = [
  { key: "metering", label: "Metering", description: "Usage recording, pricing, and rate cards." },
  { key: "billing", label: "Billing", description: "Wallets, top-ups, credit drawdown, and invoicing." },
  { key: "subscriptions", label: "Subscriptions", description: "Stripe subscription sync and unit economics." },
  { key: "referrals", label: "Referrals", description: "Referral programs, attribution, and payouts." },
] as const;

export function ProductsTab({ config }: { config: TenantConfig }) {
  const update = useUpdateConfig();
  const [selected, setSelected] = useState<string[]>(config.products);

  const toggle = (key: string, on: boolean) =>
    setSelected((prev) =>
      on ? [...new Set([...prev, key])] : prev.filter((p) => p !== key),
    );

  const dirty =
    selected.length !== config.products.length ||
    selected.some((p) => !config.products.includes(p));

  const save = () => update.mutate({ products: selected });

  return (
    <Section
      title="Product access"
      description="Enable the products this tenant can use. Disabling a product hides its area and blocks its API namespace."
      actions={
        <Button
          size="sm"
          onClick={save}
          disabled={!dirty || update.isPending}
        >
          {update.isPending ? "Saving…" : "Save products"}
        </Button>
      }
    >
      <div className="flex flex-col gap-3">
        {AVAILABLE_PRODUCTS.map((product) => {
          const enabled = selected.includes(product.key);
          return (
            <div
              key={product.key}
              className="flex items-center justify-between gap-4 rounded-lg border border-border px-3 py-2.5"
            >
              <CheckboxRow
                checked={enabled}
                onChange={(on) => toggle(product.key, on)}
                label={product.label}
                description={product.description}
              />
              <StatusBadge
                value={enabled ? "Enabled" : "Available"}
                tone={enabled ? "solid" : "muted"}
              />
            </div>
          );
        })}
      </div>
    </Section>
  );
}
