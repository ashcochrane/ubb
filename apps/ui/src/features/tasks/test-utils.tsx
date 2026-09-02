// Test-only render helper: the tasks pages use <Link> — a kind of work is a
// ROUTED object and its price is a LINK into the book — so tests mount them
// inside a real memory router whose other routes render nothing. Navigation
// targets exist; the content under test lives at "/".

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";

export function renderWithProviders(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const rootRoute = createRootRoute({ component: Outlet });
  const indexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: "/",
    component: () => <>{ui}</>,
  });
  const stubPaths = [
    "/tasks",
    "/tasks/kinds/$key",
    "/tasks/runs",
    "/tasks/runs/$taskId",
    "/pricing",
  ];
  const stubs = stubPaths.map((path) =>
    createRoute({ getParentRoute: () => rootRoute, path, component: () => null }),
  );
  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute, ...stubs]),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

/**
 * The class the destructive Badge variant carries, and only it. The Badge's
 * base class names the destructive colour for `aria-invalid` states on EVERY
 * variant, so a bare `/destructive/` match finds every badge; a test asserting
 * a state is — or is not — drawn as a failure matches this instead.
 */
export const DRAWN_AS_FAILURE = /(^|\s)text-destructive(\s|$)/;
