// The return-once modal: raw API keys are shown exactly once, here, and can
// never be fetched again. Used by key create, key rotate, and sandbox mint.

import { KeyRound } from "lucide-react";

import { CodeBlock } from "@/components/shared/code-block";
import { DetailList, type DetailItem } from "@/components/shared/detail-list";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export interface MintedKey {
  title: string;
  description: string;
  apiKey: string;
  details: DetailItem[];
}

export function RawKeyDialog({
  minted,
  onClose,
}: {
  minted: MintedKey | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={minted !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg">
        {minted && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <KeyRound className="h-4 w-4" strokeWidth={1.5} />
                {minted.title}
              </DialogTitle>
              <DialogDescription>{minted.description}</DialogDescription>
            </DialogHeader>
            <CodeBlock value={minted.apiKey} wrap />
            <p className="text-[13px] font-medium text-text-primary">
              This is the only time UBB shows this key.
            </p>
            <p className="text-[12px] text-text-secondary">
              Store it somewhere safe now — UBB keeps only a hash, so it can
              never be retrieved again. If it's lost, rotate the key to mint a
              replacement.
            </p>
            {minted.details.length > 0 && <DetailList items={minted.details} />}
            <DialogFooter>
              <Button onClick={onClose}>Done</Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
