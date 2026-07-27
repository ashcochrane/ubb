import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { generateWebhookSecret } from "../lib/secret";
import { SecretReveal } from "./secret-reveal";

/**
 * Caller-supplied signing secret field: free-text entry plus a client-side
 * "Generate" (crypto.getRandomValues → 48 hex chars). While a value is
 * present it's echoed in a copyable block with the store-it-now warning,
 * because the API will never show it again.
 */
export function SecretInput({
  label = "Signing secret",
  value,
  onChange,
  error,
}: {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
}) {
  const id = React.useId();
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className="flex gap-2">
        <Input
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          autoComplete="off"
          spellCheck={false}
          className="font-mono"
          placeholder="At least 32 characters"
        />
        <Button
          type="button"
          variant="outline"
          onClick={() => onChange(generateWebhookSecret())}
        >
          Generate
        </Button>
      </div>
      {error ? (
        <p className="text-xs text-destructive">{error}</p>
      ) : (
        <p className="text-xs text-muted-foreground">
          UBB signs every delivery with this secret; your receiver uses it to verify
          signatures. 32–255 characters.
        </p>
      )}
      {value !== "" && <SecretReveal secret={value} />}
    </div>
  );
}
