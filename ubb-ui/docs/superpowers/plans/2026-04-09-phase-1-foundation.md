# Phase 1: Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wipe the existing `src/` directory and rebuild the project scaffold with feature co-location, provider pattern, Clerk auth (with no-auth dev mode), nav shell, and all shared infrastructure.

**Architecture:** Feature co-located structure modeled after engage-online-ui. Routes in `src/app/routes/`, features in `src/features/`, shared UI in `src/components/`. Provider pattern (`selectProvider`) controls mock vs real API. Clerk for auth with Zustand for tenant context.

**Tech Stack:** React 19, Vite 8, TypeScript 5.9, Tailwind CSS v4, TanStack Router, TanStack Query v5, Zustand 5, shadcn/ui, openapi-fetch, Clerk, Lucide, Recharts, Sonner, Vitest + RTL + MSW

**Design spec:** `docs/superpowers/specs/2026-04-09-full-rebuild-design.md`

---

## Pre-Flight: What to Save Before Wiping

Before deleting `src/`, copy these files to a temp location — they'll be migrated into the new structure:

- `src/index.css` → will become `src/styles/app.css`
- `src/lib/format.ts` → will become `src/lib/format.ts`
- `src/lib/format.test.ts` → will become `src/lib/format.test.ts`
- `src/lib/utils.ts` → will become `src/lib/utils.ts`

**Do NOT save** anything else from `src/`. The rest is being rebuilt.

**Do NOT delete:**
- Root config files: `package.json`, `tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json`, `vite.config.ts`, `eslint.config.js`, `components.json`, `index.html`, `.env.example`, `.env.local`, `.gitignore`
- `docs/` directory (all mockups and specs)
- `scripts/` directory
- `ui-mockups/` directory
- `public/` directory

---

## File Map

### Infrastructure (shared)

| File | Responsibility |
|------|---------------|
| `src/main.tsx` | React root, Clerk/NoAuth conditional, QueryProvider not here |
| `src/styles/app.css` | Tailwind imports, OKLCH design tokens (migrated from index.css) |
| `src/lib/api-provider.ts` | `VITE_API_PROVIDER` validation, `selectProvider()` helper |
| `src/lib/query-client.ts` | QueryClient singleton with defaults |
| `src/lib/utils.ts` | `cn()` helper (migrated) |
| `src/lib/format.ts` | Currency/date/number formatting (migrated) |
| `src/lib/format.test.ts` | Format utility tests (migrated) |
| `src/api/client.ts` | openapi-fetch client + Clerk auth middleware |
| `src/stores/auth-store.ts` | Zustand: tenant context, mode, permissions |

### App Shell (routes + providers)

| File | Responsibility |
|------|---------------|
| `src/app/providers/query-provider.tsx` | QueryClientProvider wrapper |
| `src/app/routes/__root.tsx` | Root layout: QueryProvider, Toaster, error/404 handling |
| `src/app/routes/sign-in.tsx` | Clerk sign-in page (public route) |
| `src/app/routes/_app.tsx` | Auth guard + nav shell layout |
| `src/app/routes/_app/index.tsx` | Dashboard placeholder (/) |
| `src/app/routes/_app/pricing-cards/index.tsx` | Pricing cards placeholder |
| `src/app/routes/_app/products/index.tsx` | Products placeholder |
| `src/app/routes/_app/customers/index.tsx` | Customers placeholder |
| `src/app/routes/_app/billing/index.tsx` | Billing placeholder |
| `src/app/routes/_app/export/index.tsx` | Export placeholder |
| `src/app/routes/_app/settings/index.tsx` | Settings placeholder |

### Shared Components

| File | Responsibility |
|------|---------------|
| `src/components/shared/nav-shell.tsx` | Full-height sidebar + content area layout |
| `src/components/shared/nav-config.ts` | Sidebar sections with labels and items |
| `src/components/shared/top-bar.tsx` | Top bar (right of sidebar): collapse toggle, theme, user |
| `src/components/shared/page-header.tsx` | Reusable page title + description |
| `src/components/shared/not-found.tsx` | 404 page |
| `src/components/shared/route-error.tsx` | Route-level error display |

