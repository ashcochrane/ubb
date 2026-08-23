// Sandbox: a sibling test workspace. Status card + mint (each POST mints a
// FRESH ubb_test_ key — also the rotation path). Reset requires a SANDBOX
// key (the console's live credentials get 403), so we render a copyable curl
// instead of a dead button.

import { useState } from "react";
import { FlaskConical } from "lucide-react";

import { CodeBlock } from "@/components/shared/code-block";
import { CopyButton } from "@/components/shared/copy-button";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { useHasRole } from "@/hooks/use-current-role";

import { useCreateSandbox, useSandbox } from "../api/queries";
import { apiOrigin, sandboxResetCurl } from "../lib/test-event";
import { RawKeyDialog, type MintedKey } from "./raw-key-dialog";

export function SandboxSection() {
  const sandbox = useSandbox();
  const create = useCreateSandbox();
  const isAdmin = useHasRole("admin");
  const [minted, setMinted] = useState<MintedKey | null>(null);

  const mint = () => {
    create.mutate(undefined, {
      onSuccess: (result) =>
        setMinted({
          title: "Sandbox key minted",
          description:
            "Use this ubb_test_ key against the same API base URL. Sandbox traffic is fully isolated and never touches live Stripe.",
          apiKey: result.api_key,
          details: [
            {
              label: "Sandbox workspace",
              value: result.sandbox_tenant_id,
              mono: true,
            },
          ],
        }),
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sandbox</CardTitle>
        <CardDescription>
          A sibling test workspace with the same API surface but no real
          money. <span className="font-mono text-[12px]">ubb_test_</span> keys
          only reach test-mode Stripe.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {sandbox.isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-2/3" />
          </div>
        ) : sandbox.isError ? (
          <ErrorCard error={sandbox.error} onRetry={() => void sandbox.refetch()} />
        ) : !sandbox.data?.exists ? (
          <EmptyState
            icon={FlaskConical}
            title="No sandbox yet"
            description={
              isAdmin
                ? "Creating one provisions the test workspace and mints a ubb_test_ key you can use immediately."
                : "An Admin can create the sandbox for this workspace."
            }
            {...(isAdmin && {
              action: { label: "Create sandbox", onClick: mint },
            })}
          />
        ) : (
          <>
            <div className="flex items-center justify-between gap-2">
              <Badge variant="outline">Provisioned</Badge>
              <Button
                variant="outline"
                size="sm"
                onClick={mint}
                disabled={!isAdmin || create.isPending}
              >
                {create.isPending ? "Working…" : "Mint sandbox key"}
              </Button>
            </div>
            <div className="space-y-2 text-[13px]">
              <div className="flex items-baseline justify-between gap-3">
                <span className="shrink-0 text-[12px] text-text-secondary">
                  Sandbox workspace
                </span>
                <span className="inline-flex min-w-0 items-center gap-1.5 font-mono text-[12px]">
                  <span className="truncate" title={sandbox.data.sandbox_tenant_id ?? ""}>
                    {sandbox.data.sandbox_tenant_id}
                  </span>
                  {sandbox.data.sandbox_tenant_id && (
                    <CopyButton
                      value={sandbox.data.sandbox_tenant_id}
                      label="Copy sandbox workspace id"
                    />
                  )}
                </span>
              </div>
              <div className="flex items-baseline justify-between gap-3">
                <span className="shrink-0 text-[12px] text-text-secondary">
                  Test keys
                </span>
                <span className="flex flex-wrap justify-end gap-1">
                  {sandbox.data.key_prefixes.length === 0 ? (
                    <span className="text-[12px] text-text-muted">None yet</span>
                  ) : (
                    sandbox.data.key_prefixes.map((prefix) => (
                      <Badge key={prefix} variant="secondary" className="font-mono">
                        {prefix}…
                      </Badge>
                    ))
                  )}
                </span>
              </div>
            </div>
            <p className="text-[12px] text-text-secondary">
              Each mint returns a fresh key, shown once — minting again is also
              how you rotate sandbox keys.
              {!isAdmin && " Minting requires the Admin role."}
            </p>
            <Separator />
            <div className="space-y-2">
              <p className="text-[13px] font-medium text-text-primary">
                Reset the sandbox
              </p>
              <p className="text-[12px] text-text-secondary">
                Resetting wipes the sandbox's data so you can start clean. It
                only accepts a sandbox key — this console signs in with live
                credentials, which the endpoint refuses — so run it from your
                terminal:
              </p>
              <CodeBlock value={sandboxResetCurl(apiOrigin())} wrap />
              <ul className="list-disc space-y-1 pl-4 text-[12px] text-text-secondary">
                <li>
                  <span className="font-mono">"keep_config": true</span> preserves
                  your pricing, webhook, and billing configuration (pricing
                  books, cost books, markups, plans, budgets); set it to{" "}
                  <span className="font-mono">false</span> to wipe those too. The
                  workspace and its API keys always survive.
                </li>
                <li>
                  The wipe runs in the background: the sandbox answers 401 until
                  it finishes — that's the wipe in progress, not a revoked key.
                  The <span className="font-mono">sandbox.reset_completed</span>{" "}
                  webhook fires when it's done.
                </li>
              </ul>
            </div>
          </>
        )}
      </CardContent>
      <RawKeyDialog minted={minted} onClose={() => setMinted(null)} />
    </Card>
  );
}
