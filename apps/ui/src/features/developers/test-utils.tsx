// Test-only render helpers for the developers feature.
//
// The Code Builder's links are routed — a kind of work is a page of its own,
// and the round trip goes there and back — so the page is mounted inside a
// real memory router whose other routes render nothing. Its URL state is held
// the way the route holds it: the search the page last asked for, parsed by
// the same schema, so a test reads exactly what a reload would.

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
import { useState, type ReactNode } from "react";

import { CodeBuilderPage } from "./components/code-builder-page";
import { codeBuilderSearchSchema, type CodeBuilderSearch } from "./lib/code-builder-search";

/** The screens the page links to, present so a link resolves. */
const STUB_PATHS = [
  "/developers",
  "/developers/code-builder",
  "/tasks",
  "/tasks/kinds/$key",
  "/pricing",
  "/webhooks",
  "/settings/audit",
];

export interface MountedBuilder {
  /** Every search the page asked for, in order — the URL's history. */
  readonly searches: CodeBuilderSearch[];
  /** The search the page is showing now. */
  current(): CodeBuilderSearch;
  /** True once the signed-in member's role has been resolved, whatever it is. */
  roleResolved(): boolean;
}

function routerAround(Index: () => ReactNode) {
  const rootRoute = createRootRoute({ component: Outlet });
  const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", component: Index });
  const stubs = STUB_PATHS.map((path) =>
    createRoute({ getParentRoute: () => rootRoute, path, component: () => null }),
  );
  return createRouter({
    routeTree: rootRoute.addChildren([indexRoute, ...stubs]),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });
}

function aQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

/** Any piece of the page, inside a router whose link targets exist. */
export function renderInRouter(ui: ReactNode) {
  const router = routerAround(() => <>{ui}</>);
  render(
    <QueryClientProvider client={aQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

export function renderCodeBuilder(initial: CodeBuilderSearch = {}): MountedBuilder {
  const searches: CodeBuilderSearch[] = [codeBuilderSearchSchema.parse(initial)];

  function Builder() {
    const [search, setSearch] = useState(searches[0] ?? {});
    return (
      <CodeBuilderPage
        search={search}
        onSearchChange={(next) => {
          // Through the schema, as the route's `validateSearch` would read it
          // back after the navigation.
          const parsed = codeBuilderSearchSchema.parse(next);
          searches.push(parsed);
          setSearch(parsed);
        }}
      />
    );
  }

  const queryClient = aQueryClient();
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={routerAround(Builder)} />
    </QueryClientProvider>,
  );
  return {
    searches,
    current: () => searches[searches.length - 1] ?? {},
    roleResolved: () => {
      const roles = queryClient.getQueryCache().findAll({ queryKey: ["tenant", "current-role"] });
      return roles.length > 0 && roles.every((query) => query.state.status === "success");
    },
  };
}
