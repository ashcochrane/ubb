// The one control a manual wallet movement's reason is chosen with (#479):
// the registry's six reasons in the catalogue's words, or none. A select
// rather than a text box, because the route refuses anything else by name —
// a typed value could only ever be one of these six or a 422.

import type * as React from "react";

import { MOVEMENT_REASONS, movementReasonLabel } from "@/lib/movement-reason";

export function MovementReasonSelect(props: React.ComponentProps<"select">) {
  return (
    <select
      className="block w-full rounded-md border border-border bg-bg-surface px-2 py-1.5 text-[13px] disabled:opacity-50"
      {...props}
    >
      <option value="">No reason given</option>
      {MOVEMENT_REASONS.map((reason) => (
        <option key={reason} value={reason}>
          {movementReasonLabel(reason)}
        </option>
      ))}
    </select>
  );
}
