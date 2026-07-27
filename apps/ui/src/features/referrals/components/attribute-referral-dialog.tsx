import { useEffect } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { problemMessage } from "@/api/problem";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import { humanize } from "@/lib/labels";
import { toastSuccess } from "@/lib/mutations";

import { useAttributeReferral } from "../api/queries";
import {
  attributeFormSchema,
  isAttributionMethod,
  toAttributeRequest,
  type AttributeFormValues,
} from "../lib/schemas";

export function AttributeReferralDialog({
  open,
  onOpenChange,
  defaultCode,
  defaultLinkToken,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Prefill — usually the current referrer's code / link token. */
  defaultCode?: string;
  defaultLinkToken?: string;
}) {
  const form = useForm<AttributeFormValues>({
    resolver: zodResolver(attributeFormSchema),
    defaultValues: {
      customer_id: "",
      method: "code",
      code: defaultCode ?? "",
      link_token: defaultLinkToken ?? "",
    },
  });
  const mutation = useAttributeReferral();
  const method = form.watch("method");

  useEffect(() => {
    if (open) {
      form.reset({
        customer_id: "",
        method: "code",
        code: defaultCode ?? "",
        link_token: defaultLinkToken ?? "",
      });
      mutation.reset();
    }
    // Reset only when the dialog (re)opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, defaultCode, defaultLinkToken]);

  const submit = form.handleSubmit((values) =>
    mutation.mutate(toAttributeRequest(values), {
      onSuccess: (result) => {
        toastSuccess("Referral attributed", `Status: ${humanize(result.status)}`);
        onOpenChange(false);
      },
    }),
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Attribute a referral</DialogTitle>
          <DialogDescription>
            Bind a referred customer to a referrer. A customer can be attributed once, by the
            referral code or the link token — never both.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4" noValidate>
          <FormField
            label="Referred customer UUID"
            error={form.formState.errors.customer_id?.message}
            hint="The UBB customer UUID of the referred (new) customer — not their external ID."
          >
            {(id) => (
              <Input
                id={id}
                className="font-mono"
                placeholder="9f1c2e34-…"
                autoComplete="off"
                {...form.register("customer_id")}
              />
            )}
          </FormField>
          <FormField label="Attribute by">
            {(id) => (
              <Select
                value={method}
                onValueChange={(value) => {
                  if (typeof value === "string" && isAttributionMethod(value)) {
                    form.setValue("method", value);
                    form.clearErrors(["code", "link_token"]);
                  }
                }}
              >
                <SelectTrigger id={id} className="w-full">
                  <span>{method === "code" ? "Referral code" : "Link token"}</span>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="code">Referral code</SelectItem>
                  <SelectItem value="link_token">Link token</SelectItem>
                </SelectContent>
              </Select>
            )}
          </FormField>
          {method === "code" ? (
            <FormField
              label="Referral code"
              error={form.formState.errors.code?.message}
              hint="The code the referred customer signed up with."
            >
              {(id) => (
                <Input id={id} className="font-mono" autoComplete="off" {...form.register("code")} />
              )}
            </FormField>
          ) : (
            <FormField
              label="Link token"
              error={form.formState.errors.link_token?.message}
              hint="The token from the referrer's shared link."
            >
              {(id) => (
                <Input
                  id={id}
                  className="font-mono"
                  autoComplete="off"
                  {...form.register("link_token")}
                />
              )}
            </FormField>
          )}
          {mutation.error ? (
            <p className="text-xs text-destructive">{problemMessage(mutation.error)}</p>
          ) : null}
          <div className="flex justify-end">
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Working…" : "Attribute referral"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
