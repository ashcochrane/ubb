import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import { formatMarkup, formatMicros, type Plan } from "../api/types";

/**
 * An absent fee axis renders as an em dash, not "$0.00" — the plan does not
 * charge it, which is different from charging zero.
 */
function Fee({ micros, suffix }: { micros: number; suffix: string }) {
  if (micros === 0) return <span className="text-muted-foreground">—</span>;
  return (
    <>
      {formatMicros(micros)}
      {suffix}
    </>
  );
}

export function PlansTable({
  plans,
  onEdit,
}: {
  plans: Plan[];
  onEdit: (plan: Plan) => void;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Plan</TableHead>
          <TableHead>Access</TableHead>
          <TableHead>Per seat</TableHead>
          <TableHead>Markup</TableHead>
          <TableHead />
        </TableRow>
      </TableHeader>
      <TableBody>
        {plans.map((plan) => (
          <TableRow key={plan.id}>
            <TableCell className="font-medium">{plan.name}</TableCell>
            <TableCell>
              <Fee
                micros={plan.access_fee_micros}
                suffix={plan.interval === "year" ? "/yr" : "/mo"}
              />
            </TableCell>
            <TableCell>
              <Fee micros={plan.per_seat_micros} suffix="/seat" />
            </TableCell>
            <TableCell>{formatMarkup(plan.markup_percentage_micros)}</TableCell>
            <TableCell>
              <button
                type="button"
                onClick={() => onEdit(plan)}
                className="text-sm underline underline-offset-2"
              >
                Edit
              </button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
