import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Info } from "lucide-react";
import {
  ErrorInline,
  LoadingRows,
  Section,
} from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { usePostpaidConfig, usePutPostpaidConfig } from "../api/queries";
import { postpaidSchema, type PostpaidFormValues } from "../lib/schema";
import type { PostpaidConfig } from "../api/types";

function PostpaidForm({ config }: { config: PostpaidConfig }) {
  const put = usePutPostpaidConfig();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<PostpaidFormValues>({
    resolver: zodResolver(postpaidSchema),
    values: {
      groupBy: config.usage_line_item_group_by ?? "",
      consolidateWithSubscription: config.consolidate_with_subscription ?? false,
    },
  });

  const onSubmit = (v: PostpaidFormValues) =>
    put.mutate({
      usage_line_item_group_by: v.groupBy,
      consolidate_with_subscription: v.consolidateWithSubscription,
    });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <FormField
        label="Usage line-item group-by"
        error={errors.groupBy?.message}
        hint="Dimension used to group metered usage into Stripe invoice line items (e.g. provider, product)."
      >
        {(id) => <Input id={id} placeholder="provider" {...register("groupBy")} />}
      </FormField>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          className="size-4 accent-foreground"
          {...register("consolidateWithSubscription")}
        />
        Consolidate usage onto the subscription invoice rather than a separate invoice
      </label>
      <Button type="submit" disabled={put.isPending}>
        {put.isPending ? "Saving…" : "Save postpaid config"}
      </Button>
    </form>
  );
}

export function PostpaidSection() {
  const { billingMode } = useAuth();
  const query = usePostpaidConfig();
  const isPostpaid = billingMode === "postpaid";

  return (
    <Section
      title="Postpaid config"
      description="How metered usage is pushed to Stripe at period close."
    >
      <div className="space-y-4">
        {!isPostpaid && (
          <Alert>
            <Info />
            <AlertTitle>Only applies to postpaid billing</AlertTitle>
            <AlertDescription>
              This tenant's billing mode is{" "}
              <span className="font-medium">{billingMode ?? "unset"}</span>. These
              settings only take effect when the mode is <em>postpaid</em>.
            </AlertDescription>
          </Alert>
        )}
        {query.isLoading ? (
          <LoadingRows rows={2} />
        ) : query.isError ? (
          <ErrorInline error={query.error} onRetry={() => query.refetch()} />
        ) : query.data ? (
          <PostpaidForm config={query.data} />
        ) : null}
      </div>
    </Section>
  );
}
