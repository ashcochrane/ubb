import { KeyRound, RotateCw, Trash2, Key } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Section, LoadingRows, ErrorInline } from "@/components/shared/data-states";
import { BoolBadge } from "@/components/shared/status-badge";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { CursorPagerControls } from "@/components/shared/cursor-pager";
import { formatShortDate, formatRelativeDate } from "@/lib/format";
import { useApiKeys, useRevokeApiKey } from "../api/queries";
import { CreateApiKeyDialog } from "./create-api-key-dialog";
import { RotateApiKeyDialog } from "./rotate-api-key-dialog";

export function ApiKeysTab() {
  const pager = useApiKeys();
  const revoke = useRevokeApiKey();

  return (
    <Section
      title="API keys"
      description="Keys authenticate server-to-server requests. Secrets are shown only at creation and rotation."
      actions={<CreateApiKeyDialog />}
    >
      {pager.isLoading ? (
        <LoadingRows />
      ) : pager.isError ? (
        <ErrorInline error={pager.error} onRetry={pager.refetch} />
      ) : pager.items.length === 0 ? (
        <EmptyState
          icon={Key}
          title="No API keys yet"
          description="Create a key to start making authenticated API requests."
        />
      ) : (
        <div className="space-y-3">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Label</TableHead>
                <TableHead>Prefix</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last used</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="w-8" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {pager.items.map((key) => (
                <TableRow key={key.id}>
                  <TableCell className="font-medium">
                    {key.label || <span className="text-muted-foreground">Untitled</span>}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{key.key_prefix}</TableCell>
                  <TableCell>
                    <BoolBadge value={key.is_active} trueLabel="Active" falseLabel="Revoked" />
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {key.last_used_at ? formatRelativeDate(key.last_used_at) : "Never"}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatShortDate(key.created_at)}
                  </TableCell>
                  <TableCell>
                    {key.is_active && (
                      <div className="flex items-center justify-end gap-1">
                        <RotateApiKeyDialog
                          keyId={key.id}
                          label={key.label}
                          trigger={
                            <Button variant="ghost" size="icon-sm" aria-label="Rotate key">
                              <RotateCw />
                            </Button>
                          }
                        />
                        <ConfirmDialog
                          destructive
                          title="Revoke this key?"
                          description="The key stops working immediately and can't be restored. This can't be undone."
                          confirmLabel="Revoke key"
                          onConfirm={async () => {
                            await revoke.mutateAsync(key.id);
                          }}
                          trigger={
                            <Button variant="ghost" size="icon-sm" aria-label="Revoke key">
                              <Trash2 />
                            </Button>
                          }
                        />
                      </div>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <CursorPagerControls pager={pager} />
        </div>
      )}
      <p className="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
        <KeyRound className="size-3.5" />
        A tenant must keep at least one active key — revoking the last one is refused.
      </p>
    </Section>
  );
}
