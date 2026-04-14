import { createRootRouteWithContext, Outlet } from "@tanstack/react-router";
import { QueryProvider } from "@/app/providers/query-provider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { NotFound } from "@/components/shared/not-found";
import { RouteError } from "@/components/shared/route-error";
import { Toaster } from "sonner";

interface RouterContext {
  auth: {
    isSignedIn: boolean | undefined;
    isLoaded: boolean;
    getToken: () => Promise<string | null>;
  };
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: RootLayout,
  errorComponent: RootError,
  notFoundComponent: NotFound,
});

function RootLayout() {
  return (
    <QueryProvider>
      <TooltipProvider>
        <Outlet />
        <Toaster position="bottom-right" />
      </TooltipProvider>
    </QueryProvider>
  );
}

function RootError({ error, reset }: { error: Error; reset: () => void }) {
  return <RouteError error={error} reset={reset} />;
}
