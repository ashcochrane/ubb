import * as React from "react";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import {
  PRODUCTS,
  billingModeLabel,
  productDescription,
  productLabel,
  type Product,
} from "@/lib/labels";
import { toastOnError, toastSuccess } from "@/lib/mutations";

import { useUpdateTenantConfig } from "../api/queries";
import type { TenantConfig } from "../api/types";

export function ProductsCard({
  config,
  isAdmin,
}: {
  config: TenantConfig;
  isAdmin: boolean;
}) {
  const mutation = useUpdateTenantConfig();
  const [pending, setPending] = React.useState<{
    product: Product;
    enable: boolean;
  } | null>(null);

  const modeNeedsBilling =
    config.billing_mode === "prepaid" || config.billing_mode === "postpaid";

  const confirm = () => {
    if (!pending) return;
    const { product, enable } = pending;
    const next = enable
      ? [...config.products, product]
      : config.products.filter((p) => p !== product);
    mutation.mutate(
      { products: next },
      {
        onSuccess: () => {
          setPending(null);
          toastSuccess(
            enable
              ? `${productLabel(product)} enabled`
              : `${productLabel(product)} disabled`,
          );
        },
        onError: (error) => {
          setPending(null);
          toastOnError("Couldn't update products")(error);
        },
      },
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Products</CardTitle>
        <CardDescription>
          What this workspace can do. Disabling a product hides its console
          sections and turns off its API — data is always preserved.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-2 sm:grid-cols-2">
        {PRODUCTS.map((product) => {
          const enabled = config.products.includes(product);
          const isMetering = product === "metering";
          const billingLockedByMode =
            product === "billing" && enabled && modeNeedsBilling;
          return (
            <div
              key={product}
              className="flex items-start justify-between gap-3 rounded-lg border border-border p-3"
            >
              <div>
                <p className="text-sm font-medium">{productLabel(product)}</p>
                <p className="text-[13px] text-muted-foreground">
                  {productDescription(product)}
                </p>
                {isMetering && (
                  <p className="mt-1 text-[12px] text-muted-foreground">
                    Always on — the platform core can't be disabled.
                  </p>
                )}
                {billingLockedByMode && (
                  <p className="mt-1 text-[12px] text-muted-foreground">
                    In use by the {billingModeLabel(config.billing_mode)}{" "}
                    billing mode — switch to Meter only first.
                  </p>
                )}
                {product === "metering_async" && (
                  <p className="mt-1 text-[12px] text-muted-foreground">
                    Only gates the high-throughput ingest endpoint.
                  </p>
                )}
              </div>
              <Switch
                checked={enabled}
                aria-label={productLabel(product)}
                disabled={
                  !isAdmin ||
                  isMetering ||
                  billingLockedByMode ||
                  mutation.isPending
                }
                onCheckedChange={(checked: boolean) =>
                  setPending({ product, enable: checked })
                }
              />
            </div>
          );
        })}
      </CardContent>

      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(open) => {
          if (!open) setPending(null);
        }}
        title={
          pending
            ? `${pending.enable ? "Enable" : "Disable"} ${productLabel(pending.product)}?`
            : "Change products?"
        }
        description={
          pending
            ? pending.enable
              ? `${productDescription(pending.product)} Its console sections and API become available immediately.`
              : `Its console sections disappear for everyone and its API starts answering "feature not enabled" errors immediately. Data is preserved — you can re-enable it at any time.`
            : ""
        }
        confirmLabel={pending?.enable ? "Enable" : "Disable"}
        destructive={pending ? !pending.enable : false}
        pending={mutation.isPending}
        onConfirm={confirm}
      />
    </Card>
  );
}
