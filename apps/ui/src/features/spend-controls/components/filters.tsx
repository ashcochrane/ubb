// The tab's two filters, both wire parameters the report takes: one customer
// (labelled by shortened UUID — the margin list carries no external ids, the
// events ledger's shape) and one family, offered from the registry's own list.

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { controlFamilyLabel } from "@/lib/control-family";
import { shortId } from "@/lib/format";
import { CONTROL_FAMILY_VALUES, type ControlFamily } from "@/lib/vocabulary";

import { useSpendControlCustomers } from "../api/queries";

const EVERY = "every";

export function FamilyFilter({
  value,
  onChange,
}: {
  value: ControlFamily | undefined;
  onChange: (next: ControlFamily | undefined) => void;
}) {
  return (
    <div className="space-y-1">
      <Label className="text-[11px] text-text-muted">Family</Label>
      <Select
        value={value ?? EVERY}
        onValueChange={(next) =>
          onChange(
            typeof next === "string" && next !== EVERY
              ? CONTROL_FAMILY_VALUES.find((family) => family === next)
              : undefined,
          )
        }
      >
        <SelectTrigger className="h-8 w-[190px] text-[12px]" aria-label="Family">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={EVERY}>Every family</SelectItem>
          {CONTROL_FAMILY_VALUES.map((family) => (
            <SelectItem key={family} value={family}>
              {controlFamilyLabel(family)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

const ANY_CUSTOMER = "any";

export function CustomerFilter({
  value,
  onChange,
}: {
  value: string | undefined;
  onChange: (next: string | undefined) => void;
}) {
  const customers = useSpendControlCustomers();
  const rows = customers.data?.customers ?? [];
  return (
    <div className="space-y-1">
      <Label className="text-[11px] text-text-muted">Customer</Label>
      <div className="flex items-center gap-2">
        {customers.isLoading ? (
          <Skeleton className="h-8 w-[200px]" />
        ) : (
          <Select
            value={value ?? ANY_CUSTOMER}
            onValueChange={(next) =>
              onChange(typeof next === "string" && next !== ANY_CUSTOMER ? next : undefined)
            }
          >
            <SelectTrigger className="h-8 w-[200px] text-[12px]" aria-label="Customer">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY_CUSTOMER}>Every customer</SelectItem>
              {rows.map((row) => (
                <SelectItem key={row.customer_id} value={row.customer_id}>
                  <span className="font-mono text-[12px]">{shortId(row.customer_id)}</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        {value !== undefined && (
          <Button variant="ghost" size="sm" onClick={() => onChange(undefined)}>
            Clear
          </Button>
        )}
      </div>
    </div>
  );
}
