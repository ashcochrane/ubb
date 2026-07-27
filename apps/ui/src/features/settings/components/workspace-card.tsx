import * as React from "react";

import { problemMessage } from "@/api/problem";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toastSuccess } from "@/lib/mutations";

import { useUpdateTenantConfig } from "../api/queries";
import type { TenantConfig } from "../api/types";
import { SUPPORTED_CURRENCIES } from "../lib/settings";

export function WorkspaceCard({
  config,
  isAdmin,
}: {
  config: TenantConfig;
  isAdmin: boolean;
}) {
  const mutation = useUpdateTenantConfig();
  const [currency, setCurrency] = React.useState(config.default_currency);
  React.useEffect(() => {
    setCurrency(config.default_currency);
  }, [config.default_currency]);

  const currencyDirty = currency !== config.default_currency;
  const selected = SUPPORTED_CURRENCIES.find((c) => c.code === currency);

  const saveCurrency = () => {
    mutation.mutate(
      { default_currency: currency },
      {
        onSuccess: () => toastSuccess("Workspace currency updated"),
      },
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Workspace</CardTitle>
        <CardDescription>
          The basics of this workspace on UBB.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium">Name</p>
            <p className="text-[13px] text-muted-foreground">
              The workspace name can't be changed from the console.
            </p>
          </div>
          <p className="text-sm">{config.name}</p>
        </div>

        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium">Status</p>
            <p className="text-[13px] text-muted-foreground">
              Inactive workspaces stop accepting API traffic.
            </p>
          </div>
          <Badge variant={config.is_active ? "secondary" : "destructive"}>
            {config.is_active ? "Active" : "Inactive"}
          </Badge>
        </div>

        <div className="flex flex-col gap-2">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium">Currency</p>
              <p className="max-w-sm text-[13px] text-muted-foreground">
                Every balance, price, and invoice uses this one currency. It
                locks permanently the first time any money is recorded.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Select
                value={currency}
                onValueChange={(value: string | null) => {
                  if (value !== null) setCurrency(value);
                }}
              >
                <SelectTrigger
                  aria-label="Workspace currency"
                  disabled={!isAdmin || mutation.isPending}
                  className="w-[220px]"
                >
                  <SelectValue>
                    {selected
                      ? `${selected.code.toUpperCase()} — ${selected.name}`
                      : currency.toUpperCase()}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {SUPPORTED_CURRENCIES.map((c) => (
                    <SelectItem key={c.code} value={c.code}>
                      {c.code.toUpperCase()} — {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {currencyDirty && (
                <Button
                  size="sm"
                  onClick={saveCurrency}
                  disabled={!isAdmin || mutation.isPending}
                >
                  {mutation.isPending ? "Working…" : "Save"}
                </Button>
              )}
            </div>
          </div>
          {mutation.isError && (
            <p className="text-right text-xs text-destructive">
              {problemMessage(mutation.error)}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
