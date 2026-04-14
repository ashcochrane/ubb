// src/features/billing/components/margin-page.tsx
import { useCallback, useState } from "react";
import { PageHeader } from "@/components/shared/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarginDashboard } from "../api/queries";
import type { MarginNode } from "../api/types";
import { MarginStatsGrid } from "./margin-stats";
import { MarginTree } from "./margin-tree";
import { MarginEditPanel } from "./margin-edit-panel";
import { ChangeHistory } from "./change-history";

export function MarginPage() {
  const { data, isLoading } = useMarginDashboard();
  const [editingNode, setEditingNode] = useState<MarginNode | null>(null);

  const handleEdit = useCallback((node: MarginNode) => {
    setEditingNode(node);
  }, []);
  const handleCloseEdit = useCallback(() => {
    setEditingNode(null);
  }, []);

  if (isLoading || !data) {
    return (
      <div className="space-y-6">
        <PageHeader title="Billing margins" />
        <div className="grid grid-cols-4 gap-2.5">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-md" />
          ))}
        </div>
        <Skeleton className="h-60 rounded-md" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Billing margins"
        description="Control how much margin is applied on top of API costs when billing your customers. Changes apply to future events only."
      />

      <MarginStatsGrid stats={data.stats} />

      <MarginTree
        hierarchy={data.hierarchy}
        onEdit={handleEdit}
      />

      {editingNode && (
        <MarginEditPanel
          node={editingNode}
          onClose={handleCloseEdit}
        />
      )}

      <ChangeHistory changes={data.changes} />
    </div>
  );
}
