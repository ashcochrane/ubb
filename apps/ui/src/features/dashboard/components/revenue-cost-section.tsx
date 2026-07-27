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
  meterOnly: boolean;
  currency: string;
}

export function RevenueCostSection({
  window,
  meterOnly,
  currency,
}: RevenueCostSectionProps) {
  const chart = useRevenueVsCost(window);
  const [showMargin, setShowMargin] = React.useState(true);

  const billedLabel = meterOnly ? "Usage billed" : "Billed revenue";
  const title = meterOnly
    ? "Usage billed vs provider cost"
    : "Revenue vs provider cost";

  const legendItems = [
    { label: billedLabel, color: "var(--chart-1)" },
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
      ) : !chart.points || chart.points.length === 0 ? (
        <SectionEmpty
          title="No usage in this window"
          description="Once events are recorded, daily billed and provider cost land here."
          cta={{ label: "Send a test event", to: "/developers" }}
        />
      ) : (
        <React.Suspense fallback={<Skeleton className="h-[280px] rounded-md" />}>
          <RevenueCostChart
            points={chart.points}
            showMargin={showMargin}
            currency={currency}
            billedLabel={billedLabel}
          />
        </React.Suspense>
      )}
    </ChartCard>
  );
}
