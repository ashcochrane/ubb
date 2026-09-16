import * as React from "react";

import { ChartCard } from "@/components/shared/chart-card";
import { ChartLegend } from "@/components/shared/chart-legend";
import { ErrorCard } from "@/components/shared/error-card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";

import { useRevenueVsCost } from "../api/queries";
import type { Window } from "../api/types";
import { SectionEmpty } from "./section-empty";

const RevenueCostChart = React.lazy(() => import("./revenue-cost-chart"));

export interface RevenueCostSectionProps {
  window: Window;
  currency: string;
}

// ⚠ THE METERED TITLE AND ITS RELABELLED SERIES ARE GONE (#501), with the
// second definition of revenue they existed to name. One question answers every
// workspace now, so there is one chart and one word for what it plots.

export function RevenueCostSection({
  window,
  currency,
}: RevenueCostSectionProps) {
  const chart = useRevenueVsCost(window);
  const [showMargin, setShowMargin] = React.useState(true);

  const revenueLabel = "Revenue";
  const title = "Revenue vs provider cost";

  const legendItems = [
    { label: revenueLabel, color: "var(--chart-1)" },
    { label: "Provider cost", color: "var(--chart-2)" },
    ...(showMargin
      ? [{ label: "Margin", color: "var(--chart-3)", dashed: true }]
      : []),
  ];

  return (
    <ChartCard
      title={title}
      legend={<ChartLegend items={legendItems} variant="line" className="hidden sm:flex" />}
      actions={
        <div className="flex items-center gap-1.5">
          <Switch
            id="overview-show-margin"
            checked={showMargin}
            onCheckedChange={setShowMargin}
          />
          <Label
            htmlFor="overview-show-margin"
            className="text-[11px] font-normal text-text-muted"
          >
            Margin
          </Label>
        </div>
      }
    >
      {chart.isPending ? (
        <Skeleton className="h-[280px] rounded-md" />
      ) : chart.isError ? (
        <ErrorCard
          error={chart.error}
          title="Couldn't load the revenue chart"
          onRetry={chart.refetch}
        />
      ) : !chart.data || chart.data.length === 0 ? (
        <SectionEmpty
          title="No usage in this window"
          description="Once events are recorded, daily revenue and provider cost land here."
          cta={{ label: "Send a test event", to: "/developers" }}
        />
      ) : (
        <React.Suspense fallback={<Skeleton className="h-[280px] rounded-md" />}>
          <RevenueCostChart
            points={chart.data}
            showMargin={showMargin}
            currency={currency}
            revenueLabel={revenueLabel}
          />
        </React.Suspense>
      )}
    </ChartCard>
  );
}
