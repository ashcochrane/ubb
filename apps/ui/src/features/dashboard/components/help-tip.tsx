import { HelpCircle } from "lucide-react";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

/** Small inline "?" affordance for a plain-language explanation. */
export function HelpTip({ label, text }: { label: string; text: string }) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger
          aria-label={label}
          className="inline-flex h-4 w-4 items-center justify-center rounded-full text-text-muted transition-colors hover:text-text-primary"
        >
          <HelpCircle className="h-3.5 w-3.5" strokeWidth={1.5} />
        </TooltipTrigger>
        <TooltipContent className="max-w-[260px] text-left leading-snug">
          {text}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
