import React from "react";
import ReactDOM from "react-dom/client";
import { ClerkProvider, useAuth } from "@clerk/react";
import { RouterProvider, createRouter } from "@tanstack/react-router";
import { routeTree } from "./app/routeTree.gen";
import { setAuthTokenGetter } from "./api/client";
import "./styles/app.css";

import { API_PROVIDER } from "./lib/api-provider";

const clerkPubKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;
const noAuthMode = !clerkPubKey && API_PROVIDER === "mock";

const router = createRouter({
  routeTree,
  context: { auth: undefined! },
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

/** Wraps the router with Clerk auth context. */
function ClerkApp() {
  const auth = useAuth();
  const { isSignedIn, isLoaded, getToken } = auth;

  React.useEffect(() => {
    setAuthTokenGetter(() => getToken());
  }, [getToken]);

  const authContext = React.useMemo(
    () => ({ auth: { isSignedIn, isLoaded, getToken } }),
    [isSignedIn, isLoaded, getToken],
  );

  if (!isLoaded) return null;

  return <RouterProvider router={router} context={authContext} />;
}

/** No Clerk — renders the router directly with faked auth. */
function NoAuthApp() {
  const authContext = React.useMemo(
    () => ({
      auth: {
        isSignedIn: true,
        isLoaded: true,
        getToken: async () => null,
      },
    }),
    [],
  );
  return <RouterProvider router={router} context={authContext} />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {noAuthMode ? (
      <NoAuthApp />
    ) : (
      <ClerkProvider publishableKey={clerkPubKey!}>
        <ClerkApp />
      </ClerkProvider>
    )}
  </React.StrictMode>,
);
