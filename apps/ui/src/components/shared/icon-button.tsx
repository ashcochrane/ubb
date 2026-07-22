import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement>;

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  function IconButton({ className, children, ...props }, ref) {
    return (
      <button
        ref={ref}
        type="button"
        className={cn(
          "flex h-[30px] w-[30px] items-center justify-center rounded-full",
          "border border-border bg-bg-surface text-text-muted",
          "transition-colors hover:bg-bg-subtle hover:text-text-secondary hover:border-border-mid",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40",
          className,
        )}
        {...props}
      >
        {children}
      </button>
    );
  },
);
