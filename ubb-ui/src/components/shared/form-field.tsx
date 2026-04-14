import { useId } from "react";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export interface FormFieldProps {
  label: string;
  error?: string;
  hint?: string;
  className?: string;
  children: (id: string) => React.ReactNode;
}

/**
 * Wraps a label + input + error/hint text. The `children` prop is a render
 * function that receives a stable generated id so consumers can wire it to
 * their input's `id` (and the label's `htmlFor` is set automatically).
 *
 * Example:
 *   <FormField label="Stripe key" error={errors.key?.message}>
 *     {(id) => <Input id={id} {...register("key")} />}
 *   </FormField>
 */
export function FormField({
  label,
  error,
  hint,
  className,
  children,
}: FormFieldProps) {
  const id = useId();

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Label htmlFor={id}>{label}</Label>
      {children(id)}
      {error ? (
        <p className="text-xs text-destructive">{error}</p>
      ) : hint ? (
        <p className="text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}
