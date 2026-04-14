import { cn } from "@/lib/utils";

export type AddMode = "row" | "paste" | "upload" | null;

interface AddDataStripProps {
  mode: AddMode;
  onModeChange: (mode: AddMode) => void;
}

const modes = [
  { key: "row" as const, title: "+ Add rows", subtitle: "Type directly into the grid" },
  { key: "paste" as const, title: "Paste data", subtitle: "From a spreadsheet" },
  { key: "upload" as const, title: "Upload CSV", subtitle: "Import a file" },
];

export function AddDataStrip({ mode, onModeChange }: AddDataStripProps) {
  return (
    <div className="flex gap-2">
      {modes.map((m) => (
        <button
          key={m.key}
          className={cn(
            "flex-1 rounded-md border-[1.5px] border-dashed py-2.5 text-center transition-all",
            mode === m.key
              ? "border-solid border-accent-border bg-accent-ghost text-accent-text"
              : "border-border-mid text-text-secondary hover:border-accent-border hover:text-accent-text",
          )}
          onClick={() => onModeChange(mode === m.key ? null : m.key)}
        >
          <div className="text-[12px] font-medium">{m.title}</div>
          <div className="text-[10px] opacity-70">{m.subtitle}</div>
        </button>
      ))}
    </div>
  );
}
