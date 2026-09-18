// One measure of the one economic query, drawn as what its state says it is
// (#510; slice 7 §19).
//
// `@/lib/measure-state` decides what may be SAID; this decides what is drawn,
// and it sits here rather than in a feature because four features draw it —
// the dashboard, the customers page, billing and the events page — and a
// second copy of the rule inside any of them is how one of them starts
// rendering an unknown as a zero again.
//
// Every rendering of a figure the row carries has `data-measure-state` with the
// state the server sent — including the absent marker a state can still come
// to (a share of nothing) — so a test asserts WHICH state rendered rather than
// matching prose a figure could happen to contain. A figure the row does not
// carry at all has no attribute, because nobody stated anything.

import { OpenSetValue } from "@/components/shared/open-set-value";
import {
  FIGURES_KEY,
  type AnswerCaveats,
  type EconomicsAnswer,
  type MeasureFigure,
  type PlottedFigures,
} from "@/lib/economic-query";
import { ABSENT_LABEL } from "@/lib/localisation";
import {
  horizonNote,
  readingNote,
  readMeasure,
  readShare,
  revenueContextNote,
  type MeasureReading,
} from "@/lib/measure-state";
import { MEASURE_STATUS_LABEL_KEYS } from "@/lib/vocabulary";

/** One reading, drawn. The component the two below share. */
function Reading({
  reading,
  status,
}: {
  reading: MeasureReading;
  status: string | undefined;
}) {
  switch (reading.kind) {
    case "absent":
      return <span data-measure-state={status}>{ABSENT_LABEL}</span>;
    case "figure":
      return <span data-measure-state={status}>{reading.text}</span>;
    case "bound":
      return (
        <span data-measure-state={status} title={reading.note ?? undefined}>
          {reading.text}
        </span>
      );
    case "state":
      // The state's NAME, muted, and never an amount: the sentence that
      // explains it rides as the title, because a card has room for the name
      // and a hover has room for the reason.
      return (
        <span
          data-measure-state={status}
          className="text-text-muted"
          title={reading.note}
        >
          {reading.text}
        </span>
      );
    case "unfamiliar":
      // A state this build cannot read is the token the server sent, marked —
      // through the one helper that owns that rule, never a second copy.
      return (
        <span data-measure-state={status}>
          <OpenSetValue labelKeys={MEASURE_STATUS_LABEL_KEYS} value={reading.status} />
        </span>
      );
  }
}

/** One measure, as its state says it may be drawn. */
export function MeasureValue({
  figure,
  currency,
}: {
  figure: MeasureFigure | null;
  currency: string;
}) {
  return <Reading reading={readMeasure(figure, currency)} status={figure?.status} />;
}

/** The margin as a share of the revenue it was drawn from — carrying the
 *  margin's own state wherever the margin states no figure. */
export function MarginShare({
  margin,
  revenue,
}: {
  margin: MeasureFigure | null;
  revenue: MeasureFigure | null;
}) {
  return <Reading reading={readShare(margin, revenue)} status={margin?.status} />;
}

/**
 * The revenue a finer question could not place, stated beside the surface
 * that asked it — or nothing, where the answer placed it all.
 *
 * ⚠ **THIS IS WHAT KEEPS "UNAVAILABLE AT THIS GRAIN" FROM BEING A SILENT
 * DROP** (§5's third prohibition). The measure itself renders as its state and
 * the margin as none; without this line the tenant would see neither the money
 * nor why no margin is drawn.
 */
export function RevenueContext({
  context,
  currency,
}: {
  context: EconomicsAnswer["context"];
  currency: string;
}) {
  const note = revenueContextNote(context, currency);
  if (note === null) return null;
  return (
    <p data-revenue-context="" className="text-[11px] text-text-muted">
      {note}
    </p>
  );
}

/**
 * Where a window reaches back past the records its answer reads, the day they
 * are held from — or nothing, where it does not. See `horizonNote` for why
 * this is what stands where "no usage" would otherwise be.
 */
