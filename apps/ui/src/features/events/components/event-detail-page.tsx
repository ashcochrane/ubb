// The full receipt for one usage event: identity, timing, money, measurements,
// stop context, the open metadata bag, and the Pricing Receipt's "why this
// amount".
//
// The detail response does NOT carry the customer's id — the ledger link
// forwards it as a search param. Without it the refund action is hidden
// (refunds POST to /billing/customers/{customer_id}/refund).

import { ArrowLeft } from "lucide-react";

import { CopyButton } from "@/components/shared/copy-button";
import { DetailList, type DetailItem } from "@/components/shared/detail-list";
import { ErrorCard } from "@/components/shared/error-card";
import { PageHeader } from "@/components/shared/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useHasProduct } from "@/hooks/use-tenant-config";
import { formatDate } from "@/lib/format";
import {
  customerPriceAmount,
  customerPriceExplanation,
  notApplicableReasonLabel,
  pricingMethodLabel,
  pricingStatusLabel,
  settledPriceMicros,
} from "@/lib/customer-price";
import { ABSENT_LABEL } from "@/lib/localisation";
import { pricingModeLabel } from "@/lib/pricing-mode";
import {
  COSTING_STATUS_EXPLANATIONS,
  costingStatusLabel,
  unresolvedReasonLabel,
} from "@/lib/supplier-cost";

import { useUsageEvent } from "../api/queries";
import {
  asChargeReceiptTerms,
  asStopContextEntries,
  type UsageEventDetail,
} from "../api/types";
import { usageEventKindLabel } from "../lib/kind";
import {
  MEASUREMENTS_STATUS_EXPLANATIONS,
  NO_QUANTITIES_RECORDED,
  measurementsStatusLabel,
} from "../lib/measurements";
import { formatEventMicros, formatSignedEventMicros } from "../lib/money";
import {
  pricingReceiptSubjectTypeLabel,
  receiptExplanation,
} from "../lib/receipt-subject";
import { shortId } from "../lib/search";
import { KeyValueTree } from "./key-value-tree";
import { RefundAction } from "./refund-action";
import { Section } from "./section";
import { StopContextTimeline } from "./stop-context-timeline";
import { TaskSection } from "./task-section";

export interface EventDetailPageProps {
  eventId: string;
  customerId?: string;
  onBack: () => void;
}

function BackLink({ onBack }: { onBack: () => void }) {
  return (
    <button
      type="button"
      onClick={onBack}
      className="inline-flex items-center gap-1 text-[12px] text-text-secondary transition-colors hover:text-text-primary"
    >
      <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
      Back to events
    </button>
  );
}

function idItem(label: string, value: string): DetailItem {
  return {
    label,
    mono: true,
    value: (
      <span className="inline-flex max-w-full items-center gap-1.5">
        <span className="break-all">{value}</span>
        <CopyButton value={value} label={`Copy ${label.toLowerCase()}`} />
      </span>
    ),
  };
}

function measurementRows(detail: UsageEventDetail): Array<[string, string]> {
  return Object.entries(detail.measurements).map(([key, quantity]) => [
    key,
    typeof quantity === "number" ? quantity.toLocaleString() : String(quantity),
  ]);
}

/**
 * The measured quantities, or why there are none.
 *
 * READ THE STATUS FIRST, and read it before the bag — the same order the
 * registry's own decision rule is written in. This section used to render only
 * when the bag had entries, which meant the two states with an empty bag
 * disappeared off the page: a customer whose measurement detail was removed at
 * its retention horizon saw a receipt that looked exactly like one for a Task
 * that was never measured, and both looked like nothing had happened. The
 * quantities are the answer for one of the three states, not the subject of the
 * section.
 */
function Measurements({ detail }: { detail: UsageEventDetail }) {
  const status = detail.measurements_status;
  const rows = measurementRows(detail);
  return (
    <Section
      title="Usage measurements"
      description={MEASUREMENTS_STATUS_EXPLANATIONS[status]}
    >
      {status !== "available" ? (
        <p className="text-[12px] text-text-muted">
          {measurementsStatusLabel(status)}
        </p>
      ) : rows.length > 0 ? (
        <DetailList
          items={rows.map(([key, quantity]) => ({
            label: key,
            value: quantity,
          }))}
        />
      ) : (
        // Only reachable with the record present and holding nothing, which is
        // the one state this sentence is true of.
        <p className="text-[12px] text-text-muted">{NO_QUANTITIES_RECORDED}</p>
      )}
    </Section>
  );
}

