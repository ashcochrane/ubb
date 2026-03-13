import { type ColumnDef } from "@tanstack/react-table";
import { Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/format";
import { Link } from "@tanstack/react-router";

export type Customer = {
  id: string;
  external_id: string;
  status: string;
  stripe_customer_id: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export const columns: ColumnDef<Customer>[] = [
  {
    accessorKey: "external_id",
    header: "External ID",
    cell: ({ row }) => (
      <Link
        to="/customers/$customerId"
        params={{ customerId: row.original.id }}
        className="font-medium hover:underline"
      >
        {row.getValue("external_id")}
      </Link>
    ),
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => {
      const status = row.getValue("status") as string;
      const variant =
        status === "active"
          ? "default"
          : status === "suspended"
            ? "secondary"
            : "destructive";
      return <Badge variant={variant}>{status}</Badge>;
    },
  },
  {
    accessorKey: "created_at",
    header: "Created",
    cell: ({ row }) => formatDate(row.getValue("created_at")),
  },
];
