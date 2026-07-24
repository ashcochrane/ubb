import { humanize } from "@/lib/labels";

/**
 * Curated key-value rendering for audit record metadata — never a raw JSON
 * dump. Objects and arrays nest with an indent guide; primitives render as
 * label → mono value pairs.
 */
export function MetadataTree({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data);
  if (entries.length === 0) {
    return (
      <p className="text-[12px] text-muted-foreground">No details recorded.</p>
    );
  }
  return (
    <div className="space-y-1">
      {entries.map(([key, value]) => (
        <MetadataNode key={key} name={key} value={value} />
      ))}
    </div>
  );
}

function MetadataNode({ name, value }: { name: string; value: unknown }) {
  if (value !== null && typeof value === "object") {
    const entries: [string, unknown][] = Array.isArray(value)
      ? value.map((item, index) => [String(index + 1), item])
      : Object.entries(value as Record<string, unknown>);
    return (
      <div>
        <p className="text-[12px] font-medium text-muted-foreground">
          {humanize(name)}
        </p>
        <div className="ml-1 space-y-1 border-l border-border pl-3">
          {entries.length === 0 ? (
            <p className="text-[12px] text-muted-foreground">Empty</p>
          ) : (
            entries.map(([key, nested]) => (
              <MetadataNode key={key} name={key} value={nested} />
            ))
          )}
        </div>
      </div>
    );
  }
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-[12px] text-muted-foreground">
        {humanize(name)}
      </span>
      <span className="min-w-0 break-all font-mono text-[12px]">
        {formatMetaValue(value)}
      </span>
    </div>
  );
}

function formatMetaValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return value.toLocaleString();
  const text = String(value);
  return text === "" ? "—" : text;
}
