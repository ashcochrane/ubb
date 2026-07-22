import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useDefaultMargin, useUpdateDefaultMargin } from "../api/queries";

export function DefaultMarginPage() {
  const { data, isLoading } = useDefaultMargin();
  const update = useUpdateDefaultMargin();
  const [value, setValue] = useState<string>("");

  useEffect(() => {
    if (data) setValue(String(data.defaultMarginPct));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.defaultMarginPct]);

  if (isLoading || !data) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading…
      </div>
    );
  }

  const parsed = Number.parseFloat(value);
  const valid = Number.isFinite(parsed) && parsed >= 0 && parsed < 100;
  const dirty = valid && parsed !== data.defaultMarginPct;

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!dirty) return;
    update.mutateAsync({ defaultMarginPct: parsed });
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Default margin"
        description="Markup applied to API costs when no product-, card- or customer-level override exists."
      />
      <Card className="max-w-md">
        <CardHeader>
          <CardTitle className="text-base">Default margin</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="default-margin">Default margin (%)</Label>
              <Input
                id="default-margin"
                type="number"
                min={0}
                max={99.99}
                step={0.01}
                value={value}
                onChange={(e) => setValue(e.target.value)}
              />
            </div>
            <Button type="submit" disabled={!dirty || update.isPending}>
              {update.isPending ? "Saving…" : "Save"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