export function RetentionHorizonNote({
  caveats,
}: {
  caveats: Pick<AnswerCaveats, "held_from" | "measurement_horizon">;
}) {
  const note = horizonNote(caveats);
  if (note === null) return null;
  return (
    <p data-retention-horizon={caveats.held_from ?? ""} className="text-[11px] text-text-muted">
      {note}
    </p>
  );
}

// ---------------------------------------------------------------------------
// Chart tooltips

/** One plotted series: the row key its number sits under, and its legend. */
export interface TooltipSeries {
  readonly key: string;
  readonly name: string;
  readonly color?: string;
}

/** The part of a Recharts tooltip entry this reads: the row it came from. */
interface TooltipEntry {
  payload?: Record<string, unknown>;
}

/**
 * A chart tooltip that says each series as its state allows.
 *
 * ⚠ **A LINE CANNOT SAY "AT LEAST", AND IT CANNOT SAY "OUT OF HORIZON" EITHER.**
 * A plotted position is a position; where a figure is a bound, the tooltip is
 * where the bound appears (#330's rule), and where there is no figure the line
 * has a GAP — `statedValue` plots null, never zero — and the tooltip is where
 * the gap is named. So each row reads its series off the FIGURES the narrowing
 * stored beside the numbers, not off the numbers: a series with no figure on
 * this point is still listed, as its state, rather than silently absent.
 *
 * It replaces `BoundedCostTooltip`, whose roles treated revenue as whole "at
 * the column" — true until #351 made a price nullable, and never true of a
 * measure of the one query, which carries its own state.
 *
 * The charts render it with `filterNull={false}` so a point whose every series
 * is a gap still gets a tooltip to say why.
 */
export function MeasureTooltip({
  active,
  payload,
  label,
  series,
  currency,
  labelFormatter,
  footer,
}: {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string | number;
  series: readonly TooltipSeries[];
  currency: string;
  labelFormatter: (label: string | number | undefined) => string;
  /** Extra line above the notes (the event count, typically). */
  footer?: (row: Record<string, unknown>) => string | null;
}) {
  const row = payload?.[0]?.payload;
  if (!active || row === undefined) return null;
  const figures = (row[FIGURES_KEY] ?? {}) as PlottedFigures;
  const readings = series.map((entry) => ({
    entry,
    reading: readMeasure(figures[entry.key] ?? null, currency),
  }));
  const notes = [
    ...new Set(
      readings
        .map(({ reading }) => readingNote(reading))
        .filter((note): note is string => note !== null),
    ),
  ];
  const extra = footer ? footer(row) : null;

  return (
    <div className="rounded-md border border-border bg-bg-surface px-3 py-2 text-[11px] shadow-md">
      <div className="mb-1 font-medium text-text-primary">{labelFormatter(label)}</div>
      {readings.map(({ entry, reading }) => (
        <div
          key={entry.key}
          className="flex items-center justify-between gap-4 text-text-secondary"
        >
          <span className="inline-flex items-center gap-1.5">
            {entry.color !== undefined && (
              <span
                className="block h-[7px] w-[7px] rounded-full"
                style={{ backgroundColor: entry.color }}
              />
            )}
            {entry.name}
          </span>
          {/* Drawn, not printed: a state this build cannot read is marked
              through the open-set helper here too, rather than shown as a bare
              token that reads like a word somebody forgot to translate. */}
          <span className="font-medium text-text-primary">
            <Reading reading={reading} status={figures[entry.key]?.status} />
          </span>
        </div>
      ))}
      {(extra !== null || notes.length > 0) && (
        <div className="mt-1 space-y-0.5 border-t border-border pt-1 text-text-muted">
          {extra !== null && <div>{extra}</div>}
          {notes.map((note) => (
            <div key={note}>{note}</div>
          ))}
        </div>
      )}
    </div>
  );
}
