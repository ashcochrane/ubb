import { Link } from "@tanstack/react-router";
import { ArrowLeft, ListChecks } from "lucide-react";
import { useState, type ReactNode } from "react";

import { DetailList } from "@/components/shared/detail-list";
import { DisabledHint } from "@/components/shared/disabled-hint";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { PageHeader } from "@/components/shared/page-header";
import { Section } from "@/components/shared/section";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useHasRole } from "@/hooks/use-current-role";
import { useTenantConfig, useTenantCurrency } from "@/hooks/use-tenant-config";
import { formatDate, formatMicros } from "@/lib/format";
import { tenantDefinedLabel } from "@/lib/localisation";

import { useKindsOfWork, useRuns } from "../api/queries";
import type { KindOfWork, RunRow } from "../api/types";
import {
  altitudeLabel,
  type Ceiling,
  declarationsUnderKey,
  describeCeiling,
  describeDuration,
  describeShare,
  effectiveCeiling,
  pricedRuns,
  PRICING_MODE_EXPLANATIONS,
  pricingModeLabel,
} from "../lib/kinds";
import { DeclareKindDialog } from "./declare-kind-dialog";

/**
 * /tasks/kinds/{key} — one kind of work, as a routed object a colleague can
 * be sent to (#423, spec §25 Q1).
 *
 * One word may name a kind of work at either altitude, and the two are
 * different declarations with different policy — so the page renders every
 * declaration under the key, whole-work altitude first.
 */
export function KindDetailPage({ kindKey }: { kindKey: string }) {
  const kinds = useKindsOfWork();
  const declarations = declarationsUnderKey(kinds.data ?? [], kindKey);
  const soldAtOnePrice = declarations.some((kind) => kind.pricing_mode === "fixed");
  // The runs are read for one thing: the price they were quoted, which is the
  // only wire-borne price a kind of work has (see `pricedRuns`). Only a kind
  // sold at one agreed price pins one, so nothing is fetched otherwise.
  const runs = useRuns({ task_type: kindKey }, { enabled: soldAtOnePrice });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link
          to="/tasks"
          className="inline-flex items-center gap-1 text-[12px] text-text-secondary hover:text-text-primary"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> All kinds of work
        </Link>
        <Link
          to="/tasks/runs"
          search={{ task_type: kindKey }}
          className="text-[12px] text-accent-text underline-offset-2 hover:underline"
        >
          Runs of this kind
        </Link>
      </div>

      {kinds.isLoading ? (
        <Card size="sm" className="p-3">
          <div className="space-y-2">
            <Skeleton className="h-8 w-1/3" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        </Card>
      ) : kinds.isError ? (
        <ErrorCard
          error={kinds.error}
          onRetry={() => void kinds.refetch()}
          title="Couldn't load this kind of work"
        />
      ) : declarations.length === 0 ? (
        <EmptyState
          icon={ListChecks}
          title={`No kind of work named ${kindKey}`}
          description="Nothing in this workspace is declared under that key. It may have been spelled differently, or never declared."
        />
      ) : (
        declarations.map((kind) => (
          <KindOfWorkCard
            key={`${kind.kind}:${kind.key}`}
            kind={kind}
            standing={kinds.data ?? []}
            runs={runs.rows}
            runsSettled={!runs.isLoading}
          />
        ))
      )}
    </div>
  );
}

function KindOfWorkCard({
  kind,
  standing,
  runs,
  runsSettled,
}: {
  kind: KindOfWork;
  standing: readonly KindOfWork[];
  runs: readonly RunRow[];
  runsSettled: boolean;
}) {
  const { data: config } = useTenantConfig();
  const currency = useTenantCurrency();
  const isAdmin = useHasRole("admin");
  const [reviseOpen, setReviseOpen] = useState(false);
  const ceiling = effectiveCeiling(kind, config);

  return (
    <div className="space-y-4">
      <PageHeader
        title={tenantDefinedLabel(kind.key)}
        description={`${altitudeLabel(kind.kind)} · ${pricingModeLabel(kind.pricing_mode)}`}
        actions={
          <>
            {kind.retired ? (
              <Badge variant="secondary">
                Retired{kind.retired_at ? ` ${formatDate(kind.retired_at)}` : ""}
              </Badge>
            ) : (
              <Badge variant="outline">Live</Badge>
            )}
            <DisabledHint disabled={!isAdmin} hint="Requires the Admin role.">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setReviseOpen(true)}
                disabled={!isAdmin}
              >
                Revise ceiling and windows
              </Button>
            </DisabledHint>
          </>
        }
      />

      <Section
        title="How it is sold"
        description="The regime is declared here; the amount is a line in the pricing book, which is the one place prices are edited."
      >
        <HowItIsSold
          kind={kind}
          againstPrice={
            kind.pricing_mode === "fixed" ? (
              <CeilingAgainstPrice
                ceiling={ceiling}
                runs={runs}
                runsSettled={runsSettled}
                currency={currency}
              />
            ) : undefined
          }
        />
      </Section>

      <Section
        title="Spend ceiling and windows"
        description="What one run of this kind may spend on supplier cost, and how long it may run."
      >
        <DetailList
          items={[
            { label: "Ceiling", value: describeCeiling(ceiling, currency) },
            {
              label: "Silence window",
              value: describeDuration(kind.silence_window_seconds) ?? "Workspace default",
            },
            {
              label: "Absolute deadline",
              value: describeDuration(kind.absolute_deadline_seconds) ?? "None",
            },
            {
              label: "Required grouping fields",
              value:
                kind.required_dimensions.length === 0
                  ? "None"
                  : kind.required_dimensions.map(tenantDefinedLabel).join(", "),
              mono: kind.required_dimensions.length > 0,
            },
          ]}
        />
      </Section>

      <DeclareKindDialog
        open={reviseOpen}
        onOpenChange={setReviseOpen}
        standing={standing}
        existing={kind}
      />
    </div>
  );
}

