import { Section, QueryState } from "@/components/shared/data-states";
import { StatCard } from "@/components/shared/stat-card";
import { useWebhookConfigs } from "../api/queries";
import { StatGrid, ViewLink } from "./stat-grid";

export function WebhooksHealthSection() {
  const query = useWebhookConfigs();
  return (
    <Section
      title="Webhooks"
      description="Configured outbound endpoints."
      actions={<ViewLink to="/webhooks">View webhooks</ViewLink>}
    >
      <QueryState
        query={query}
        empty={{ title: "No webhook endpoints", description: "Add an endpoint to receive event deliveries." }}
        isEmpty={(d) => d.length === 0}
      >
        {(configs) => {
          const active = configs.filter((c) => c.is_active).length;
          const paused = configs.length - active;
          return (
            <StatGrid>
              <StatCard variant="raised" label="Endpoints" value={configs.length.toLocaleString()} />
              <StatCard variant="raised" label="Active" value={active.toLocaleString()} />
              <StatCard variant="raised" label="Paused" value={paused.toLocaleString()} />
            </StatGrid>
          );
        }}
      </QueryState>
    </Section>
  );
}
