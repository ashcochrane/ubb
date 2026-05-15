import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useDeleteCard,
  useDeleteRate,
  usePricingCard,
} from "../api/queries";
import { CardEditForm } from "./card-edit-form";
import { RateEditDialog, type RateEditDialogRate } from "./rate-edit-dialog";

export function CardDetailPage({ cardId }: { cardId: string }) {
  const { data: card, isLoading } = usePricingCard(cardId);
  const deleteCard = useDeleteCard();
  const deleteRate = useDeleteRate(cardId);
  const navigate = useNavigate();

  const [rateDialogOpen, setRateDialogOpen] = useState(false);
  const [editingRate, setEditingRate] = useState<RateEditDialogRate | null>(null);

  if (isLoading || !card) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full max-w-3xl" />
        <Skeleton className="h-48 w-full max-w-3xl" />
      </div>
    );
  }

  async function onDeleteCard() {
    if (!confirm(`Delete card "${card!.name}"?`)) return;
    await deleteCard.mutateAsync(cardId);
    navigate({ to: "/pricing-cards" });
  }

  async function onDeleteRate(rateId: string, metricName: string) {
    if (!confirm(`Delete rate ${metricName}?`)) return;
    await deleteRate.mutateAsync(rateId);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={card.name}
        description={card.description ?? ""}
        actions={
          <Button variant="destructive" onClick={onDeleteCard} disabled={deleteCard.isPending}>
            Delete card
          </Button>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Details</CardTitle>
        </CardHeader>
        <CardContent>
          <CardEditForm card={card} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base">Rates</CardTitle>
          <Button
            onClick={() => {
              setEditingRate(null);
              setRateDialogOpen(true);
            }}
          >
            Add rate
          </Button>
        </CardHeader>
        <CardContent>
          {card.dimensions.length === 0 ? (
            <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
              No rates yet.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Metric</TableHead>
                  <TableHead>Unit</TableHead>
                  <TableHead className="text-right">Cost (micros)</TableHead>
                  <TableHead className="text-right">Per</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {card.dimensions.map((d) => (
                  <TableRow key={d.id}>
                    <TableCell className="font-medium">{d.metricName}</TableCell>
                    <TableCell className="text-muted-foreground">{d.unit}</TableCell>
                    <TableCell className="text-right">{d.costPerUnitMicros}</TableCell>
                    <TableCell className="text-right">{d.unitQuantity}</TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setEditingRate(d as unknown as RateEditDialogRate);
                          setRateDialogOpen(true);
                        }}
                      >
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => onDeleteRate(d.id, d.metricName)}
                      >
                        Delete
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <RateEditDialog
        cardId={cardId}
        open={rateDialogOpen}
        onOpenChange={setRateDialogOpen}
        rate={editingRate ?? undefined}
      />
    </div>
  );
}
