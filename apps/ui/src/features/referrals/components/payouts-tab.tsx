import { Coins } from "lucide-react";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Section,
  QueryState,
  CopyField,
} from "@/components/shared/data-states";
import { formatMicros, formatDate } from "@/lib/format";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { usePayoutExport } from "../api/queries";

export function PayoutsTab() {
  const { defaultCurrency } = useAuth();
  const query = usePayoutExport();

  return (
    <div className="space-y-4">
      <Alert>
        <Coins />
        <AlertDescription>
          A point-in-time snapshot of amounts owed to each referrer — the same
          data you would hand to finance for a payout run. Rewards keep accruing
          after export.
        </AlertDescription>
      </Alert>

      <QueryState
        query={query}
        isEmpty={(d) => d.data.length === 0}
        empty={{
          title: "Nothing to pay out",
          description: "No referrer has accrued rewards yet.",
        }}
      >
        {(data) => (
          <Section
            title="Payout export"
            description={`${data.referrer_count} referrer(s) · exported ${formatDate(data.exported_at)}`}
            actions={
              <span className="text-sm font-medium">
                Total {formatMicros(data.total_payout_micros, defaultCurrency)}
              </span>
            }
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Referrer</TableHead>
                  <TableHead>Code</TableHead>
                  <TableHead className="text-right">Referrals</TableHead>
                  <TableHead className="text-right">Active</TableHead>
                  <TableHead className="text-right">Referred spend</TableHead>
                  <TableHead className="text-right">Payout</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.data.map((row) => (
                  <TableRow key={row.referrer_customer_id}>
                    <TableCell>
                      <div className="font-medium">{row.external_id || "—"}</div>
                      <div className="font-mono text-xs text-muted-foreground">
                        {row.referrer_customer_id}
                      </div>
                    </TableCell>
                    <TableCell className="max-w-[12rem]">
                      <CopyField value={row.referral_code} />
                    </TableCell>
                    <TableCell className="text-right">{row.referral_count}</TableCell>
                    <TableCell className="text-right">
                      {row.active_referral_count}
                    </TableCell>
                    <TableCell className="text-right">
                      {formatMicros(row.total_referred_spend_micros, defaultCurrency)}
                    </TableCell>
                    <TableCell className="text-right font-medium">
                      {formatMicros(row.total_earned_micros, defaultCurrency)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Section>
        )}
      </QueryState>
    </div>
  );
}
