import { useFormContext } from "react-hook-form";
import type { WizardFormValues } from "../lib/schema";

export function IntegrationSnippet() {
  const { watch } = useFormContext<WizardFormValues>();
  const cardId = watch("cardId");
  const product = watch("product");
  const dimensions = watch("dimensions");

  const usageLines = dimensions
    .map((d) => `    ${d.key}: ${d.type === "flat" ? "1" : `${d.key}Count`}`)
    .join(",\n");

  const productLine = product ? `\n  product: "${product}",` : "";

  const snippet = `meter.track({
  pricing_card: "${cardId}",${productLine}
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
      <p className="mt-1.5 text-muted text-muted-foreground">
        This snippet updates automatically when you assign a product.
      </p>
    </div>
  );
}
