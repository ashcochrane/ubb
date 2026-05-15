import { useState } from "react";

interface Props {
  apiKey: string | null;
  onDone: () => void;
  isCompleting: boolean;
}

export function SdkStep({ apiKey, onDone, isCompleting }: Props) {
  const [copied, setCopied] = useState<"key" | "snippet" | null>(null);

  const snippet = apiKey
    ? `import { UBBClient } from "ubb-sdk";
const client = new UBBClient({ apiKey: "${apiKey}" });
await client.usage.record({
  customerId: "cus_123",
  cardId: "<your card id>",
  costMicros: 1000,
});`
    : "";

  const copy = (text: string, kind: "key" | "snippet") => {
    navigator.clipboard.writeText(text);
    setCopied(kind);
    setTimeout(() => setCopied(null), 1500);
  };

  return (
    <div className="space-y-4">
      <div className="text-center">
        <h1 className="text-[18px] font-semibold">Connect the SDK</h1>
        <p className="mt-1 text-[12px] text-muted-foreground">
          Send usage events from your codebase with the key below.
        </p>
      </div>

      {apiKey ? (
        <div>
          <label className="text-[11px] text-muted-foreground">API key</label>
          <div className="flex items-center gap-2">
            <code className="flex-1 rounded border border-border bg-muted px-2 py-1 text-[11px]">
              {apiKey}
            </code>
            <button
              type="button"
              onClick={() => copy(apiKey, "key")}
              className="rounded border border-border px-2 py-1 text-[11px]"
            >
              {copied === "key" ? "Copied" : "Copy"}
            </button>
          </div>
          <p className="mt-1 text-[11px] text-muted-foreground">
            This key is shown once. Store it safely — you can't retrieve it again.
          </p>
        </div>
      ) : (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-[11px] text-amber-900">
          Your API key was shown earlier. If you didn't copy it, you'll need to
          generate a new one from Settings.
        </div>
      )}

      <div>
        <label className="text-[11px] text-muted-foreground">Example snippet</label>
        <pre className="whitespace-pre rounded border border-border bg-muted p-3 text-[11px]">
          {snippet || "// API key unavailable — generate a new one from Settings."}
        </pre>
        {snippet && (
          <button
            type="button"
            onClick={() => copy(snippet, "snippet")}
            className="mt-1 rounded border border-border px-2 py-1 text-[11px]"
          >
            {copied === "snippet" ? "Copied" : "Copy snippet"}
          </button>
        )}
      </div>

      <button
        type="button"
        onClick={onDone}
        disabled={isCompleting}
        className="w-full rounded-lg bg-foreground px-5 py-2 text-[12px] font-medium text-background hover:opacity-90 disabled:opacity-50"
      >
        {isCompleting ? "Finishing…" : "Done"}
      </button>
    </div>
  );
}