### Auth Feature

| File | Responsibility |
|------|---------------|
| `src/features/auth/hooks/use-auth.ts` | Auth hook wrapping Clerk + Zustand |

### Test Setup

| File | Responsibility |
|------|---------------|
| `src/test-setup.ts` | Vitest globals, RTL cleanup |

### Config Updates

| File | Change |
|------|--------|
| `vite.config.ts` | Update TanStack Router routesDirectory to `src/app/routes` |
| `components.json` | Update css path to `src/styles/app.css` |
| `index.html` | Update CSS import path |
| `.env.example` | Add `VITE_API_PROVIDER`, update descriptions |
| `.env.local` | Add `VITE_API_PROVIDER=mock`, comment out Clerk key |

---

## Task 1: Wipe src/ and Restore Saved Files

**Files:**
- Delete: entire `src/` directory
- Create: `src/styles/app.css`, `src/lib/format.ts`, `src/lib/format.test.ts`, `src/lib/utils.ts`, `src/main.tsx` (empty placeholder), `src/test-setup.ts`

- [ ] **Step 1: Save files to migrate**

```bash
mkdir -p /tmp/ubb-migrate
cp src/index.css /tmp/ubb-migrate/app.css
cp src/lib/format.ts /tmp/ubb-migrate/format.ts
cp src/lib/format.test.ts /tmp/ubb-migrate/format.test.ts
cp src/lib/utils.ts /tmp/ubb-migrate/utils.ts
```

- [ ] **Step 2: Delete src/ directory**

```bash
rm -rf src/
```

- [ ] **Step 3: Create new directory structure**

```bash
mkdir -p src/app/providers
mkdir -p src/app/routes/_app/pricing-cards
mkdir -p src/app/routes/_app/products
mkdir -p src/app/routes/_app/customers
mkdir -p src/app/routes/_app/billing
mkdir -p src/app/routes/_app/export
mkdir -p src/app/routes/_app/settings
mkdir -p src/features/auth/hooks
mkdir -p src/components/ui
mkdir -p src/components/shared
mkdir -p src/api
mkdir -p src/hooks
mkdir -p src/lib
mkdir -p src/stores
mkdir -p src/types
mkdir -p src/styles
```

- [ ] **Step 4: Restore migrated files**

```bash
cp /tmp/ubb-migrate/app.css src/styles/app.css
cp /tmp/ubb-migrate/format.ts src/lib/format.ts
cp /tmp/ubb-migrate/format.test.ts src/lib/format.test.ts
cp /tmp/ubb-migrate/utils.ts src/lib/utils.ts
```

- [ ] **Step 5: Create empty main.tsx placeholder**

```typescript
// src/main.tsx
// Placeholder — will be implemented in Task 3
export {};
```

- [ ] **Step 6: Create test setup**

```typescript
// src/test-setup.ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore(infra): wipe src/ and restore migrated utilities"
```

---

## Task 2: Update Config Files

**Files:**
- Modify: `vite.config.ts`
- Modify: `components.json`
- Modify: `index.html`
- Modify: `.env.example`
- Modify: `.env.local`

- [ ] **Step 1: Update vite.config.ts**

Change the TanStack Router plugin to use the new routes directory, and update the test setup path:

```typescript
// vite.config.ts
/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { TanStackRouterVite } from "@tanstack/router-plugin/vite";
import path from "path";

export default defineConfig({
  plugins: [
    tailwindcss(),
    TanStackRouterVite({
      routesDirectory: "./src/app/routes",
      generatedRouteTree: "./src/app/routeTree.gen.ts",
    }),
    react(),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/test-setup.ts",
  },
});
```

- [ ] **Step 2: Update components.json**

