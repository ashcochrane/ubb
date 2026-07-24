import * as React from "react";
import { Check, Copy } from "lucide-react";

import { cn } from "@/lib/utils";

/** Small copy-to-clipboard affordance with a transient "copied" check. */
export function CopyButton({
  value,
  label = "Copy",
  className,
}: {
  value: string;
  label?: string;
  className?: string;
}) {
  const [copied, setCopied] = React.useState(false);
  const timeout = React.useRef<number | undefined>(undefined);

  React.useEffect(() => () => window.clearTimeout(timeout.current), []);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.clearTimeout(timeout.current);
      timeout.current = window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard unavailable (permissions/insecure context) — leave state as-is.
    }
  };

  return (
    <button
      type="button"
      onClick={copy}
      aria-label={copied ? "Copied" : label}
      className={cn(
        "inline-flex h-6 w-6 shrink-0 items-center justify-center rounded border border-border text-text-secondary transition-colors hover:bg-bg-subtle hover:text-text-primary",
        className,
      )}
    >
      {copied ? (
        <Check className="h-3 w-3" strokeWidth={2} />
      ) : (
        <Copy className="h-3 w-3" strokeWidth={1.5} />
      )}
    </button>
  );
}
