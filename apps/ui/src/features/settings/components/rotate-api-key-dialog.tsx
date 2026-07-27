import { useState, type ReactNode } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { CopyField } from "@/components/shared/data-states";
import { useRotateApiKey } from "../api/queries";
import { readRawKey } from "../api/types";

/**
 * Rotate an API key: a destructive confirm (the old key stops working
 * immediately) followed by a one-time reveal of the successor's raw secret.
 */
export function RotateApiKeyDialog({
  keyId,
  label,
  trigger,
}: {
  keyId: string;
  label: string;
  trigger: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [revealed, setRevealed] = useState(false);
  const rotate = useRotateApiKey();

  const reset = () => {
    setNewKey(null);
    setRevealed(false);
  };

  const confirm = async () => {
    try {
      const result = await rotate.mutateAsync(keyId);
      setNewKey(readRawKey(result));
      setRevealed(true);
    } catch {
      /* surfaced via toast */
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) reset();
      }}
    >
      <DialogTrigger render={trigger as React.ReactElement} />
      <DialogContent className="sm:max-w-md">
        {revealed ? (
          <>
            <DialogHeader>
              <DialogTitle>Key rotated</DialogTitle>
              <DialogDescription>
                Copy the new secret now — it is shown only once. The previous key
                will fail on its next request.
              </DialogDescription>
            </DialogHeader>
            {newKey ? (
              <CopyField label="New secret key" value={newKey} />
            ) : (
              <p className="text-sm text-muted-foreground">
                The key was rotated but the raw value was not returned by the API.
              </p>
            )}
            <DialogFooter>
              <DialogClose render={<Button />}>Done</DialogClose>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Rotate this key?</DialogTitle>
              <DialogDescription>
                {label ? `"${label}" ` : "This key "}
                will be replaced by a new secret. The old key stops working
                immediately — update your integration right away.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <DialogClose render={<Button variant="outline" disabled={rotate.isPending} />}>
                Cancel
              </DialogClose>
              <Button variant="destructive" onClick={confirm} disabled={rotate.isPending}>
                {rotate.isPending ? "Rotating…" : "Rotate key"}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
