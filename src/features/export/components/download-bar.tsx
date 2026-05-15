import { useState, useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import type { ExportFormat, ExportGranularity } from "../api/types";

interface DownloadBarProps {
  format: ExportFormat;
  onFormatChange: (f: ExportFormat) => void;
  granularity: ExportGranularity;
  onGranularityChange: (g: ExportGranularity) => void;
  onDownload: () => void;
  isGenerating: boolean;
  isSuccess: boolean;
  downloadUrl: string | undefined;
}

function SegmentedToggle<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { key: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div>
      <div className="mb-1 text-[11px] font-bold uppercase tracking-[0.07em] text-text-muted">{label}</div>
      <div className="flex">
        {options.map((opt, i) => (
          <button
            key={opt.key}
            className={cn(
              "border px-3 py-1.5 text-[12px] font-medium",
              i === 0 && "rounded-l-md",
              i === options.length - 1 && "rounded-r-md border-l-0",
              i > 0 && i < options.length - 1 && "border-l-0",
              value === opt.key
                ? "border-accent-base bg-accent-base text-text-inverse"
                : "border-border-mid text-text-secondary hover:bg-bg-subtle",
            )}
            onClick={() => onChange(opt.key)}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function DownloadBar({
  format,
  onFormatChange,
  granularity,
  onGranularityChange,
  onDownload,
  isGenerating,
  isSuccess,
  downloadUrl,
}: DownloadBarProps) {
  const [showReady, setShowReady] = useState(false);
  const triggeredUrlRef = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (!isSuccess || !downloadUrl) return;
    if (triggeredUrlRef.current === downloadUrl) return;
    triggeredUrlRef.current = downloadUrl;

    // Trigger the browser download by programmatically clicking an anchor.
    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = ""; // signal to browser to save rather than navigate
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    // Defer setState out of the effect body to avoid cascading renders
    // (react-hooks/set-state-in-effect).
    const showTimer = setTimeout(() => setShowReady(true), 0);
    const hideTimer = setTimeout(() => setShowReady(false), 2500);
    return () => {
      clearTimeout(showTimer);
      clearTimeout(hideTimer);
    };
  }, [isSuccess, downloadUrl]);

  return (
    <div className="flex items-end gap-3">
      <SegmentedToggle
        label="Format"
        options={[
          { key: "csv" as ExportFormat, label: "CSV" },
          { key: "json" as ExportFormat, label: "JSON" },
        ]}
        value={format}
        onChange={onFormatChange}
      />
      <SegmentedToggle
        label="Granularity"
        options={[
          { key: "dimension" as ExportGranularity, label: "By dimension" },
          { key: "event" as ExportGranularity, label: "By event" },
        ]}
        value={granularity}
        onChange={onGranularityChange}
      />
    </div>
  );
}
