// A configuration fingerprint, as a long id is shown in this console:
// truncated to fit, whole on hover, and copyable (apps/ui UX ground rules).

import { CopyButton } from "@/components/shared/copy-button";

export function Fingerprint({ value }: { value: string }) {
  return (
    <span className="inline-flex min-w-0 max-w-full items-center gap-1.5 align-middle">
      <code className="truncate font-mono text-[12px]" title={value}>
        {value}
      </code>
      <CopyButton value={value} label="Copy the fingerprint" />
    </span>
  );
}
