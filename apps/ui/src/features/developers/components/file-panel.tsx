// One generated file, with the two ways a developer takes it (#579).

import * as React from "react";

import { Button } from "@/components/ui/button";

import { downloadName, type RenderedFile } from "../lib/artifact";

export function FilePanel({
  file,
  copyLabel,
  onTaken,
}: {
  file: RenderedFile;
  /** What the copy action says — `Copy scaffold` until the verdict is complete. */
  copyLabel: string;
  /** Called once the file has been copied or downloaded. */
  onTaken?: () => void;
}) {
  const [copied, setCopied] = React.useState(false);
  const timeout = React.useRef<number | undefined>(undefined);
  React.useEffect(() => () => window.clearTimeout(timeout.current), []);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(file.contents);
    } catch {
      // Clipboard unavailable (permissions or an insecure context): nothing
      // was taken, so nothing is recorded as held.
      return;
    }
    setCopied(true);
    window.clearTimeout(timeout.current);
    timeout.current = window.setTimeout(() => setCopied(false), 1500);
    onTaken?.();
  };

  const download = () => {
    const url = URL.createObjectURL(new Blob([file.contents], { type: "text/plain" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = downloadName(file.path);
    anchor.click();
    URL.revokeObjectURL(url);
    onTaken?.();
  };

  return (
    <article aria-label={file.path} className="rounded-md border border-border">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-bg-subtle px-3 py-2">
        <code className="font-mono text-[12px] text-text-primary">{file.path}</code>
        <div className="flex items-center gap-1.5">
          <Button size="sm" variant="outline" onClick={() => void copy()}>
            {copied ? "Copied" : copyLabel}
          </Button>
          <Button size="sm" variant="ghost" onClick={download}>
            Download
          </Button>
        </div>
      </header>
      <pre className="max-h-96 overflow-auto px-3 py-2 font-mono text-[12px] leading-relaxed text-text-primary">
        {file.contents}
      </pre>
    </article>
  );
}
