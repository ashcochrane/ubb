// src/features/billing/components/margin-tree-row.tsx
import { memo, useCallback } from "react";
import type { MarginNode } from "../api/types";
import { cn } from "@/lib/utils";

interface MarginTreeRowProps {
  node: MarginNode;
  expanded?: boolean;
  onToggle?: (id: string) => void;
  onEdit: (node: MarginNode) => void;
  hasChildren?: boolean;
}

const levelPadding = { default: "pl-3.5", product: "pl-7", card: "pl-12" };

function MarginTreeRowImpl({ node, expanded, onToggle, onEdit, hasChildren }: MarginTreeRowProps) {
  const handleToggle = useCallback(() => {
    onToggle?.(node.id);
  }, [onToggle, node.id]);
  const handleEdit = useCallback(() => {
    onEdit(node);
  }, [onEdit, node]);

  const sourceLabel = node.source === "inherited"
    ? `From ${node.parentSource.toLowerCase().replace(/:\s*\d+%/, "")}`
    : node.source === "set"
      ? "Set"
      : "Override";

  return (
    <div
      className={cn(
        "grid min-h-[44px] items-center border-b border-border/50 text-[12px] transition-colors hover:bg-bg-subtle",
        node.level === "default" && "bg-accent-ghost hover:bg-accent-light",
        node.level === "card" && "bg-bg-raised",
        levelPadding[node.level],
      )}
      style={{ gridTemplateColumns: "minmax(0,1fr) 80px 80px 90px 100px 60px" }}
    >
      {/* Name */}
      <div className="flex items-center gap-2 pr-2">
        {node.level === "product" && hasChildren && (
          <button
            type="button"
            onClick={handleToggle}
            className="flex h-4 w-4 items-center justify-center rounded border border-border-mid bg-bg-surface text-text-muted"
          >
            <svg
              viewBox="0 0 8 8"
              fill="none"
              className={cn("h-2 w-2 transition-transform", expanded && "rotate-90")}
            >
              <path d="M2 1.5l3 2.5-3 2.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        )}
        {node.level === "default" && (
          <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold bg-accent-light text-accent-text">
            Default
          </span>
        )}
        {node.level === "card" && (
          <span className="rounded-full border border-border bg-bg-subtle px-2 py-0.5 text-[10px] font-semibold text-text-secondary">
            Card
          </span>
        )}
        <div>
          <span className={cn(
            node.level === "default" ? "text-[13px] font-semibold text-text-primary" : "text-[13px] font-medium text-text-primary",
            node.level === "card" && "text-[12px]",
          )}>
            {node.name}
          </span>
          {node.level === "default" && (
            <div className="mt-0.5 text-[11px] text-text-muted">Applies to everything without an override</div>
          )}
        </div>
      </div>

      {/* Margin % */}
      <div className={cn(
        "text-right text-[13px] font-bold",
        node.source === "inherited" ? "text-text-secondary" : "text-text-primary",
      )}>
        {node.marginPct}%
      </div>

      {/* Multiplier */}
      <div className="text-right text-[12px] text-text-secondary">
        {node.multiplier.toFixed(2)}×
      </div>

      {/* Source */}
      <div className="text-right">
        {node.source === "set" && (
          <span className="text-[12px] font-medium text-accent-text">Set</span>
        )}
        {node.source === "override" && (
          <span className="rounded-full bg-accent-light px-2 py-0.5 text-[12px] font-semibold text-accent-text">
            Override
          </span>
        )}
        {node.source === "inherited" && (
          <span className="text-[12px] text-text-muted">{sourceLabel}</span>
        )}
      </div>

      {/* Billings */}
      <div className="text-right text-[12px] font-medium text-text-primary">
        ${node.billings30d.toLocaleString()}
      </div>

      {/* Edit */}
      <div className="text-center">
        <button
          type="button"
          onClick={handleEdit}
          className="text-[11px] font-medium text-accent-dark hover:text-accent-base"
          style={{ borderBottom: "1px solid var(--color-accent-border)" }}
        >
          Edit
        </button>
      </div>
    </div>
  );
}

export const MarginTreeRow = memo(MarginTreeRowImpl);
