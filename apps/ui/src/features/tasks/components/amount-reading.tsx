import { notApplicableReasonLabel } from "@/lib/customer-price";

import {
  describeCustomerPrice,
  describeTotal,
  explainCustomerPrice,
  explainSupplierCost,
  type CustomerPriceReading,
  type SupplierCostReading,
} from "../lib/runs";

/**
 * One reading of a total, drawn so that the readings a naive renderer would
 * collapse into `$0.00` stay visibly different things.
 *
 * `data-reading` is the reading's kind, so a test asserts WHICH reading a cell
 * holds rather than matching prose that could be satisfied by the wrong one.
 * The qualifier — WHY a price does not apply, in the catalogue's words — is
 * drawn in both layouts, because the two reasons send a reader to opposite
 * places (#151 §8) and a hover title is not a rendering. In a table cell the
 * longer explanation is the title; on a detail page there is room for it.
 */
function Reading({
  kind,
  text,
  qualifier,
  note,
  layout,
}: {
  kind: CustomerPriceReading["kind"];
  text: string;
  qualifier?: string;
  note: string | null;
  layout: "cell" | "detail";
}) {
  const muted = kind === "unknown";
  if (layout === "cell") {
    return (
      <span
        data-reading={kind}
        className={muted ? "text-text-muted" : undefined}
        title={note ?? undefined}
      >
        {text}
        {qualifier && (
          <span className="block text-[11px] font-normal text-text-secondary">{qualifier}</span>
        )}
      </span>
    );
  }
  return (
    <span data-reading={kind}>
      <span className={muted ? "text-text-muted" : "font-medium"}>{text}</span>
      {qualifier && <span className="ml-1 text-[12px] text-text-secondary">· {qualifier}</span>}
      {note && <span className="block text-[12px] text-text-secondary">{note}</span>}
    </span>
  );
}

export function SupplierCostReadingView({
  reading,
  currency,
  layout = "cell",
}: {
  reading: SupplierCostReading;
  currency: string;
  layout?: "cell" | "detail";
}) {
  return (
    <Reading
      kind={reading.kind}
      text={describeTotal(reading, currency)}
      note={explainSupplierCost(reading)}
      layout={layout}
    />
  );
}

export function CustomerPriceReadingView({
  reading,
  currency,
  layout = "cell",
}: {
  reading: CustomerPriceReading;
  currency: string;
  layout?: "cell" | "detail";
}) {
  return (
    <Reading
      kind={reading.kind}
      text={describeCustomerPrice(reading, currency)}
      qualifier={
        reading.kind === "not_applicable" ? notApplicableReasonLabel(reading.reason) : undefined
      }
      note={explainCustomerPrice(reading)}
      layout={layout}
    />
  );
}
