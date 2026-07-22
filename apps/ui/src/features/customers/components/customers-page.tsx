import { useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { Plus, Users, Search, ChevronRight } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Section, QueryState } from "@/components/shared/data-states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { formatMicros, formatPercent } from "@/lib/format";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { useMarginRoster } from "../api/queries";
import { CustomerCreateDialog } from "./customer-create-dialog";

export function CustomersPage() {
  const { isBillingMode } = useAuth();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Customers"
        description="Create customers, look them up, and manage their wallet, pricing, usage, and subscription."
        actions={
          <CustomerCreateDialog
            trigger={
              <Button size="sm">
                <Plus />
                New customer
              </Button>
            }
          />
        }
      />

      <LookupBar />

      {isBillingMode ? (
        <RosterTable />
      ) : (
        <Alert>
          <Users />
          <AlertTitle>No customer directory endpoint</AlertTitle>
          <AlertDescription>
            The API doesn't expose a customer list for metering-only tenants. Use the lookup above to open a
            customer by ID, or create a new one. (When billing is enabled, customers with activity appear here
            automatically.)
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}

function LookupBar() {
  const navigate = useNavigate();
  const [value, setValue] = useState("");
  const go = () => {
    const id = value.trim();
    if (id) navigate({ to: "/customers/$customerId", params: { customerId: id } });
  };
  return (
    <div className="flex items-center gap-2">
      <div className="relative max-w-md flex-1">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          className="pl-8"
          placeholder="Open a customer by ID…"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && go()}
        />
      </div>
      <Button variant="outline" size="sm" onClick={go} disabled={!value.trim()}>
        Open
      </Button>
    </div>
  );
}

function RosterTable() {
  const query = useMarginRoster();
  return (
    <Section
      title="Customers with activity"
      description="Sourced from margin data for the current period."
    >
      <QueryState
        query={query}
        isEmpty={(d) => d.customers.length === 0}
        empty={{
          title: "No customers with activity yet",
          description: "Once customers record usage or revenue, they'll appear here. Create one to get started.",
        }}
      >
        {(data) => (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Customer ID</TableHead>
                <TableHead className="text-right">Usage revenue</TableHead>
                <TableHead className="text-right">Provider cost</TableHead>
                <TableHead className="text-right">Gross margin</TableHead>
                <TableHead className="text-right">Margin %</TableHead>
                <TableHead className="w-8" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.customers.map((c) => (
                <TableRow key={c.customer_id}>
                  <TableCell className="font-mono text-xs">
                    <Link
                      to="/customers/$customerId"
                      params={{ customerId: c.customer_id }}
                      className="hover:underline"
                    >
                      {c.customer_id}
                    </Link>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMicros(c.usage_revenue_micros)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {formatMicros(c.provider_cost_micros)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMicros(c.gross_margin_micros)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatPercent(c.margin_percentage)}
                  </TableCell>
                  <TableCell>
                    <Link to="/customers/$customerId" params={{ customerId: c.customer_id }}>
                      <ChevronRight className="size-4 text-muted-foreground" />
                    </Link>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </QueryState>
    </Section>
  );
}
