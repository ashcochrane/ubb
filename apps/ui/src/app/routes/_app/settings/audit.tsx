import { createFileRoute } from "@tanstack/react-router";

import { AuditLogPage } from "@/features/settings/components/audit-log-page";
import { auditSearchSchema } from "@/features/settings/lib/settings";

export const Route = createFileRoute("/_app/settings/audit")({
  validateSearch: auditSearchSchema,
  component: RouteComponent,
});

function RouteComponent() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <AuditLogPage
      search={search}
      onSearchChange={(next) => void navigate({ search: next, replace: true })}
    />
  );
}
