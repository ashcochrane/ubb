// /spend-controls — the Spend controls tab (#466, #467; slice 6 §18 Q6).
//
// ONE TAB THAT REPORTS ACROSS EVERY FAMILY AND CONFIGURES NOTHING. Each
// family is configured where its subject lives (Q3): a ceiling on the kind of
// work, a customer's pool and floors on the customer's Billing tab, the
// tenant's floors and admission control on Settings. This tab shows the
// workspace's enforcement posture and hosts two reports, tenant-wide, under
// one customer filter and one window: Stops and breaches, with a family
// filter besides, and Utilisation and headroom, which is the Ceiling's alone
// and so offers none. The report shown is URL-backed (`?report=`) so a
// narrowed view of either is a link. It is ungated: the four spend controls
// sit on a kernel concept, and a family a workspace lacks answers no rows.
//
// ⚠ THE POSTURE'S WORD COMES FROM THE LEGACY ADAPTER, AND THAT IS THE ONE
// REVIEWED EXCEPTION. Spec §18 rules that the posture's label "is slice 8's
// ledger entry and is rendered through its existing map without renaming
// it" (`g6-map-enforcement-mode-label`): the registry declares no concept
// for that value set, so there is no label key to bind and no catalogue word
// to render instead. This file is pinned in `tests/contracts/
// test_label_catalogue.py`'s importer list as the explicit act the ratchet's
// own message allows, and leaves it with slice 8.

import { DateRangePicker } from "@/components/shared/date-range-picker";
import { PageHeader } from "@/components/shared/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useTenantConfig } from "@/hooks/use-tenant-config";
import { datetimeWindow, resolveRange } from "@/lib/date-range";
import { enforcementModeLabel } from "@/lib/labels";

import { SPEND_CONTROL_REPORTS, type SpendControlReport, type SpendControlsSearch } from "../lib/search";
import { CustomerFilter, FamilyFilter } from "./filters";
import { StopsAndBreaches, STOPS_AND_BREACHES_TITLE } from "./stops-and-breaches";
import { UTILISATION_AND_HEADROOM_TITLE, UtilisationAndHeadroom } from "./utilisation-and-headroom";

export const CONFIGURES_NOTHING =
  "This tab reports and configures nothing. A ceiling is declared on the kind of work, a customer's pool and floors on the customer's Billing tab, and the workspace's floors and admission control on Settings.";

export interface SpendControlsPageProps {
  /** URL-backed: the route passes it down and receives changes back. */
  search: SpendControlsSearch;
  onSearchChange: (next: SpendControlsSearch) => void;
}

/** The two reports, in the order the tab lists them; the first is the default. */
const REPORT_TITLES: Record<SpendControlReport, string> = {
  stops: STOPS_AND_BREACHES_TITLE,
  utilisation: UTILISATION_AND_HEADROOM_TITLE,
};

export function SpendControlsPage({ search, onSearchChange }: SpendControlsPageProps) {
  const config = useTenantConfig();
  const update = (patch: Partial<SpendControlsSearch>) =>
    onSearchChange({ ...search, ...patch });
  const window = datetimeWindow(resolveRange(search));
  const report: SpendControlReport = search.report ?? "stops";

  return (
    <div className="space-y-4">
      <PageHeader
        title="Spend controls"
        description="What each spend control stopped, what still landed past it, and how much of each ceiling the work used."
        actions={
          <DateRangePicker
            value={{ start_date: search.start_date, end_date: search.end_date }}
            onChange={(range) =>
              update({ start_date: range.start_date, end_date: range.end_date })
            }
          />
        }
      />

      <Card>
        <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-2 py-3">
          <div>
            <p className="text-[11px] text-text-muted">Enforcement posture</p>
            {config.isLoading ? (
              <Skeleton className="h-5 w-24" />
            ) : (
              <p className="text-[13px] font-medium text-text-primary" data-posture={config.data?.enforcement_mode}>
                {enforcementModeLabel(config.data?.enforcement_mode)}
              </p>
            )}
          </div>
          <p className="max-w-prose text-[12px] text-text-secondary">{CONFIGURES_NOTHING}</p>
        </CardContent>
      </Card>

      <Tabs
        value={report}
        onValueChange={(value) => {
          const next = SPEND_CONTROL_REPORTS.find((candidate) => candidate === value);
          // The default report is left out of the URL, as the customer page
          // leaves out its Overview tab.
          update({ report: next !== undefined && next !== "stops" ? next : undefined });
        }}
      >
        <TabsList aria-label="Report">
          {SPEND_CONTROL_REPORTS.map((candidate) => (
            <TabsTrigger key={candidate} value={candidate}>
              {REPORT_TITLES[candidate]}
            </TabsTrigger>
          ))}
        </TabsList>

        <div className="flex flex-wrap items-end gap-4 pt-3">
          <CustomerFilter
            value={search.customer_id}
            onChange={(customer_id) => update({ customer_id })}
          />
          {report === "stops" && (
            <FamilyFilter
              value={search.control_family}
              onChange={(control_family) => update({ control_family })}
            />
          )}
        </div>

        <TabsContent value="stops" className="pt-3">
          <StopsAndBreaches
            filters={{
              customer_id: search.customer_id,
              control_family: search.control_family,
              ...window,
            }}
          />
        </TabsContent>
        <TabsContent value="utilisation" className="pt-3">
          <UtilisationAndHeadroom filters={{ customer_id: search.customer_id, ...window }} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
