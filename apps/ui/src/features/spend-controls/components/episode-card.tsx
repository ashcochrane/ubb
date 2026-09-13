// One episode of Stops and breaches, drawn by its shape (#466; slice 6 §14,
// §18): a Ceiling row explained by its unit and the events after the stop; a
// Customer spend pool row explained by the Charge that crossed it and that
// Charge's posting; a Wallet policy row with its floor and its episode — or,
// for the soft floor, a marker with nothing to itemise.
//
// Every family word is the catalogue's through `controlFamilyLabel`; every
// stop word renders through the console's one open-set helper, as does the
// mechanism that applied a ceiling's stop; every amount is a reading from
// `../lib/episodes`, so nothing here can coalesce an absence into `$0.00`.

import * as React from "react";
import { Link } from "@tanstack/react-router";
import { ChevronDown, ChevronRight } from "lucide-react";

import { CopyButton } from "@/components/shared/copy-button";
import { DetailList, type DetailItem } from "@/components/shared/detail-list";
import { OpenSetValue } from "@/components/shared/open-set-value";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDate, formatMicros, shortId } from "@/lib/format";
import { tenantDefinedLabel } from "@/lib/localisation";
import { REASON_CODE_LABEL_KEYS, TRIGGER_SOURCE_LABEL_KEYS } from "@/lib/vocabulary";

import type {
  CeilingEpisodeRow,
  CustomerSpendPoolEpisodeRow,
  EpisodeRow,
  WalletPolicyEpisodeRow,
} from "../api/types";
import {
  A_KILL_NEVER_RESUMES,
  ANNOUNCEMENT_GONE,
  BALANCE_UNANNOUNCED,
  ceilingBasisLabel,
  containedWork,
  describeCrossing,
  episodeShape,
  eventCount,
  FLOOR_GONE,
  POOL_ROW_GONE,
  readCrossedCost,
  readFinalCost,
  readItemisedCost,
  readItemisedPrice,
  readSpentAfter,
  SOFT_FLOOR_MARKER,
  STILL_OPEN,
} from "../lib/episodes";
import { controlFamilyLabel } from "../lib/families";
import { ItemisedEventsTable } from "./itemised-events";
import { Reading, Unknown } from "./reading";

function CustomerLink({ customerId }: { customerId: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <Link
        to="/customers/$customerId"
        params={{ customerId }}
        className="font-mono text-[12px] underline-offset-2 hover:underline"
        title={customerId}
      >
        {shortId(customerId)}
      </Link>
      <CopyButton value={customerId} label="Copy customer ID" />
    </span>
  );
}

function span(openedAt: string, closedAt: string | null | undefined): string {
  return `${formatDate(openedAt)} → ${closedAt ? formatDate(closedAt) : STILL_OPEN}`;
}

function ceilingItems(row: CeilingEpisodeRow, currency: string): DetailItem[] {
  const crossed = readCrossedCost(row);
  return [
    {
      label: "Unit of work",
      value: (
        <span className="inline-flex flex-wrap items-center justify-end gap-x-2 gap-y-0.5">
          <Link
            to="/tasks/runs/$taskId"
            params={{ taskId: row.task_id }}
            className="font-mono text-[12px] underline-offset-2 hover:underline"
            title={row.task_id}
          >
            {shortId(row.task_id)}
          </Link>
          <span className="text-[12px] text-text-secondary">
            {tenantDefinedLabel(row.task_type)}
            {containedWork(row) ? " · contained work" : ""}
          </span>
        </span>
      ),
    },
    { label: "Customer", value: <CustomerLink customerId={row.customer_id} /> },
    { label: "Ceiling", value: formatMicros(row.task_cogs_ceiling_micros, currency) },
    { label: "Bounds", value: ceilingBasisLabel(row.ceiling_basis) },
    {
      label: "Applied by",
      value: <OpenSetValue labelKeys={TRIGGER_SOURCE_LABEL_KEYS} value={row.trigger_source} />,
    },
    {
      label: "Known cost when it fired",
      value:
        crossed === null ? (
          <Unknown because={ANNOUNCEMENT_GONE} />
        ) : (
          <Reading reading={crossed} currency={currency} />
        ),
    },
    {
      label: "Known cost where it ended",
      value: <Reading reading={readFinalCost(row)} currency={currency} />,
    },
    { label: "Stopped", value: `${formatDate(row.opened_at)} · ${A_KILL_NEVER_RESUMES}` },
  ];
}