Change the CSS path to point to the new location:

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "base-nova",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "src/styles/app.css",
    "baseColor": "zinc",
    "cssVariables": true,
    "prefix": ""
  },
  "iconLibrary": "lucide",
  "rtl": false,
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  },
  "menuColor": "default",
  "menuAccent": "subtle",
  "registries": {}
}
```

- [ ] **Step 3: Update index.html**

Change the CSS import and script entry point:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>UBB</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 4: Update .env.example**

```bash
# API provider: mock (no backend) | api (real backend)
VITE_API_PROVIDER=mock

# Backend API URL (only needed when VITE_API_PROVIDER=api)
VITE_API_URL=http://localhost:8000

# Clerk publishable key (leave blank for no-auth dev mode)
VITE_CLERK_PUBLISHABLE_KEY=
```

- [ ] **Step 5: Update .env.local**

```bash
VITE_API_PROVIDER=mock
VITE_API_URL=http://localhost:8000
# VITE_CLERK_PUBLISHABLE_KEY=pk_test_c3RpbGwtY2hhbW9pcy0yNi5jbGVyay5hY2NvdW50cy5kZXYk
```

- [ ] **Step 6: Commit**

```bash
git add vite.config.ts components.json index.html .env.example .env.local
git commit -m "chore(infra): update config for new directory structure"
```

---

## Task 3: Provider Pattern + API Client

**Files:**
- Create: `src/lib/api-provider.ts`
- Create: `src/api/client.ts`

- [ ] **Step 1: Create api-provider.ts**

```typescript
// src/lib/api-provider.ts
const VALID_PROVIDERS = ["mock", "api"] as const;

export type ApiProvider = (typeof VALID_PROVIDERS)[number];

function getApiProvider(): ApiProvider {
  const value = import.meta.env.VITE_API_PROVIDER;
  if (!value || !VALID_PROVIDERS.includes(value as ApiProvider)) {
    return "mock";
  }
  return value as ApiProvider;
}

/** Current API provider — set via VITE_API_PROVIDER env var. Defaults to "mock". */
export const API_PROVIDER = getApiProvider();

/** Select the active implementation from a record of providers. */
export function selectProvider<T>(providers: Record<ApiProvider, T>): T {
  return providers[API_PROVIDER];
}
```

- [ ] **Step 2: Create api/client.ts**

```typescript
// src/api/client.ts
import createClient, { type Middleware } from "openapi-fetch";

let _getToken: (() => Promise<string | null>) | null = null;

/**
 * Register the auth token getter. Called once after Clerk initialises.
 * The getter is invoked on every outgoing request so the Authorization
 * header always carries a fresh JWT.
 */
export function setAuthTokenGetter(fn: () => Promise<string | null>) {
  _getToken = fn;
}

const authMiddleware: Middleware = {
  async onRequest({ request }) {
    if (_getToken) {
      const token = await _getToken();
      if (token) {
        request.headers.set("Authorization", `Bearer ${token}`);
      }
    }
    return request;
  },
};

function createApiClient(basePath: string) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const client = createClient<any>({
    baseUrl: `${import.meta.env.VITE_API_URL || ""}${basePath}`,
  });
  client.use(authMiddleware);
  return client;
}

export const platformApi = createApiClient("/api/v1/platform");
export const meteringApi = createApiClient("/api/v1/metering");
export const billingApi = createApiClient("/api/v1/billing");
export const tenantApi = createApiClient("/api/v1/tenant");
```

- [ ] **Step 3: Commit**

```bash
git add src/lib/api-provider.ts src/api/client.ts
git commit -m "feat(infra): add provider pattern and openapi-fetch client"
```

---

## Task 4: Query Client + Provider

**Files:**
- Create: `src/lib/query-client.ts`
- Create: `src/app/providers/query-provider.tsx`

- [ ] **Step 1: Create query-client.ts**

```typescript
// src/lib/query-client.ts
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 1000 * 30,
      refetchOnWindowFocus: true,
    },
    mutations: {
      retry: 0,
    },
  },
});
```

- [ ] **Step 2: Create query-provider.tsx**

```typescript
// src/app/providers/query-provider.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { queryClient } from "@/lib/query-client";

