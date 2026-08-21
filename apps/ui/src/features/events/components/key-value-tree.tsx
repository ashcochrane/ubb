// Recursive key-value renderer for free-form objects (event metadata and the
// Pricing Receipt). Deliberately NOT a raw JSON dump: primitives render as
// label/value rows, nested objects and lists indent. Defensive — any shape
// renders without throwing.

import { cn } from "@/lib/utils";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isComplex(value: unknown): boolean {
  return (
    (isRecord(value) && Object.keys(value).length > 0) ||
    (Array.isArray(value) && value.length > 0)
  );
}

function leafText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) return "(empty list)";
  if (isRecord(value)) return "(empty)";
  return String(value);
}

export function KeyValueTree({
  value,
  mono = false,
  depth = 0,
}: {
  value: unknown;
  mono?: boolean;
  depth?: number;
}) {
  if (Array.isArray(value) && value.length > 0) {
    return (
      <div className={cn("space-y-1", depth > 0 && "border-l border-border pl-3")}>
        {value.map((item, index) => (
          <div key={index} className="flex items-baseline gap-2">
            <span className="shrink-0 font-mono text-[11px] text-text-muted">
              {index}
            </span>
            <div className="min-w-0 flex-1">
              <KeyValueTree value={item} mono={mono} depth={depth + 1} />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (isRecord(value) && Object.keys(value).length > 0) {
    return (
      <div className={cn("space-y-1", depth > 0 && "border-l border-border pl-3")}>
        {Object.entries(value).map(([key, entry]) =>
          isComplex(entry) ? (
            <div key={key}>
              <div className="text-[12px] font-medium text-text-secondary">
                {key}
              </div>
              <div className="mt-1">
                <KeyValueTree value={entry} mono={mono} depth={depth + 1} />
              </div>
            </div>
          ) : (
            <div
              key={key}
              className="flex items-baseline justify-between gap-4"
            >
              <span className="shrink-0 text-[12px] text-text-secondary">
                {key}
              </span>
              <span
                className={cn(
                  "min-w-0 break-all text-right text-[13px] text-text-primary",
                  mono && "font-mono text-[12px]",
                )}
              >
                {leafText(entry)}
              </span>
            </div>
          ),
        )}
      </div>
    );
  }

  return (
    <span
      className={cn(
        "break-all text-[13px] text-text-primary",
        mono && "font-mono text-[12px]",
      )}
    >
      {leafText(value)}
    </span>
  );
}
