// The one select over a Customer Spend Pool's two modes (#468), shared by the
// customer's own declaration and the workspace's seat default so the two
// forms offer the registry's set in one order under the catalogue's words.
// The words are the select's `items` as well as its options, so the closed
// trigger shows the word for its value rather than the token.

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SPEND_POOL_ENFORCE_MODE_WORDS } from "@/lib/spend-pool";
import { SPEND_POOL_ENFORCE_MODE_VALUES, type SpendPoolEnforceMode } from "@/lib/vocabulary";

export function SpendPoolEnforceModeSelect({
  value,
  onValueChange,
  id,
  disabled,
  ariaLabel,
}: {
  value: SpendPoolEnforceMode;
  onValueChange: (mode: SpendPoolEnforceMode) => void;
  id?: string;
  disabled?: boolean;
  ariaLabel?: string;
}) {
  return (
    <Select
      value={value}
      items={SPEND_POOL_ENFORCE_MODE_WORDS}
      onValueChange={(next) => {
        // The set is closed and every option is one of it; a cleared
        // selection has no mode to declare and changes nothing.
        if (next) onValueChange(next);
      }}
    >
      <SelectTrigger id={id} className="w-full" disabled={disabled} aria-label={ariaLabel}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {SPEND_POOL_ENFORCE_MODE_VALUES.map((mode) => (
          <SelectItem key={mode} value={mode}>
            {SPEND_POOL_ENFORCE_MODE_WORDS[mode]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
