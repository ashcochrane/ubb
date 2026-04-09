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
    <div className="rounded-xl border border-border px-3.5 py-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[12px] font-medium">Integration snippet</span>
        <button
          type="button"
          onClick={copy}
          className="text-[10px] text-blue-600 hover:underline dark:text-blue-400"
        >
          Copy to clipboard
        </button>
      </div>
      <pre className="overflow-x-auto rounded-lg bg-accent/50 px-3 py-2.5 font-mono text-[10px] leading-[1.8] text-muted-foreground">
        {snippet}
      </pre>
      <p className="mt-1.5 text-[10px] text-muted-foreground">
        This snippet updates automatically when you assign a product.
      </p>
    </div>
  );
}
