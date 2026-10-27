import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import type { TenantConfig } from "../api/types";

/**
 * UBB v1 is US dollars only (ADR-0023), so there is nothing to choose: the
 * currency is shown, never offered. A picker of currencies the server
 * refuses would be a control whose every other choice is an error.
 */
export function WorkspaceCard({ config }: { config: TenantConfig }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Workspace</CardTitle>
        <CardDescription>
          The basics of this workspace on UBB.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium">Name</p>
            <p className="text-[13px] text-muted-foreground">
              The workspace name can't be changed from the console.
            </p>
          </div>
          <p className="text-sm">{config.name}</p>
        </div>

        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium">Status</p>
            <p className="text-[13px] text-muted-foreground">
              Inactive workspaces stop accepting API traffic.
            </p>
          </div>
          <Badge variant={config.is_active ? "secondary" : "destructive"}>
            {config.is_active ? "Active" : "Inactive"}
          </Badge>
        </div>

        <div className="flex flex-col gap-2">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium">Currency</p>
              <p className="max-w-sm text-[13px] text-muted-foreground">
                Every balance, price, and invoice is in US dollars. UBB
                accepts no other currency and converts none.
              </p>
            </div>
            <p className="text-sm">{config.default_currency.toUpperCase()}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
