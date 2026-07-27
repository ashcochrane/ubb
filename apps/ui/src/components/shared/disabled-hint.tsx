import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Makes the explanation on a disabled control actually reachable.
 *
 * A natively disabled Button gets `disabled:pointer-events-none` and cannot be
 * focused, so a `title` placed directly on it never fires — for mouse users
 * (no hover hit-target) or keyboard users (unfocusable). When `disabled` and
 * `hint` are both set, this wraps the control in a focusable span that carries
 * the tooltip (`title`) and announces the reason to assistive tech
 * (`aria-label`). Otherwise children render untouched.
 *
 * Put the hint HERE, not on the button:
 *
 *   <DisabledHint disabled={!isAdmin} hint="Requires the Admin role.">
 *     <Button disabled={!isAdmin}>Void grant</Button>
 *   </DisabledHint>
 */
export function DisabledHint({
  disabled,
  hint,
  children,
  className,
}: {
  disabled: boolean | undefined;
  hint: string | undefined;
  children: ReactNode;
  className?: string;
}) {
  if (!disabled || !hint) return <>{children}</>;
  return (
    <span
      tabIndex={0}
      title={hint}
      aria-label={hint}
      className={cn("inline-flex rounded-lg outline-none focus-visible:ring-3 focus-visible:ring-ring/50", className)}
    >
      {children}
    </span>
  );
}
