import { createFileRoute } from "@tanstack/react-router";

import { WorkspaceSettingsPage } from "@/features/settings/components/workspace-settings-page";
import { workspaceSearchSchema } from "@/features/settings/lib/settings";

export const Route = createFileRoute("/_app/settings/")({
  validateSearch: workspaceSearchSchema,
  component: RouteComponent,
});

function RouteComponent() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <WorkspaceSettingsPage
      connected={search.connected}
      onClearConnected={() => void navigate({ search: {}, replace: true })}
    />
  );
}
