import { useState } from "react";
import { FlaskConical, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Section,
  DetailGrid,
  DetailRow,
  LoadingRows,
  ErrorInline,
} from "@/components/shared/data-states";
import { StatusBadge } from "@/components/shared/status-badge";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { CheckboxRow } from "./checkbox-row";
import { useSandbox, useCreateSandbox, useResetSandbox } from "../api/queries";
import { readString, readBool } from "../api/types";

/**
 * Sandbox management. Both `/tenant/sandbox` reads and writes are untyped
 * `object` responses, so we probe defensively: a truthy `enabled`/`active`
 * flag, or a present `tenant_id`, means a sandbox exists.
 */
export function SandboxTab() {
  const sandbox = useSandbox();
  const create = useCreateSandbox();
  const reset = useResetSandbox();
  const [keepConfig, setKeepConfig] = useState(true);

  const data = sandbox.data;
  const enabled =
    readBool(data ?? {}, "enabled") ??
    readBool(data ?? {}, "active") ??
    (data ? readString(data, "tenant_id") !== null || readString(data, "id") !== null : false);
  const sandboxTenantId = data
    ? readString(data, "sandbox_tenant_id") ?? readString(data, "tenant_id") ?? readString(data, "id")
    : null;

  return (
    <Section
      title="Sandbox"
      description="A parallel test environment with its own data and test-mode API keys. Experiment without touching live records."
      actions={
        !sandbox.isLoading && !sandbox.isError && !enabled ? (
          <Button size="sm" onClick={() => create.mutate()} disabled={create.isPending}>
            {create.isPending ? "Enabling…" : "Enable sandbox"}
          </Button>
        ) : undefined
      }
    >
      {sandbox.isLoading ? (
        <LoadingRows rows={2} />
      ) : sandbox.isError ? (
        <ErrorInline error={sandbox.error} onRetry={() => sandbox.refetch()} title="Couldn't load sandbox" />
      ) : enabled ? (
        <div className="space-y-5">
          <DetailGrid>
            <DetailRow label="Status">
              <StatusBadge value="Enabled" tone="solid" />
            </DetailRow>
            {sandboxTenantId && (
              <DetailRow label="Sandbox tenant">
                <span className="font-mono text-xs break-all">{sandboxTenantId}</span>
              </DetailRow>
            )}
          </DetailGrid>

          <div className="flex items-center justify-between gap-4 rounded-lg border border-destructive/30 px-3 py-2.5">
            <div>
              <p className="text-sm font-medium">Reset sandbox data</p>
              <p className="text-xs text-muted-foreground">
                Wipes all sandbox records. This can't be undone.
              </p>
            </div>
            <ConfirmDialog
              destructive
              title="Reset sandbox data?"
              confirmLabel="Reset sandbox"
              description={
                <span className="flex flex-col gap-3">
                  <span>
                    All records in the sandbox will be permanently deleted. Live data
                    is unaffected.
                  </span>
                  <CheckboxRow
                    checked={keepConfig}
                    onChange={setKeepConfig}
                    label="Keep configuration"
                    description="Preserve sandbox settings (products, pricing) and only clear transactional data."
                  />
                </span>
              }
              onConfirm={async () => {
                await reset.mutateAsync({ keep_config: keepConfig });
              }}
              trigger={
                <Button variant="destructive" size="sm">
                  <RotateCcw />
                  Reset data
                </Button>
              }
            />
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-2 rounded-lg border border-border px-3 py-2.5 text-sm text-muted-foreground">
          <FlaskConical className="size-4" />
          No sandbox yet. Enable one to get an isolated test environment.
        </div>
      )}
    </Section>
  );
}
