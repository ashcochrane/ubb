import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useCustomers } from "@/api/hooks/use-customers";
import { CustomersTable } from "@/components/customers/customers-table";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export const Route = createFileRoute("/_authenticated/customers/")({
  component: CustomersPage,
});

function CustomersPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<string>("all");

  const { data, isLoading } = useCustomers({
    search: search || undefined,
    status: status === "all" ? undefined : status,
  });

  const customers = data?.results ?? data?.items ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Customers</h1>
        <p className="text-muted-foreground">
          Manage your customers and view their details.
        </p>
      </div>

      <div className="flex items-center gap-4">
        <Input
          placeholder="Search customers..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-sm"
        />
        <Select value={status} onValueChange={(v) => setStatus(v ?? "all")}>
          <SelectTrigger className="w-[140px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Statuses</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="suspended">Suspended</SelectItem>
            <SelectItem value="deleted">Deleted</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <CustomersTable data={customers} isLoading={isLoading} />
    </div>
  );
}