export function QueryProvider({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add src/lib/query-client.ts src/app/providers/query-provider.tsx
git commit -m "feat(infra): add query client and provider"
```

---

## Task 5: Auth Store

**Files:**
- Create: `src/stores/auth-store.ts`
- Create: `src/features/auth/hooks/use-auth.ts`

- [ ] **Step 1: Create auth-store.ts**

```typescript
// src/stores/auth-store.ts
import { create } from "zustand";

export type TenantMode = "track" | "revenue" | "billing";

interface AuthState {
  activeTenantId: string | null;
  tenantMode: TenantMode | null;
  permissions: string[];

  setTenant: (tenantId: string, mode: TenantMode) => void;
  setPermissions: (permissions: string[]) => void;
  reset: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  activeTenantId: null,
  tenantMode: null,
  permissions: [],

  setTenant: (tenantId, mode) =>
    set({ activeTenantId: tenantId, tenantMode: mode }),

  setPermissions: (permissions) => set({ permissions }),

  reset: () =>
    set({ activeTenantId: null, tenantMode: null, permissions: [] }),
}));
```

- [ ] **Step 2: Create use-auth.ts**

```typescript
// src/features/auth/hooks/use-auth.ts
import { useCallback } from "react";
import { useShallow } from "zustand/shallow";
import { useAuthStore, type TenantMode } from "@/stores/auth-store";

export interface UseAuth {
  activeTenantId: string | null;
  tenantMode: TenantMode | null;
  permissions: string[];
  hasPermission: (permission: string) => boolean;
  isBillingMode: boolean;
}

export function useAuth(): UseAuth {
  const { activeTenantId, tenantMode, permissions } = useAuthStore(
    useShallow((s) => ({
      activeTenantId: s.activeTenantId,
      tenantMode: s.tenantMode,
      permissions: s.permissions,
    })),
  );

  const hasPermission = useCallback(
    (permission: string) => permissions.includes(permission),
    [permissions],
  );

  return {
    activeTenantId,
    tenantMode,
    permissions,
    hasPermission,
    isBillingMode: tenantMode === "billing",
  };
}
```

- [ ] **Step 3: Commit**

```bash
git add src/stores/auth-store.ts src/features/auth/hooks/use-auth.ts
git commit -m "feat(auth): add auth store and useAuth hook"
```

---

## Task 6: Shared Components (Nav Shell, Top Bar, Page Header, Errors)

**Files:**
- Create: `src/components/shared/nav-config.ts`
- Create: `src/components/shared/nav-shell.tsx`
- Create: `src/components/shared/top-bar.tsx`
- Create: `src/components/shared/page-header.tsx`
- Create: `src/components/shared/not-found.tsx`
- Create: `src/components/shared/route-error.tsx`

- [ ] **Step 1: Install required shadcn components**

```bash
npx shadcn@latest add button separator tooltip scroll-area avatar skeleton
```

- [ ] **Step 2: Create nav-config.ts**

Navigation uses sections with labels to group items (matching the current UI: ungrouped top items, then METERING, BILLING, SETTINGS sections). Updated to use the new nav model from the design spec.

```typescript
// src/components/shared/nav-config.ts
import {
  LayoutDashboard,
  Users,
  CreditCard,
  BarChart3,
  Package,
  DollarSign,
  Download,
  Settings,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  title: string;
  url: string;
  icon: LucideIcon;
}

export interface NavSection {
  /** Section label (e.g. "METERING"). Omit for ungrouped top items. */
  label?: string;
  items: NavItem[];
  /** Only show this section when this condition is true. Undefined = always show. */
  visibleWhen?: "billing";
}

