import { Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/shared/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useCustomers } from "../api/queries";
import { CustomerCreateDialog } from "./customer-create-dialog";

export function CustomersPage() {
  const { data, isLoading } = useCustomers();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Customers"
        description="Customers your SDK sends usage for."
        actions={<CustomerCreateDialog />}
      />

      {isLoading || !data ? (
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : data.data.length === 0 ? (
        <div className="rounded-lg border border-dashed p-12 text-center text-sm text-muted-foreground">
          No customers yet. Click{" "}
          <span className="font-medium">New customer</span> to add one.
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>External ID</TableHead>
              <TableHead>Stripe ID</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.data.map((c) => (
              <TableRow key={c.id}>
                <TableCell>
                  <Link
                    to="/customers/$customerId"
                    params={{ customerId: c.id }}
                    className="font-medium hover:underline"
                  >
                    {c.externalId}
                  </Link>
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {c.stripeCustomerId || "—"}
                </TableCell>
                <TableCell>{c.status}</TableCell>
                <TableCell className="text-muted-foreground">
                  {new Date(c.createdAt).toLocaleDateString()}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
