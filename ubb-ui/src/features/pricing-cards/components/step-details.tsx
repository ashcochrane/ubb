import { useFormContext } from "react-hook-form";
import type { WizardFormValues } from "../lib/schema";
import { slugify, slugifyWithSuffix } from "../lib/slugify";
import { CardPreview } from "./card-preview";

export function StepDetails() {
  const { register, watch, setValue, formState: { errors } } = useFormContext<WizardFormValues>();
  const description = watch("description") ?? "";

  const nameRegistration = register("name");
  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    nameRegistration.onChange(e);
    setValue("cardId", slugify(e.target.value));
  };

  const handleRegenerate = () => {
    const name = watch("name");
    if (name) setValue("cardId", slugifyWithSuffix(name));
  };

  return (
    <div className="space-y-5">
      <div className="space-y-3">
        <div>
          <label className="mb-1 block text-label font-medium">Card name</label>
          <input
            {...nameRegistration}
            onChange={handleNameChange}
            placeholder="e.g. Mapbox Geocoding API, Internal OCR Service..."
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-[13px] outline-none focus:border-muted-foreground"
          />
          <p className="mt-0.5 text-muted text-muted-foreground">
            Use the API or model name your team would recognise.
          </p>
          {errors.name && <p className="mt-0.5 text-muted text-red">{errors.name.message}</p>}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-label font-medium">Provider</label>
            <input
              {...register("provider")}
              placeholder="e.g. Google, OpenAI, Anthropic..."
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-[13px] outline-none focus:border-muted-foreground"
            />
          </div>

          <div>
            <label className="mb-1 block text-label font-medium">Card ID</label>
            <div className="flex gap-1.5">
              <input
                {...register("cardId")}
                placeholder="auto-generated"
                className="flex-1 rounded-lg border border-border bg-background px-3 py-2 font-mono text-[12px] text-muted-foreground outline-none focus:border-muted-foreground"
              />
              <button
                type="button"
                onClick={handleRegenerate}
                className="shrink-0 rounded-lg border border-border px-2.5 py-2 text-label text-muted-foreground hover:bg-accent"
              >
                Regenerate
              </button>
            </div>
            <p className="mt-0.5 text-muted text-muted-foreground">
              Referenced in SDK calls. Auto-derived from name.
            </p>
          </div>
        </div>
      </div>

      <div className="border-t border-border pt-4 space-y-3">
        <div>
          <label className="mb-1 block text-label font-medium">Description (optional)</label>
          <textarea
            {...register("description")}
            maxLength={250}
            placeholder="e.g. Used for geocoding property addresses in the search pipeline..."
            className="min-h-[56px] w-full rounded-lg border border-border bg-background px-3 py-2 text-[13px] outline-none focus:border-muted-foreground"
          />
          <div className="text-right text-muted text-muted-foreground">
            {description.length} / 250
          </div>
        </div>

        <div>
          <label className="mb-1 block text-label font-medium">Pricing source URL (optional)</label>
          <input
            {...register("pricingSourceUrl")}
            placeholder="https://cloud.google.com/maps-platform/pricing"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-[13px] outline-none focus:border-muted-foreground"
          />
          <p className="mt-0.5 text-muted text-muted-foreground">
            Link to the provider's pricing page for reference.
          </p>
        </div>
      </div>

      <CardPreview />
    </div>
  );
}
