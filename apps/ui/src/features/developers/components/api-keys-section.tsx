// API keys: list (active + revoked, newest first), create, rotate, revoke.
// Raw keys surface once via the return-once modal; last_used_at is labeled
// approximate (Redis-buffered, flushed periodically — it can lag).

import { useState } from "react";
import { Info, KeyRound } from "lucide-react";

import { CopyButton } from "@/components/shared/copy-button";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { LoadMore } from "@/components/shared/load-more";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useHasRole } from "@/hooks/use-current-role";
import { formatDate, formatRelativeDate, formatShortDate } from "@/lib/format";

import { useApiKeys, useRevokeApiKey, useRotateApiKey } from "../api/queries";
import type { ApiKey } from "../api/types";
import { ApiKeyCreateDialog } from "./api-key-create-dialog";
import { RawKeyDialog, type MintedKey } from "./raw-key-dialog";

export function ApiKeysSection() {
  const keys = useApiKeys();
  const rotate = useRotateApiKey();
  const revoke = useRevokeApiKey();
  const isAdmin = useHasRole("admin");

  const [createOpen, setCreateOpen] = useState(false);
  const [minted, setMinted] = useState<MintedKey | null>(null);
  const [rotateTarget, setRotateTarget] = useState<ApiKey | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<ApiKey | null>(null);

  const confirmRotate = () => {
    if (!rotateTarget) return;
    rotate.mutate(rotateTarget.id, {
      onSuccess: (rotated) => {
        setRotateTarget(null);
        setMinted({
          title: "Key rotated",
          description:
            "The old key stops working on its next request. Update your integration with the replacement below.",
          apiKey: rotated.api_key,
          details: [
            { label: "New key", value: rotated.key_prefix, mono: true },
            { label: "Label", value: rotated.label },
          ],
        });
      },
      onError: () => setRotateTarget(null),
    });
  };

  const confirmRevoke = () => {
    if (!revokeTarget) return;
    revoke.mutate(revokeTarget.id, {
      onSettled: () => setRevokeTarget(null),
    });
  };

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold text-text-primary">API keys</h2>
          <p className="text-[13px] text-text-secondary">
            Bearer credentials for your servers and agents. UBB stores only a
            hash — each full key is shown once, at mint time.
          </p>
          {!isAdmin && (
            <p className="mt-1 text-[12px] text-text-muted">
              Creating, rotating, and revoking keys requires the Admin role.
            </p>
          )}
        </div>
        <Button onClick={() => setCreateOpen(true)} disabled={!isAdmin}>
          Create key
        </Button>
      </div>

      {keys.isInitialLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
        </div>
      ) : keys.isError ? (
        <ErrorCard error={keys.error} onRetry={() => void keys.refetch()} />
      ) : keys.rows.length === 0 ? (
        <EmptyState
          icon={KeyRound}
          title="No API keys yet"
          description={
            isAdmin
              ? "Mint a key to start sending usage events from your backend."
              : "An Admin can mint the first key for this workspace."
          }
          {...(isAdmin && {
            action: { label: "Create API key", onClick: () => setCreateOpen(true) },
          })}
        />
      ) : (
        <div className="rounded-lg border border-border">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Key</TableHead>
                  <TableHead>Label</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>
                    <span className="inline-flex items-center gap-1">
                      Last used (approximate)
                      <Tooltip>
                        <TooltipTrigger
                          render={
                            <span
                              tabIndex={0}
                              aria-label="About last-used times"
                              className="inline-flex"
                            />
                          }
                        >
                          <Info className="h-3 w-3 text-text-muted" />
                        </TooltipTrigger>
                        <TooltipContent>
                          Usage is buffered and written back periodically, so
                          this can lag a recently-used key by a few minutes.
                        </TooltipContent>
                      </Tooltip>
                    </span>
                  </TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {keys.rows.map((key) => (
                  <TableRow key={key.id}>
                    <TableCell>
                      <span className="inline-flex items-center gap-1.5 font-mono text-[12px]">
                        {key.key_prefix}…
                        <CopyButton value={key.key_prefix} label="Copy key prefix" />
                      </span>
                    </TableCell>
                    <TableCell className="max-w-[200px] truncate" title={key.label}>
                      {key.label || "—"}
                    </TableCell>
                    <TableCell>
                      {/* App-wide badge rule: Active = secondary (filled),
                          dormant/terminal = outline. */}
                      {key.is_active ? (
                        <Badge variant="secondary">Active</Badge>
                      ) : (
                        <Badge variant="outline">Revoked</Badge>
                      )}
                    </TableCell>
                    <TableCell title={formatDate(key.created_at)}>
                      {formatShortDate(key.created_at)}
                    </TableCell>
                    <TableCell
                      {...(key.last_used_at && { title: formatDate(key.last_used_at) })}
                    >
                      {key.last_used_at ? formatRelativeDate(key.last_used_at) : "Never"}
                    </TableCell>
                    <TableCell className="text-right">
                      {key.is_active ? (
                        <span className="inline-flex gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={!isAdmin}
                            onClick={() => setRotateTarget(key)}
                          >
                            Rotate
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={!isAdmin}
                            className="text-destructive hover:text-destructive"
                            onClick={() => setRevokeTarget(key)}
                          >
                            Revoke
                          </Button>
                        </span>
                      ) : (
                        <span className="text-[12px] text-text-muted">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <LoadMore
            shownCount={keys.rows.length}
            hasMore={keys.hasMore}
            isFetchingNextPage={keys.isFetchingNextPage}
            onLoadMore={keys.fetchNextPage}
            noun="keys"
          />
        </div>
      )}

      <ApiKeyCreateDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={(created, wasTest) =>
          setMinted({
            title: wasTest ? "Sandbox key created" : "API key created",
            description: wasTest
              ? "This ubb_test_ key was minted on your sandbox workspace — it appears in the sandbox's key list, not this one."
              : "Use this key as a bearer token from your backend.",
            apiKey: created.api_key,
            details: [
              { label: "Key", value: created.key_prefix, mono: true },
              ...(created.label ? [{ label: "Label", value: created.label }] : []),
              { label: "Landed on workspace", value: created.tenant_id, mono: true },
            ],
          })
        }
      />
      <RawKeyDialog minted={minted} onClose={() => setMinted(null)} />
      <ConfirmDialog
        open={rotateTarget !== null}
        onOpenChange={(open) => !open && setRotateTarget(null)}
        title="Rotate this key?"
        description={
          rotateTarget
            ? `${rotateTarget.key_prefix}… is replaced in one step: a successor is minted and the old key stops working on its next request. The new key is shown once.`
            : ""
        }
        confirmLabel="Rotate key"
        onConfirm={confirmRotate}
        pending={rotate.isPending}
      />
      <ConfirmDialog
        open={revokeTarget !== null}
        onOpenChange={(open) => !open && setRevokeTarget(null)}
        title="Revoke this key?"
        description={
          revokeTarget
            ? `${revokeTarget.key_prefix}… stops authenticating immediately and can't be reactivated. It stays in the list as history. If this is your last active key, revoke is refused — rotate instead.`
            : ""
        }
        confirmLabel="Revoke key"
        destructive
        onConfirm={confirmRevoke}
        pending={revoke.isPending}
      />
    </section>
  );
}
