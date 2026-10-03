import { createFileRoute } from "@tanstack/react-router";

import { CodeBuilderPage } from "@/features/developers/components/code-builder-page";
import { codeBuilderSearchSchema } from "@/features/developers/lib/code-builder-search";

export const Route = createFileRoute("/_app/developers/code-builder")({
  validateSearch: codeBuilderSearchSchema,
  component: RouteComponent,
});

function RouteComponent() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <CodeBuilderPage
      search={search}
      onSearchChange={(next) => void navigate({ search: next, replace: true })}
    />
  );
}
