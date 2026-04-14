// src/features/onboarding/components/permissions-table.tsx
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { StripePermission } from "../api/types";

interface PermissionsTableProps {
  permissions: StripePermission[];
}

export function PermissionsTable({ permissions }: PermissionsTableProps) {
  return (
    <div className="rounded-lg border border-border">
      <Table className="text-label">
        <TableHeader>
          <TableRow className="border-b border-border hover:bg-transparent">
            <TableHead className="h-auto px-3 py-2 text-left font-medium text-muted-foreground">
              Resource
            </TableHead>
            <TableHead className="h-auto px-3 py-2 text-left font-medium text-muted-foreground">
              Permission
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {permissions.map((p) => (
            <TableRow
              key={p.resource}
              className="border-b border-border/50 last:border-0 hover:bg-transparent"
            >
              <TableCell className="px-3 py-1.5">{p.resource}</TableCell>
              <TableCell className="px-3 py-1.5">
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-muted font-medium",
                    p.access === "Read" &&
                      "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400",
                    p.access === "Write" &&
                      "bg-purple-50 text-purple-700 dark:bg-purple-900/20 dark:text-purple-400",
                    p.access === "None" && "bg-muted text-muted-foreground",
                  )}
                >
                  {p.access}
                </span>
                {p.description && (
                  <span className="ml-2 text-muted text-muted-foreground">
                    {p.description}
                  </span>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