/**
 * The regime, the price as a READ-ONLY LINK into the book, and — for a kind
 * sold at one agreed price — the ceiling shown against that price.
 *
 * THE PRICE IS A LINK AND NOT A NUMBER, ON PURPOSE (#187 §25 Q1, story 57).
 * There is one place prices are edited, and the amount a run is quoted is
 * resolved per customer from that customer's own book at start — so the
 * registry carries no figure for a kind of work and this page invents none.
 */
function HowItIsSold({
  kind,
  againstPrice,
}: {
  kind: KindOfWork;
  /** The ceiling-against-price row, present only for a kind sold at one price. */
  againstPrice?: ReactNode;
}) {
  const fixed = kind.pricing_mode === "fixed";
  return (
    <DetailList
      items={[
        {
          label: "Regime",
          value: (
            <span>
              <span className="font-medium">{pricingModeLabel(kind.pricing_mode)}</span>
              <span className="block text-[12px] text-text-secondary">
                {PRICING_MODE_EXPLANATIONS[kind.pricing_mode]}
              </span>
            </span>
          ),
        },
        {
          label: "Price",
          value: (
            <span>
              <span className="block">
                {fixed
                  ? "One agreed price per delivered run, set as a line in the pricing book."
                  : "Set per event by the rules in the pricing book."}
              </span>
              <Link to="/pricing" className="text-accent-text underline-offset-2 hover:underline">
                Open the pricing books
              </Link>
            </span>
          ),
        },
        ...(againstPrice !== undefined
          ? [{ label: "Ceiling against price", value: againstPrice }]
          : []),
      ]}
    />
  );
}

/**
 * THE CEILING AGAINST THE PRICE (#150 §5.4, rehomed here by #150 §17): a
 * tenant who raises a price and leaves the ceiling alone has silently
 * tightened it in relative terms, and this row is where they see it.
 *
 * The price it is held against is what this kind's runs were actually quoted
 * — one figure when every book agrees, a range when a customer's book differs
 * — and a kind nobody has run yet says so rather than guessing. That lags a
 * repricing by exactly one run, and the copy says so too. The mechanism
 * behind the ceiling is slice 6's; only the rendering lands here.
 */
function CeilingAgainstPrice({
  ceiling,
  runs,
  runsSettled,
  currency,
}: {
  ceiling: Ceiling | null;
  runs: readonly RunRow[];
  runsSettled: boolean;
  currency: string;
}) {
  if (!runsSettled || ceiling === null) return <Skeleton className="h-4 w-48" />;
  const priced = pricedRuns(runs);
  if (priced === null) {
    return (
      <span className="text-text-secondary">
        No run of this kind has pinned a price yet, so the ceiling cannot be shown against
        one.
      </span>
    );
  }
  const onePrice = priced.lowMicros === priced.highMicros;
  const runsWere = priced.runCount === 1 ? "1 run was" : `${priced.runCount} runs were`;
  const quoted = onePrice
    ? `${runsWere} quoted ${formatMicros(priced.lowMicros, currency)}.`
    : `${runsWere} quoted between ${formatMicros(priced.lowMicros, currency)} and ${formatMicros(priced.highMicros, currency)}.`;
  const lag = (
    <span className="text-text-secondary">
      A price changed in the book shows here from the next run.
    </span>
  );
  if (ceiling.source === "uncapped") {
    return (
      <span>
        {quoted}{" "}
        <span className="text-text-secondary">There is no ceiling to hold against it.</span>{" "}
        {lag}
      </span>
    );
  }
  // The share against the HIGH price is the low share, and vice versa; a
  // `null` here means a run was quoted at no charge, which a ceiling cannot
  // be a share of.
  const lowShare = describeShare(ceiling.micros, priced.highMicros);
  const highShare = describeShare(ceiling.micros, priced.lowMicros);
  if (lowShare === null || highShare === null) {
    return (
      <span>
        {quoted}{" "}
        <span className="text-text-secondary">
          A run quoted at no charge has no price for the ceiling to be a share of.
        </span>{" "}
        {lag}
      </span>
    );
  }
  const share = onePrice
    ? `${lowShare} of that price`
    : `between ${lowShare} and ${highShare} of the price`;
  return (
    <span>
      {quoted}{" "}
      <span className="font-medium">
        The {formatMicros(ceiling.micros, currency)} ceiling is {share}.
      </span>{" "}
      <span className="text-text-secondary">
        Raising the price without moving the ceiling tightens it.
      </span>{" "}
      {lag}
    </span>
  );
}
