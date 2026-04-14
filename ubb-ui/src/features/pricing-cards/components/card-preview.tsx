import { useFormContext } from "react-hook-form";
import type { WizardFormValues } from "../lib/schema";

export function CardPreview() {
  const { watch } = useFormContext<WizardFormValues>();
  const name = watch("name");
  const provider = watch("provider");
  const cardId = watch("cardId");

  return (
    <div className="rounded-md bg-bg-subtle px-3.5 py-3">
      <div className="mb-2 text-muted text-muted-foreground">Card preview</div>
      <div className="flex items-start gap-2">
        <div className="mt-0.5 h-2 w-2 rounded-full bg-amber" />
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[14px] font-medium">
              {name || "Untitled card"}
            </span>
            <span className="rounded-full bg-muted px-2 py-0.5 text-muted text-muted-foreground">
              Draft
            </span>
          </div>
          {provider && (
            <div className="text-label text-muted-foreground">
              {provider}
            </div>
          )}
          {cardId && (
            <div className="font-mono text-label text-muted-foreground">
              {cardId}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
