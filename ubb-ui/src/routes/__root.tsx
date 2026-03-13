import { createRootRouteWithContext, Outlet, Link } from "@tanstack/react-router";
import type { useAuth } from "@clerk/react";
import { buttonVariants } from "@/components/ui/button";

interface RouterContext {
  auth: ReturnType<typeof useAuth>;
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: () => <Outlet />,
  notFoundComponent: NotFound,
});

function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4">
      <h1 className="text-4xl font-bold">404</h1>
      <p className="text-muted-foreground">Page not found.</p>
      <Link to="/" className={buttonVariants({ variant: "default" })}>
        Go home
      </Link>
    </div>
  );
}
