import { CopyButton } from "./copy-button";
import { cn } from "@/lib/utils";

/** Monospace block for identifiers, snippets, and raw values, with copy. */
export function CodeBlock({
  value,
  wrap = false,
  className,
}: {
  value: string;
  /** Wrap long values instead of horizontal scrolling. */
  wrap?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-md border border-border bg-bg-subtle px-3 py-2",
        className,
      )}
    >
      <pre
        className={cn(
          "min-w-0 flex-1 font-mono text-[12px] leading-relaxed text-text-primary",
          wrap ? "whitespace-pre-wrap break-all" : "overflow-x-auto",
        )}
      >
        {value}
      </pre>
      <CopyButton value={value} />
    </div>
  );
}
