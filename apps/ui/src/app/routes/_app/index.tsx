import { createFileRoute } from "@tanstack/react-router";

import { OverviewPage } from "@/features/dashboard/components/overview-page";
import { dateRangeSearchSchema } from "@/lib/date-range";

export const Route = createFileRoute("/_app/")({
  validateSearch: dateRangeSearchSchema,
  component: RouteComponent,
});

function RouteComponent() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <OverviewPage
      search={search}
      onSearchChange={(next) => void navigate({ search: next, replace: true })}
    />
  );
}
