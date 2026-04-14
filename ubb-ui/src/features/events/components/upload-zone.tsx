import { useRef } from "react";

interface UploadZoneProps {
  onFileContent: (content: string) => void;
}

export function UploadZone({ onFileContent }: UploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  function handleFile(file: File) {
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result;
      if (typeof text === "string") onFileContent(text);
    };
    reader.readAsText(file);
  }

  return (
    <div
      className="cursor-pointer rounded-md border-[1.5px] border-dashed border-accent-border py-5 text-center transition-colors hover:border-accent-base hover:bg-accent-ghost"
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        const file = e.dataTransfer.files[0];
        if (file) handleFile(file);
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.tsv"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
        }}
      />
      <div className="text-[12px] font-medium text-accent-text">
        Drop a CSV here or click to browse
      </div>
      <div className="mt-0.5 text-[10px] text-text-secondary">
        We&apos;ll load it into the staging grid for review
      </div>
    </div>
  );
}
