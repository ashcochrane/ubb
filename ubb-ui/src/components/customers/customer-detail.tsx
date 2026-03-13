import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/format";
import type { Customer } from "./columns";

interface CustomerDetailProps {
  customer: Customer;
}

export function CustomerDetail({ customer }: CustomerDetailProps) {
  const statusVariant =
    customer.status === "active"
      ? "default"
      : customer.status === "suspended"
        ? "secondary"
        : "destructive";

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="text-sm text-muted-foreground">External ID</p>
            <p className="font-medium">{customer.external_id}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Status</p>
            <Badge variant={statusVariant}>{customer.status}</Badge>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Created</p>
            <p className="font-medium">{formatDate(customer.created_at)}</p>
          </div>
          {customer.stripe_customer_id && (
            <div>
              <p className="text-sm text-muted-foreground">
                Stripe Customer ID
              </p>
              <p className="font-mono text-sm">
                {customer.stripe_customer_id}
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Metadata</CardTitle>
        </CardHeader>
        <CardContent>
          {customer.metadata &&
          Object.keys(customer.metadata).length > 0 ? (
            <pre className="rounded-md bg-muted p-4 text-sm overflow-auto">
              {JSON.stringify(customer.metadata, null, 2)}
            </pre>
          ) : (
            <p className="text-sm text-muted-foreground">No metadata</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
