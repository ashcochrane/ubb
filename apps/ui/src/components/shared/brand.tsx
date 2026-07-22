import { cn } from "@/lib/utils";

export interface BrandProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

const SIZES: Record<NonNullable<BrandProps["size"]>, string> = {
  sm: "text-[16px]",
  md: "text-[21px]",
  lg: "text-[42px]",
};

export function Brand({ size = "md", className }: BrandProps) {
  return (
    <span
      className={cn(
        "font-serif font-bold leading-none tracking-[-0.5px] text-text-primary",
        SIZES[size],
        className,
      )}
      aria-label="ubb"
    >
      ubb<span className="text-accent-base">.</span>
    </span>
  );
}
