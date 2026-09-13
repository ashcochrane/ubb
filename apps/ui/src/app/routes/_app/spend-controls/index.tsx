import { createFileRoute } from "@tanstack/react-router";

import { SpendControlsPage } from "@/features/spend-controls/components/spend-controls-page";
import { spendControlsSearchSchema } from "@/features/spend-controls/lib/search";

export const Route = createFileRoute("/_app/spend-controls/")({
  validateSearch: spendControlsSearchSchema,
  component: RouteComponent,
});

function RouteComponent() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <SpendControlsPage
      search={search}
      onSearchChange={(next) => void navigate({ search: next, replace: true })}
    />
  );
}