export const navSections: NavSection[] = [
  {
    items: [
      { title: "Dashboard", url: "/", icon: LayoutDashboard },
      { title: "Customers", url: "/customers", icon: Users },
    ],
  },
  {
    label: "METERING",
    items: [
      { title: "Pricing Cards", url: "/pricing-cards", icon: CreditCard },
      { title: "Products", url: "/products", icon: Package },
    ],
  },
  {
    label: "BILLING",
    visibleWhen: "billing",
    items: [
      { title: "Billing", url: "/billing", icon: DollarSign },
      { title: "Export", url: "/export", icon: Download },
    ],
  },
  {
    label: "SETTINGS",
    items: [
      { title: "Settings", url: "/settings", icon: Settings },
    ],
  },
];
```

- [ ] **Step 3: Create nav-shell.tsx**

Full-height sidebar with "UBB" in the top-left corner. Items grouped under section labels. The top bar sits to the right of the sidebar (not full-width). This matches the current UI layout where the sidebar overlaps the top nav area.

```typescript
// src/components/shared/nav-shell.tsx
import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { navSections } from "./nav-config";
import { TopBar } from "./top-bar";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { cn } from "@/lib/utils";

interface NavShellProps {
  children: ReactNode;
  userSlot?: ReactNode;
}

