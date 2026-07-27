// Route-tree smoke test: mounts the REAL generated route tree (mock API
// provider, no-auth mode) and visits every console page, asserting each
// renders identifiable content without throwing. This is the wiring-level
// check the per-feature component tests can't provide — it fails when a
// route imports the wrong page, a validateSearch crashes on defaults, or a
// page explodes against the mock provider it ships with.

import {
  RouterProvider,
  createMemoryHistory,
  createRouter,
} from "@tanstack/react-router";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { routeTree } from "./routeTree.gen";

const ROUTES: Array<{ path: string; expectText: RegExp }> = [
  { path: "/", expectText: /overview|getting started/i },
  { path: "/events", expectText: /events/i },
  { path: "/customers", expectText: /customers/i },
  { path: "/pricing", expectText: /pricing/i },
  { path: "/billing", expectText: /billing/i },
  { path: "/subscriptions", expectText: /subscriptions|plans/i },
  { path: "/referrals", expectText: /referral/i },
  { path: "/webhooks", expectText: /webhook/i },
  { path: "/developers", expectText: /api key|developers/i },
  { path: "/settings", expectText: /workspace|settings/i },
  { path: "/settings/team", expectText: /members|team/i },
  { path: "/settings/products", expectText: /product/i },
  { path: "/settings/billing", expectText: /ubb|billing period|invoice/i },
  { path: "/settings/audit", expectText: /audit/i },
];

// The root route mounts the app's own QueryProvider (singleton query client),
// so RouterProvider alone gives the full runtime composition.
async function renderRoute(path: string) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [path] }),
    context: {
      auth: { isSignedIn: true, isLoaded: true, getToken: async () => null },
    },
  });
  render(<RouterProvider router={router} />);
  return router;
}

describe("router smoke", () => {
  afterEach(cleanup);

  for (const { path, expectText } of ROUTES) {
    it(`renders ${path}`, async () => {
      await renderRoute(path);
      await waitFor(
        () => {
          expect(screen.getAllByText(expectText).length).toBeGreaterThan(0);
        },
        { timeout: 8000 },
      );
    });
  }
});