/**
 * What a receipt whose subject is a Charge says, said before the record is
 * shown (#425, spec §29).
 *
 * A charge posting's record has an empty costing detail and a pricing detail
 * holding one key, and rendered as a tree that reads as a receipt with
 * something missing from it. Nothing is: the whole unit of work was sold for
 * one agreed price, settled before any of it ran, so there is no measured
 * quantity and no rule for the record to restate. This list says what the
 * record does hold — which Charge it explains, the price that was agreed, the
 * regime the record carries by value, and the Pricing Book line and version
 * that answered — and the tree below it is then the record it always was.
 *
 * THE AMOUNT IS THE POSTING'S OWN, read through `settledPriceMicros` like every
 * other price on this page, and not the record's total: the projection writes
 * both from the Charge's amount, and reading an untyped record for a figure
 * would need a fallback a price may never have. The identifiers come off the
 * record through `asChargeReceiptTerms`, which yields a string or an absence
 * and nothing that could be mistaken for a number.
 */
function ChargeExplanation({ detail }: { detail: UsageEventDetail }) {
  const terms = asChargeReceiptTerms(detail.pricing_receipt);
  const agreed = settledPriceMicros(detail);
  const items: DetailItem[] = [
    {
      label: "Explains",
      value: pricingReceiptSubjectTypeLabel(detail.pricing_receipt_subject_type),
    },
    {
      label: "Agreed price",
      value:
        agreed === null ? ABSENT_LABEL : formatEventMicros(agreed, detail.currency),
    },
    { label: "Sold as", value: pricingModeLabel(terms.pricing_mode) },
    { label: "Charge", value: terms.charge_id, mono: true },
    { label: "Pricing Book line", value: terms.agreed_price_line_id, mono: true },
    { label: "Book version", value: terms.book_version, mono: true },
  ];
  return <DetailList items={items} className="mb-3" />;
}