export function NavShell({ children, userSlot }: NavShellProps) {
  const { isBillingMode } = useAuth();

  const visibleSections = navSections.filter(
    (section) =>
      !section.visibleWhen ||
      (section.visibleWhen === "billing" && isBillingMode),
  );

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar — full height, overlaps top bar area */}
      <aside className="flex w-56 shrink-0 flex-col border-r border-border">
        {/* Sidebar header — "UBB" branding in the top-left intersection */}
        <div className="flex h-11 items-center px-4">
          <span className="text-base font-bold tracking-tight">UBB</span>
        </div>

        {/* Nav sections */}
        <nav className="flex-1 overflow-auto px-3 py-1">
          {visibleSections.map((section, sectionIdx) => (
            <div key={section.label ?? sectionIdx} className={cn(sectionIdx > 0 && "mt-4")}>
              {section.label && (
                <div className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {section.label}
                </div>
              )}
              <div className="space-y-0.5">
                {section.items.map((item) => (
                  <Link
                    key={item.url}
                    to={item.url}
                    className="flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                    activeProps={{
                      className:
                        "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm font-medium bg-accent text-foreground",
                    }}
                    activeOptions={{ exact: item.url === "/" }}
                  >
                    <item.icon className="h-4 w-4 shrink-0" />
                    <span>{item.title}</span>
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </nav>
      </aside>

      {/* Right side: top bar + content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar userSlot={userSlot} />
        <main className="flex-1 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
```

- [ ] **Step 3b: Create top-bar.tsx**

The top bar sits to the right of the sidebar. Contains the sidebar collapse toggle on the left, theme toggle and user avatar on the right. Matches the screenshot layout.

```typescript
// src/components/shared/top-bar.tsx
import { PanelLeft, Sun } from "lucide-react";
import type { ReactNode } from "react";
import { API_PROVIDER } from "@/lib/api-provider";

interface TopBarProps {
  userSlot?: ReactNode;
}

export function TopBar({ userSlot }: TopBarProps) {
  const isMock = API_PROVIDER === "mock";

  return (
    <header className="flex h-11 shrink-0 items-center gap-2 border-b border-border px-4">
      <button className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground">
        <PanelLeft className="h-4 w-4" />
      </button>

      <div className="flex-1" />

      {isMock && (
        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
          Mock
        </span>
      )}

      <button className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground">
        <Sun className="h-4 w-4" />
      </button>

      {userSlot}
    </header>
  );
}
```

- [ ] **Step 4: Create page-header.tsx**

```typescript
// src/components/shared/page-header.tsx
interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}

export function PageHeader({ title, description, actions }: PageHeaderProps) {
  return (
    <div className="flex items-start justify-between">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && (
          <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
```

- [ ] **Step 5: Create not-found.tsx**

```typescript
// src/components/shared/not-found.tsx
import { Link } from "@tanstack/react-router";

export function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3">
      <h1 className="text-3xl font-bold">404</h1>
      <p className="text-sm text-muted-foreground">Page not found.</p>
      <Link
        to="/"
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      >
        Go home
      </Link>
    </div>
  );
}
```

- [ ] **Step 6: Create route-error.tsx**

```typescript
// src/components/shared/route-error.tsx
interface RouteErrorProps {
  error: Error;
}

export function RouteError({ error }: RouteErrorProps) {
  return (
    <div className="flex min-h-[400px] flex-col items-center justify-center gap-3 p-8">
      <h2 className="text-lg font-semibold">Something went wrong</h2>
      <p className="max-w-md text-center text-sm text-muted-foreground">
        {error.message || "An unexpected error occurred."}
      </p>
      <button
        onClick={() => window.location.reload()}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      >
        Reload page
      </button>
    </div>
  );
}
```

- [ ] **Step 7: Commit**

```bash
git add src/components/
git commit -m "feat(shared): add nav shell, page header, error components"
```

---

## Task 7: Root Route + App Layout Route

**Files:**
- Create: `src/app/routes/__root.tsx`
- Create: `src/app/routes/sign-in.tsx`
- Create: `src/app/routes/_app.tsx`

- [ ] **Step 1: Create __root.tsx**

```typescript
// src/app/routes/__root.tsx
import { createRootRoute, Outlet } from "@tanstack/react-router";
import { QueryProvider } from "@/app/providers/query-provider";
import { NotFound } from "@/components/shared/not-found";
import { RouteError } from "@/components/shared/route-error";
import { Toaster } from "sonner";

export const Route = createRootRoute({
  component: RootLayout,
  errorComponent: RootError,
  notFoundComponent: NotFound,
});

function RootLayout() {
  return (
    <QueryProvider>
      <Outlet />
      <Toaster position="bottom-right" />
    </QueryProvider>
  );
}

function RootError({ error }: { error: Error }) {
  return <RouteError error={error} />;
}
```

- [ ] **Step 2: Create sign-in.tsx**

```typescript
// src/app/routes/sign-in.tsx
import { createFileRoute, redirect } from "@tanstack/react-router";
import { SignIn } from "@clerk/react";

const clerkEnabled = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

export const Route = createFileRoute("/sign-in")({
  beforeLoad: ({ context }) => {
    // If already signed in (or no-auth mode), go home
    if (!clerkEnabled || context.auth?.isSignedIn) {
      throw redirect({ to: "/" });
    }
  },
  component: SignInPage,
});

function SignInPage() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <SignIn routing="hash" fallbackRedirectUrl="/" />
    </div>
  );
}
```

- [ ] **Step 3: Create _app.tsx**

Auth guard + nav shell. In mock mode with no Clerk, auto-bootstraps a fake session.

```typescript
// src/app/routes/_app.tsx
import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { UserButton } from "@clerk/react";
import { User } from "lucide-react";
import { NavShell } from "@/components/shared/nav-shell";
import { RouteError } from "@/components/shared/route-error";
import { useAuthStore } from "@/stores/auth-store";
import { API_PROVIDER } from "@/lib/api-provider";

const clerkEnabled = !!import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ context }) => {
    const isMock = API_PROVIDER === "mock";

    // No-auth dev mode: auto-bootstrap mock tenant
    if (!clerkEnabled && isMock) {
      const { activeTenantId } = useAuthStore.getState();
      if (!activeTenantId) {
        useAuthStore.getState().setTenant("tenant-mock-001", "billing");
      }
      return;
    }

    // Real auth: check Clerk
    if (!context.auth?.isSignedIn) {
      throw redirect({ to: "/sign-in" });
    }
  },
  errorComponent: ({ error }) => <RouteError error={error} />,
  component: AppLayout,
});

function AppLayout() {
  const userSlot = clerkEnabled ? (
    <UserButton />
  ) : (
    <div className="flex h-7 w-7 items-center justify-center rounded-full bg-muted">
      <User className="h-4 w-4 text-muted-foreground" />
    </div>
  );

  return (
    <NavShell userSlot={userSlot}>
      <div className="p-6">
        <Outlet />
      </div>
    </NavShell>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add src/app/routes/
git commit -m "feat(infra): add root route, sign-in, and app layout with auth guard"
```

---

## Task 8: Stub Route Pages

**Files:**
- Create: `src/app/routes/_app/index.tsx`
- Create: `src/app/routes/_app/pricing-cards/index.tsx`
- Create: `src/app/routes/_app/products/index.tsx`
- Create: `src/app/routes/_app/customers/index.tsx`
- Create: `src/app/routes/_app/billing/index.tsx`
- Create: `src/app/routes/_app/export/index.tsx`
- Create: `src/app/routes/_app/settings/index.tsx`

- [ ] **Step 1: Create dashboard stub (index.tsx)**

```typescript
// src/app/routes/_app/index.tsx
import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/shared/page-header";

export const Route = createFileRoute("/_app/")({
  component: DashboardPage,
});

function DashboardPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Profitability overview across all products and customers."
      />
      <div className="rounded-lg border border-dashed p-12 text-center text-sm text-muted-foreground">
        Dashboard — Phase 3
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create pricing-cards stub**

```typescript
// src/app/routes/_app/pricing-cards/index.tsx
import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/shared/page-header";

export const Route = createFileRoute("/_app/pricing-cards/")({
  component: PricingCardsPage,
});

function PricingCardsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Pricing Cards"
        description="Define how API costs are calculated."
      />
      <div className="rounded-lg border border-dashed p-12 text-center text-sm text-muted-foreground">
        Pricing Cards — Phase 2
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create products stub**

```typescript
// src/app/routes/_app/products/index.tsx
import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/shared/page-header";

export const Route = createFileRoute("/_app/products/")({
  component: ProductsPage,
});

function ProductsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Products"
        description="Group pricing cards into products for dashboard aggregation."
      />
      <div className="rounded-lg border border-dashed p-12 text-center text-sm text-muted-foreground">
        Products — coming soon
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create customers stub**

```typescript
// src/app/routes/_app/customers/index.tsx
import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/shared/page-header";

export const Route = createFileRoute("/_app/customers/")({
  component: CustomersPage,
});

function CustomersPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Customers"
        description="Manage Stripe-to-SDK customer mappings."
      />
      <div className="rounded-lg border border-dashed p-12 text-center text-sm text-muted-foreground">
        Customer Mapping — Phase 5
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Create billing stub**

```typescript
// src/app/routes/_app/billing/index.tsx
import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/shared/page-header";

export const Route = createFileRoute("/_app/billing/")({
  component: BillingPage,
});

function BillingPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Billing"
        description="Margin management and balance configuration."
      />
      <div className="rounded-lg border border-dashed p-12 text-center text-sm text-muted-foreground">
        Margin Management — Phase 7
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Create export stub**

```typescript
// src/app/routes/_app/export/index.tsx
import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/shared/page-header";

export const Route = createFileRoute("/_app/export/")({
  component: ExportPage,
});

function ExportPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Export"
        description="Download event-level data as CSV or JSON."
      />
      <div className="rounded-lg border border-dashed p-12 text-center text-sm text-muted-foreground">
        Data Export — Phase 8
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Create settings stub**

```typescript
// src/app/routes/_app/settings/index.tsx
import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/shared/page-header";

export const Route = createFileRoute("/_app/settings/")({
  component: SettingsPage,
});

function SettingsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="Stripe connection, API keys, and account configuration."
      />
      <div className="rounded-lg border border-dashed p-12 text-center text-sm text-muted-foreground">
        Settings — coming soon
      </div>
    </div>
  );
}
```

- [ ] **Step 8: Commit**

```bash
git add src/app/routes/_app/
git commit -m "feat(infra): add stub pages for all nav sections"
```

---

## Task 9: Main Entry Point (Clerk + No-Auth)

**Files:**
- Create: `src/main.tsx` (replace placeholder)

- [ ] **Step 1: Write main.tsx**

Minimal entry point. Clerk wraps conditionally. QueryProvider is NOT here — it's in `__root.tsx`.

```typescript
// src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { ClerkProvider, useAuth } from "@clerk/react";
import { RouterProvider, createRouter } from "@tanstack/react-router";
import { routeTree } from "./app/routeTree.gen";
import { setAuthTokenGetter } from "./api/client";
import "./styles/app.css";

const clerkPubKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

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
    {clerkPubKey ? (
      <ClerkProvider publishableKey={clerkPubKey}>
        <ClerkApp />
      </ClerkProvider>
    ) : (
      <NoAuthApp />
    )}
  </React.StrictMode>,
);
```

- [ ] **Step 2: Commit**

```bash
git add src/main.tsx
git commit -m "feat(infra): add main entry point with Clerk/NoAuth conditional"
```

---

## Task 10: Verify Everything Works

- [ ] **Step 1: Run the dev server**

```bash
pnpm dev
```

Expected: Vite starts, TanStack Router generates `src/app/routeTree.gen.ts`, app loads at `http://localhost:5173`.

- [ ] **Step 2: Verify no-auth dev mode**

With `VITE_CLERK_PUBLISHABLE_KEY` commented out in `.env.local`, the app should:
- Show the sidebar with all nav items (including Billing, since mock bootstraps as "billing" mode)
- Show a placeholder user icon in the sidebar footer
- Show a "Mock" badge in the sidebar
- Navigate between all stub pages without errors

- [ ] **Step 3: Verify routing**

Click each sidebar item and confirm:
- `/` → Dashboard stub
- `/pricing-cards` → Pricing Cards stub
- `/products` → Products stub
- `/customers` → Customers stub
- `/billing` → Billing stub
- `/export` → Export stub
- `/settings` → Settings stub
- Active nav item is highlighted
- Non-existent route → 404 page

- [ ] **Step 4: Run tests**

```bash
pnpm test
```

Expected: `format.test.ts` tests pass (3 tests in 2 suites).

- [ ] **Step 5: Run lint**

```bash
pnpm lint
```

Expected: No errors.

- [ ] **Step 6: Run build**

```bash
pnpm build
```

Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 7: Commit any fixes**

If any step above required fixes, commit them:

```bash
git add -A
git commit -m "fix(infra): resolve issues from foundation verification"
```

---

## Task 11: Update PROGRESS.md

- [ ] **Step 1: Update PROGRESS.md**

Mark Phase 1 items as complete:

```markdown
## Phase 1: Foundation

- [x] Vite + React 19 + TypeScript scaffold
- [x] Tailwind CSS v4 with design tokens (migrate from previous index.css)
- [x] shadcn/ui component library
- [x] TanStack Router with route structure
- [x] Clerk auth (with no-auth dev mode)
- [x] Provider pattern (selectProvider, api-provider.ts)
- [x] API client (openapi-fetch + auth middleware)
- [x] Nav shell (sidebar matching mockup nav model)
- [x] Zustand auth store (tenant context, permissions)
- [x] QueryProvider in root route
- [x] Sonner toaster at root
- [x] Vitest + RTL + MSW setup
- [x] Migrate format.ts + tests
```

Update current status:

```markdown
**Phase:** 2 — Pricing Card Wizard (not started)
**Last completed:** Phase 1 — Foundation
```

Add session log entry:

```markdown
| 2026-04-09 | Phase 1 Foundation complete. Fresh scaffold with feature co-location, provider pattern, Clerk auth, nav shell. |
```

- [ ] **Step 2: Commit**

```bash
git add PROGRESS.md
git commit -m "docs: mark Phase 1 Foundation as complete"
```