function poolItems(row: CustomerSpendPoolEpisodeRow, currency: string): DetailItem[] {
  return [
    { label: "Customer", value: <CustomerLink customerId={row.customer_id} /> },
    { label: "Period", value: row.period },
    {
      label: "Pool",
      value:
        row.cap_micros == null ? (
          <Unknown because={POOL_ROW_GONE} />
        ) : (
          formatMicros(row.cap_micros, currency)
        ),
    },
    {
      label: "Crossed by",
      value: (
        <span className="inline-flex flex-col items-end gap-0.5" data-crossing={row.crossing_charge_id == null ? "unknown" : row.crossing_marked ? "marked" : "replayed"}>
          {row.crossing_charge_id != null && (
            <span className="inline-flex items-center gap-1 font-mono text-[12px]">
              <span title={row.crossing_charge_id}>Charge {shortId(row.crossing_charge_id)}</span>
              <CopyButton value={row.crossing_charge_id} label="Copy charge id" />
            </span>
          )}
          {row.crossing_posting_id != null && (
            <Link
              to="/events/$eventId"
              params={{ eventId: row.crossing_posting_id }}
              search={{ customer_id: row.customer_id }}
              className="font-mono text-[12px] underline-offset-2 hover:underline"
              title={row.crossing_posting_id}
            >
              posting {shortId(row.crossing_posting_id)}
            </Link>
          )}
          <span className="text-[11px] font-normal text-text-secondary">
            {describeCrossing(row)}
          </span>
        </span>
      ),
    },
    {
      label: "Charged after the crossing",
      value: <Reading reading={readSpentAfter(row)} currency={currency} />,
    },
    {
      label: "Active work stopped",
      value: row.work_stopped_count.toLocaleString(),
    },
    { label: "Starts refused", value: span(row.opened_at, row.closed_at) },
  ];
}

function walletItems(row: WalletPolicyEpisodeRow, currency: string): DetailItem[] {
  const items: DetailItem[] = [
    { label: "Customer", value: <CustomerLink customerId={row.customer_id} /> },
    {
      label: row.soft_floor ? "Soft floor" : "Hard floor",
      value:
        row.floor_micros == null ? (
          <Unknown because={FLOOR_GONE} />
        ) : (
          formatMicros(row.floor_micros, currency)
        ),
    },
    {
      label: "Balance at crossing",
      value:
        row.balance_at_crossing_micros == null ? (
          <Unknown because={BALANCE_UNANNOUNCED} />
        ) : (
          formatMicros(row.balance_at_crossing_micros, currency)
        ),
    },
    {
      label: row.soft_floor ? "Crossed" : `Episode ${row.episode_seq}`,
      value: span(row.opened_at, row.closed_at),
    },
  ];
  return items;
}

export function EpisodeCard({ row, currency }: { row: EpisodeRow; currency: string }) {
  const [open, setOpen] = React.useState(false);
  const episode = episodeShape(row);
  const soft = episode.shape === "wallet_policy" && episode.row.soft_floor;
  const events = row.itemised.events;
  const expandable = events.length > 0;

  const items =
    episode.shape === "ceiling"
      ? ceilingItems(episode.row, currency)
      : episode.shape === "customer_spend_pool"
        ? poolItems(episode.row, currency)
        : walletItems(episode.row, currency);

  return (
    <article
      className="rounded-md border border-border bg-bg-surface"
      data-family={row.control_family}
      data-shape={episode.shape}
      aria-label={`${controlFamilyLabel(row.control_family)} episode`}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-border px-3 py-2">
        <Badge variant="outline">{controlFamilyLabel(row.control_family)}</Badge>
        {soft ? (
          <span className="text-[12px] text-text-secondary">Soft floor crossed</span>
        ) : (
          <span className="text-[13px] font-medium text-text-primary">
            <OpenSetValue labelKeys={REASON_CODE_LABEL_KEYS} value={row.reason_code} />
          </span>
        )}
        <span className="ml-auto text-[12px] text-text-secondary">{formatDate(row.opened_at)}</span>
      </div>
      <div className="px-3">
        <DetailList items={items} />
      </div>
      <div className="border-t border-border px-3 py-2">
        {soft ? (
          <p className="text-[12px] text-text-secondary">{SOFT_FLOOR_MARKER}</p>
        ) : (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-text-secondary">
            <span>
              {eventCount(row.itemised.event_count)} landed past the stop · billed{" "}
              <Reading reading={readItemisedPrice(row.itemised)} currency={currency} /> · provider
              cost <Reading reading={readItemisedCost(row.itemised)} currency={currency} />
            </span>
            {expandable && (
              <Button
                variant="ghost"
                size="sm"
                className="ml-auto"
                onClick={() => setOpen((current) => !current)}
                aria-expanded={open}
              >
                {open ? (
                  <ChevronDown className="h-3.5 w-3.5" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5" />
                )}
                {open ? "Hide events" : "Show events"}
              </Button>
            )}
          </div>
        )}
        {open && expandable && (
          <div className="mt-2">
            <ItemisedEventsTable events={events} currency={currency} />
          </div>
        )}
      </div>
    </article>
  );
}
