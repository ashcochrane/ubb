import { useFormContext } from "react-hook-form";
import type { WizardFormValues } from "../lib/schema";
import type { Template } from "../api/types";
import { useTemplates } from "../api/queries";
import { cn } from "@/lib/utils";

export function StepSource() {
  const { watch, setValue } = useFormContext<WizardFormValues>();
  const sourceType = watch("sourceType");
  const templateId = watch("templateId");
  const { data: templates = [] } = useTemplates();

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-[14px] font-medium">How do you want to start?</h2>
        <p className="text-[12px] text-muted-foreground">
          Pick a pre-built template or configure from scratch.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-2.5">
        <SourceOption
          selected={sourceType === "template"}
          onClick={() => setValue("sourceType", "template")}
          title="From template"
          subtitle="Pre-filled with current API pricing."
        />
        <SourceOption
          selected={sourceType === "custom"}
          onClick={() => {
            setValue("sourceType", "custom");
            setValue("templateId", undefined);
          }}
          title="Custom card"
          subtitle="Configure from scratch for any API."
        />
      </div>

      {sourceType === "template" && templates.length > 0 && (
        <div className="space-y-2">
          <label className="text-label font-medium text-muted-foreground">
            Choose a template
          </label>
          <div className="grid grid-cols-3 gap-2.5">
            {templates.map((t: Template) => (
              <TemplateOption
                key={t.id}
                template={t}
                selected={templateId === t.id}
                onClick={() => setValue("templateId", t.id)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SourceOption({
  selected,
  onClick,
  title,
  subtitle,
}: {
  selected: boolean;
  onClick: () => void;
  title: string;
  subtitle: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-md border border-border bg-bg-surface px-3.5 py-3 text-left transition-colors",
        selected
          ? "border-2 border-foreground"
          : "hover:border-border-mid hover:shadow-md",
      )}
    >
      <div className="text-[13px] font-medium">{title}</div>
      <div className="text-label text-muted-foreground">{subtitle}</div>
    </button>
  );
}

function TemplateOption({
  template,
  selected,
  onClick,
}: {
  template: Template;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-md border border-border bg-bg-surface px-3 py-2.5 text-left transition-colors",
        selected
          ? "border-2 border-foreground"
          : "hover:border-border-mid hover:shadow-md",
      )}
    >
      <div className="text-[12px] font-medium">{template.name}</div>
      <div className="text-label text-muted-foreground">
        {template.dimensionCount} dimensions
      </div>
    </button>
  );
}
