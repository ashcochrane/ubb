import { createFileRoute } from "@tanstack/react-router";

import { RunsPage } from "@/features/tasks/components/runs-page";
import { runsSearchSchema } from "@/features/tasks/lib/runs";

export const Route = createFileRoute("/_app/tasks/runs/")({
  validateSearch: runsSearchSchema,
  component: RouteComponent,
});

function RouteComponent() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <RunsPage
      search={search}
      onSearchChange={(next) => void navigate({ search: next, replace: true })}
    />
  );
}
