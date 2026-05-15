import { useFormContext } from "react-hook-form";
import type { WizardFormValues } from "../lib/schema";

export function IntegrationSnippet() {
  const { watch } = useFormContext<WizardFormValues>();
  const slug = watch("slug");
  const dimensions = watch("dimensions");

  const usageLines = dimensions
    .map((d) => `    ${d.metricName}: ${d.pricingType === "flat" ? "1" : `${d.metricName}Count`}`)
    .join(",\n");

  const snippet = `meter.track({
  pricing_card: "${slug}",
  usage: {
${usageLines}
  }
})`;

  const copy = () => {
    navigator.clipboard.writeText(snippet);
  };

  return (
    <div className="rounded-md border border-border px-3.5 py-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[12px] font-medium">Integration snippet</span>
        <button
          type="button"
          onClick={copy}
          className="text-muted text-blue hover:underline"
        >
          Copy to clipboard
        </button>
      </div>
      <pre className="overflow-x-auto rounded-md bg-bg-subtle px-3 py-2.5 font-mono text-muted leading-[1.8] text-muted-foreground">
        {snippet}
      </pre>
    </div>
  );
}
