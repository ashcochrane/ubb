import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** Plain-language consequence of confirming. */
  description: React.ReactNode;
  confirmLabel?: string;
  /** Style the confirm button as destructive. */
  destructive?: boolean;
  /** Require typing this exact string before confirm enables (for irreversible actions). */
  typeToConfirm?: string;
  onConfirm: () => void;
  /** Disables buttons while the mutation runs. */
  pending?: boolean;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Confirm",
  destructive = false,
  typeToConfirm,
  onConfirm,
  pending = false,
}: ConfirmDialogProps) {
  const [typed, setTyped] = React.useState("");
  React.useEffect(() => {
    if (!open) setTyped("");
  }, [open]);

  const blocked = typeToConfirm !== undefined && typed !== typeToConfirm;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {typeToConfirm !== undefined && (
          <div className="space-y-1.5">
            <p className="text-[12px] text-text-secondary">
              Type <span className="font-mono font-semibold">{typeToConfirm}</span> to
              confirm.
            </p>
            <Input
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
              autoFocus
              aria-label="Confirmation text"
            />
          </div>
        )}
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={pending}
          >
            Cancel
          </Button>
          <Button
            variant={destructive ? "destructive" : "default"}
            onClick={onConfirm}
            disabled={blocked || pending}
          >
            {pending ? "Working…" : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
