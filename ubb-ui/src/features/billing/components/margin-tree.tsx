// src/features/billing/components/margin-tree.tsx
import { useCallback, useState } from "react";
import type { MarginNode } from "../api/types";
import { MarginTreeRow } from "./margin-tree-row";

interface MarginTreeProps {
  hierarchy: MarginNode[];
  onEdit: (node: MarginNode) => void;
}

export function MarginTree({ hierarchy, onEdit }: MarginTreeProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const toggleExpand = useCallback((id: string) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  }, []);

  const defaultNode = hierarchy[0];
  if (!defaultNode) return null;

  return (
    <div>
      <h2 className="text-[15px] font-bold text-text-primary">Margin hierarchy</h2>
      <p className="mt-1 mb-3 text-[12px] text-text-secondary">
        Margins cascade downward: cards inherit from their product, products inherit from the default. Override at any level.
      </p>

      <div className="overflow-hidden rounded-md border border-border bg-bg-surface">
        {/* Header */}
        <div
          className="grid bg-bg-subtle px-3.5 py-2 text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted"
          style={{ gridTemplateColumns: "minmax(0,1fr) 80px 80px 90px 100px 60px" }}
        >
          <div>Name</div>
          <div className="text-right">Margin</div>
          <div className="text-right">Multiplier</div>
          <div className="text-right">Source</div>
          <div className="text-right">Billings (30d)</div>
          <div className="text-center">Edit</div>
        </div>

        {/* Default row */}
        <MarginTreeRow node={defaultNode} onEdit={onEdit} />

        {/* Products + cards */}
        {defaultNode.children?.map((product) => (
          <div key={product.id}>
            <MarginTreeRow
              node={product}
              expanded={!!expanded[product.id]}
              onToggle={toggleExpand}
              onEdit={onEdit}
              hasChildren={!!product.children?.length}
            />
            {expanded[product.id] && product.children?.map((card) => (
              <MarginTreeRow key={card.id} node={card} onEdit={onEdit} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
