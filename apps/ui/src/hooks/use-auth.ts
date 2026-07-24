// Console identity: Clerk in real deployments, a faked session in no-auth
// dev mode (blank VITE_CLERK_PUBLISHABLE_KEY + mock API provider).
//
// `noAuthMode` is an env-derived constant, so choosing a hook implementation
// at module scope is safe (the choice can never change within a session).

import { useAuth as useClerkAuth, useUser } from "@clerk/react";

import { API_PROVIDER } from "@/lib/api-provider";

export const noAuthMode =
  !import.meta.env.VITE_CLERK_PUBLISHABLE_KEY && API_PROVIDER === "mock";

export interface AuthUser {
  email: string;
  name: string;
  signOut: () => void;
}

function useClerkAuthUser(): AuthUser {
  const { user } = useUser();
  const { signOut } = useClerkAuth();
  return {
    email: user?.primaryEmailAddress?.emailAddress ?? "",
    name: user?.fullName ?? user?.username ?? "",
    signOut: () => void signOut(),
  };
}

function useMockAuthUser(): AuthUser {
  return {
    email: "dev@example.com",
    name: "Dev User",
    signOut: () => undefined,
  };
}

/** The signed-in console user (email drives role resolution). */
export const useAuthUser: () => AuthUser = noAuthMode
  ? useMockAuthUser
  : useClerkAuthUser;
