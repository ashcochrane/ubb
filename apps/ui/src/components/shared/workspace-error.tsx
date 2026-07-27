import { AlertTriangle } from "lucide-react";

import { ApiProblem, problemMessage } from "@/api/problem";
import { Button } from "@/components/ui/button";
import { noAuthMode, useAuthUser } from "@/hooks/use-auth";
import { tenantConfigQueryOptions } from "@/hooks/use-tenant-config";
import { queryClient } from "@/lib/query-client";

/**
 * Full-screen state when the workspace bootstrap (GET /tenant/config) fails —
 * the console can't render anything meaningful without it.
 */
export function WorkspaceError({ error }: { error: Error }) {
  const { signOut } = useAuthUser();

  const isAuthProblem =
    error instanceof ApiProblem && (error.status === 401 || error.status === 403);

  const retry = async () => {
    await queryClient.invalidateQueries({
      queryKey: tenantConfigQueryOptions.queryKey,
    });
    window.location.reload();
  };

  return (
    <div className="flex h-screen items-center justify-center bg-bg-page p-6">
      <div className="w-full max-w-md rounded-lg border border-border bg-bg-surface p-8 text-center">
        <AlertTriangle className="mx-auto h-8 w-8 text-text-muted" strokeWidth={1.5} />
        <h1 className="mt-4 text-lg font-semibold text-text-primary">
          {isAuthProblem ? "Workspace unavailable" : "Couldn't load your workspace"}
        </h1>
        <p className="mt-2 text-sm text-text-secondary">
          {isAuthProblem
            ? "Your account isn't linked to an active workspace, or your access has been removed. If you were just invited, ask an admin to confirm the invitation."
            : problemMessage(error)}
        </p>
        <div className="mt-6 flex justify-center gap-2">
          <Button variant="outline" onClick={retry}>
            Try again
          </Button>
          {!noAuthMode && (
            <Button variant="ghost" onClick={signOut}>
              Sign out
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
