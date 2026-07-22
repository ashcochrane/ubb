import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { humanizeLabel } from "@/lib/format";

/**
 * Monochrome status badge for the open backend status/enum strings.
 *
 * Backend statuses are unconstrained strings (only `reward_type` is a real
 * enum), so this maps a known vocabulary of values to a small set of visual
 * "tones" — all grayscale except a single restrained red for failure/danger
 * states — and humanizes anything unrecognised. Never render raw enum strings
 * to users; route them through here.
 */
type Tone = "neutral" | "solid" | "muted" | "danger";

const TONE_CLASS: Record<Tone, string> = {
  // Filled dark — the "good / active / done" tone.
  solid: "bg-primary text-primary-foreground",
  // Outlined — the default "in-progress / informational" tone.
  neutral: "border border-border bg-transparent text-foreground",
  // Quiet gray — "inactive / skipped / terminalised" tone.
  muted: "bg-muted text-muted-foreground",
  // Restrained red — genuine failure / danger only.
  danger: "bg-destructive/10 text-destructive",
};

const VALUE_TONE: Record<string, Tone> = {
  // active / healthy / success
  active: "solid",
  paid: "solid",
  succeeded: "solid",
  success: "solid",
  delivered: "solid",
  completed: "solid",
  complete: "solid",
  connected: "solid",
  enabled: "solid",
  live: "solid",
  published: "solid",
  attributed: "solid",
  rewarded: "solid",
  // in-progress / pending / neutral
  open: "neutral",
  draft: "neutral",
  pending: "neutral",
  processing: "neutral",
  scheduled: "neutral",
  monitor: "neutral",
  advisory: "neutral",
  trialing: "neutral",
  invited: "neutral",
  requires_action: "neutral",
  // inactive / terminal-quiet
  inactive: "muted",
  disabled: "muted",
  archived: "muted",
  canceled: "muted",
  cancelled: "muted",
  void: "muted",
  voided: "muted",
  expired: "muted",
  consumed: "muted",
  skipped: "muted",
  revoked: "muted",
  paused: "muted",
  off: "muted",
  ended: "muted",
  removed: "muted",
  // failure / danger
  failed: "danger",
  failure: "danger",
  error: "danger",
  uncollectible: "danger",
  past_due: "danger",
  suspended: "danger",
  blocked: "danger",
  rejected: "danger",
  unpaid: "danger",
  enforce: "danger",
  fraud: "danger",
  unprofitable: "danger",
};

export function StatusBadge({
  value,
  tone: toneOverride,
  className,
}: {
  value: string | null | undefined;
  tone?: Tone;
  className?: string;
}) {
  if (!value) return <span className="text-muted-foreground">—</span>;
  const key = value.toLowerCase().replace(/\s+/g, "_");
  const tone = toneOverride ?? VALUE_TONE[key] ?? "neutral";
  return (
    <Badge className={cn("rounded-md font-normal", TONE_CLASS[tone], className)}>
      {humanizeLabel(value)}
    </Badge>
  );
}

/** A small on/off pill for booleans (e.g. is_active, enabled). */
export function BoolBadge({
  value,
  trueLabel = "Yes",
  falseLabel = "No",
}: {
  value: boolean;
  trueLabel?: string;
  falseLabel?: string;
}) {
  return (
    <StatusBadge
      value={value ? trueLabel : falseLabel}
      tone={value ? "solid" : "muted"}
    />
  );
}