export function EventDetailPage({
  eventId,
  customerId,
  onBack,
}: EventDetailPageProps) {
  const event = useUsageEvent(eventId);
  const hasBilling = useHasProduct("billing");

  if (event.isLoading) {
    return (
      <div className="space-y-4">
        <BackLink onBack={onBack} />
        <Skeleton className="h-8 w-64" />
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-72 w-full rounded-md" />
          <Skeleton className="h-72 w-full rounded-md" />
        </div>
      </div>
    );
  }

  if (event.isError || !event.data) {
    return (
      <div className="space-y-4">
        <BackLink onBack={onBack} />
        <ErrorCard
          error={event.error}
          onRetry={() => void event.refetch()}
          title="Couldn't load this event"
        />
      </div>
    );
  }

  const detail = event.data;
  const stopEntries = asStopContextEntries(detail.stop_context);
  // A SUPPLIER COST UBB HAS NOT LEARNED IS ABSENT, NOT ZERO (#320). Both rows
  // below fall back to the console's absent marker rather than to a number:
  // rendering `£0.00` would state that the call was free, and a margin computed
  // against that zero would read as the whole billed amount — the flattering
  // direction, on the one screen a tenant opens to check a single event.
  //
  // AND THE ABSENCE IS NAMED (#330). A dash says something is not there; the
  // status says WHICH not-there this is, because a cost UBB could not learn and
  // a cost there was never going to be are opposite facts wearing the same
  // empty cell. There is no "at least" on this screen and that is not an
  // omission: one event has no total to be a floor of — it has the mark itself.
  // AND THE SAME IS NOW TRUE OF THE CUSTOMER PRICE (#351). It went nullable
  // with a status of its own, so a price UBB could not resolve reaches this
  // screen as an absence and must render as one: `£0.00` here would tell a
  // tenant they charged their customer nothing, which is the unflattering
  // direction of the identical mistake. The margin needs BOTH sides, so it is
  // absent when either is.
  //
  // ⚠ THE MARGIN READS THE STATUS TOO, THROUGH THE SAME FUNCTION THE AMOUNT
  // DOES (#371). Guarding the displayed price with the status while computing
  // the margin off the raw column would put a dash in the Billed row and a real
  // signed figure below it, derived from the very zero the dash exists to deny —
  // and the two would sit four lines apart on one screen. `settledPriceMicros`
  // is the only place either of them asks.
  const providerCost = detail.provider_cost_micros ?? null;
  const billed = settledPriceMicros(detail);
  const margin =
    providerCost === null || billed === null ? null : billed - providerCost;
  const hasMetadata = Object.keys(detail.metadata).length > 0;
  const hasReceipt = Object.keys(detail.pricing_receipt).length > 0;
  const backfilled =
    detail.created_at.slice(0, 10) !== detail.effective_at.slice(0, 10);

  // THE SECOND CORRELATION ROW IS GONE AND HAS NO REPLACEMENT (#411, spec §25).
  // The posting used to carry a second caller-supplied correlation value beside
  // the idempotency key, and this list showed both. The field is deleted, and
  // the row is DROPPED rather than repointed at a metadata key: a tenant's own
  // metadata has no fixed name, so the console would have to guess a label for
  // it — which is precisely the identity/expression defect ADR-0008 §4 exists
  // to remove. Their metadata is already rendered as metadata, below.
  const identityItems: DetailItem[] = [
    idItem("Event ID", detail.id),
    idItem("Idempotency key", detail.idempotency_key),
    // WHICH KIND OF POSTING THIS IS (#417, #425), in the catalogue's words. A
    // charge posting names no Event Type and no provider — no caller reported
    // it — so without this row the page had nothing that said what kind of
    // row a reader had opened, and an empty measurement section under it
    // read as missing data.
    { label: "Kind", value: usageEventKindLabel(detail.kind) },
    { label: "Happened at", value: formatDate(detail.effective_at) },
    {
      label: "Recorded at",
      value: backfilled
        ? `${formatDate(detail.created_at)} (backfilled)`
        : formatDate(detail.created_at),
    },
    ...(detail.event_type !== ""
      ? [{ label: "Event type", value: detail.event_type }]
      : []),
    ...(detail.provider !== ""
      ? [{ label: "Provider", value: detail.provider }]
      : []),
    // The posting's grouping values, labelled with the key the tenant declared
    // (#277). This used to be three rows reading "Dimension 1..3" — console
    // English for a slot number the tenant never chose, and only ever three of
    // the ten that exist. The response is now keyed by the declared key, so the
    // label is the tenant's own word and every declared field shows up.
    ...Object.entries(detail.grouping_fields).map(([key, value]) => ({
      label: key,
      value,
    })),
  ];

  // THE TWO SIDES ARE TWO SECTIONS NOW (#371), and the split is what the
  // absences forced. Each is an amount with a status of its own and a cause of
  // its own, and each owes the reader a sentence saying which not-there this
  // is — one section could carry one description, so the price half's was the
  // one that went unsaid. #351 stopped the customer price rendering as `£0.00`
  // and left NAMING it to this commit, exactly as #317 stopped the supplier
  // half's zero and #330 named it.
  const priceItems: DetailItem[] = [
    {
      label: "Billed",
      // Reads the STATUS rather than testing the amount for null, which is the
      // rule `@/lib/customer-price` exists to hold: a zero beside `waived`
      // renders as money under the amount test and as the absence it is under
      // this one.
      value: customerPriceAmount(detail, (micros) =>
        formatEventMicros(micros, detail.currency),
      ),
    },
    { label: "Price status", value: pricingStatusLabel(detail.pricing_status) },
    // ⚠ HOW THE PRICE WAS DERIVED, PER EVENT, AND IT IS NOT A PROPERTY OF THE
    // EVENT TYPE (#372, spec §21). Two events of the SAME Event Type may
    // legitimately read differently here — one cost-plus for a customer on a
    // margin deal, one flat for a customer on a negotiated price — because the
    // receipt records the method and the applied value per event, BY VALUE,
    // precisely so it can be shown. That is not a bug for the UI to smooth
    // over: a screen that derived the method from the Event Type instead would
    // have to pick one of the two and be wrong for the other customer, on the
    // one screen a tenant opens to check a single charge.
    //
    // Read only where there is one. It is nullable on the wire and null is an
    // ordinary state — no method derived a price that was never resolved — so a
    // row here would be a label with nothing to say.
    ...(detail.pricing_method != null
      ? [
          {
            label: "Priced by",
            value: pricingMethodLabel(detail.pricing_method),
          },
        ]
      : []),
    // Read only where the status is `not_applicable`, and never on its own —
    // the registry's rule, and the same one the missing input follows below. A
    // status saying a price does not apply without saying WHY sends a reader
    // looking for a number nobody wrote, and the two causes send them to
    // opposite places: one to the Task's own charge, one nowhere at all.
    ...(detail.pricing_status === "not_applicable" &&
    detail.not_applicable_reason != null
      ? [
          {
            label: "Why",
            value: notApplicableReasonLabel(detail.not_applicable_reason),
          },
        ]
      : []),
    // ONE POSTING, ONE CURRENCY, said once. It denominates both amounts on this
    // screen, so repeating it under the supplier cost would be the same fact
    // twice — and the first place a reader looks for what they were charged in
    // is beside what they were charged.
    { label: "Currency", value: detail.currency.toUpperCase() },
  ];

  const costItems: DetailItem[] = [
    {
      label: "Provider cost",
      value:
        providerCost === null
          ? ABSENT_LABEL
          : formatEventMicros(providerCost, detail.currency),
    },
    { label: "Cost status", value: costingStatusLabel(detail.costing_status) },
    // Read only where the status is `unresolved`, and never on its own: a
    // status saying a cost is missing without saying WHAT would settle it is a
    // shrug rather than something a tenant can act on.
    ...(detail.costing_status === "unresolved"
      ? [
          {
            label: "Missing input",
            value: unresolvedReasonLabel(detail.unresolved_reason),
          },
        ]
      : []),
    {
      // Beside the COST rather than beside the price, because the cost is the
      // side that bounds it: `@/lib/supplier-cost`'s `marginBound` owns the
      // rule that a margin computed against a partial cost is a ceiling, and a
      // margin needs both halves so it can sit under only one of them.
      label: "Margin on this event",
      value:
        margin === null
          ? ABSENT_LABEL
          : formatSignedEventMicros(margin, detail.currency),
    },
  ];

  return (
    <div className="space-y-4">
      <BackLink onBack={onBack} />
      <PageHeader
        title="Event receipt"
        description={`Event ${shortId(detail.id)} — recorded ${formatDate(detail.created_at)}`}
        actions={
          customerId !== undefined && hasBilling ? (
            <RefundAction detail={detail} customerId={customerId} />
          ) : undefined
        }
      />

      <div className="grid items-start gap-4 lg:grid-cols-2">
        <Section title="Details">
          <DetailList items={identityItems} />
        </Section>

        <div className="space-y-4">
          <Section
            title="Customer price"
            description={customerPriceExplanation(detail)}
          >
            <DetailList items={priceItems} />
          </Section>

          <Section
            title="Supplier cost"
            description={COSTING_STATUS_EXPLANATIONS[detail.costing_status]}
          >
            <DetailList items={costItems} />
          </Section>

          <Measurements detail={detail} />
        </div>

        {stopEntries.length > 0 && (
          <Section
            title="Stop context"
            description="This event landed past a spend stop. It was still recorded and billed — every event that reaches UBB is."
          >
            <StopContextTimeline entries={stopEntries} />
          </Section>
        )}

        {detail.task_id && <TaskSection taskId={detail.task_id} />}

        {hasMetadata && (
          <Section title="Metadata" className="lg:col-span-2">
            <KeyValueTree value={detail.metadata} />
          </Section>
        )}

        {/* The record took its ratified name on the wire in #370 and the
            heading came with it: a screen calling it something the API does
            not is the second public name for one concept ADR-0006 §2 refuses.
            #370 handed the QUALIFICATION forward to this commit, and here it
            is, in the console's own words rather than the schema's.

            ⚠ WHY IT HAS TO BE SAID AT ALL. A receipt is the record of an
            ECONOMIC RESOLUTION — what UBB resolved, how, and as of when — and
            every event gets one, including on a workspace that meters and does
            not bill anybody. So a heading reading "Pricing receipt" over a
            block of numbers is, on its own, an invitation to read the presence
            of a receipt as proof that a customer was charged. It is not: the
            Customer price section above is where that question is answered, and
            on a metering-only workspace it answers "no charge exists anywhere".
            The sentence is console copy rather than the schema's `description`
            for the ordinary reason — the wire's prose is written for whoever is
            integrating, and this is written for whoever is reading a receipt.

            AND THE SUBJECT DECIDES WHICH SENTENCE (#425, spec §29). The wire
            states what a receipt explains — one usage event, or one Charge —
            and a charge's record explains a price that was agreed rather than
            derived, so it is opened with a sentence saying so and a list of
            what it holds, before the record itself. `../lib/receipt-subject`
            owns both sentences. */}
        <Section
          title="Pricing receipt"
          description={receiptExplanation(detail.pricing_receipt_subject_type)}
          className="lg:col-span-2"
        >
          {hasReceipt ? (
            <>
              {detail.pricing_receipt_subject_type === "charge" && (
                <ChargeExplanation detail={detail} />
              )}
              <KeyValueTree value={detail.pricing_receipt} mono />
            </>
          ) : (
            <p className="text-[12px] text-text-muted">
              No receipt was recorded for this event.
            </p>
          )}
        </Section>
      </div>
    </div>
  );
}
