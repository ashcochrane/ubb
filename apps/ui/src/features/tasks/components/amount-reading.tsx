import { notApplicableReasonLabel } from "@/lib/customer-price";

import {
  describeCustomerPrice,
  describeSupplierCost,
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
 * In a table cell the explanation is the title; on a detail page there is
 * room for the sentence itself.
 */
function Reading({
  kind,
  text,
  qualifier,
  note,
  layout,
}: {
  kind: string;
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
      text={describeSupplierCost(reading, currency)}
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
