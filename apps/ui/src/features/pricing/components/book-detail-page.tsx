import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { ArrowLeft, Plus, Send, Trash2, Layers } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import {
  QueryState,
  Section,
  DetailGrid,
  DetailRow,
  LoadingRows,
  ErrorInline,
  ProductUnavailable,
} from "@/components/shared/data-states";
import { StatusBadge } from "@/components/shared/status-badge";
import { EmptyState } from "@/components/shared/empty-state";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { CursorPagerControls } from "@/components/shared/cursor-pager";
import { formatPrice, formatShortDate, humanizeLabel } from "@/lib/format";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { useBook, useRates, useDeleteRate } from "../api/queries";
import { AddRateDialog } from "./add-rate-dialog";
import { PublishDialog } from "./publish-dialog";

export function BookDetailPage({ bookId }: { bookId: string }) {
  const { hasProduct } = useAuth();
  const navigate = useNavigate();
  const bookQuery = useBook(bookId);

  if (!hasProduct("metering")) {
    return (
      <div className="space-y-6">
        <PageHeader title="Rate card" />
        <ProductUnavailable product="Metering" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Rate card"
        actions={
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate({ to: "/pricing" })}
          >
            <ArrowLeft />
            Back
          </Button>
        }
      />

      <QueryState
        query={bookQuery}
        isEmpty={(b) => b === null}
        empty={{
          title: "Rate card not found",
          description:
            "It may have been deleted, or it lives beyond the first page of cards.",
        }}
      >
        {(book) =>
          book && (
            <div className="space-y-6">
              <Section title="Card">
                <DetailGrid>
                  <DetailRow label="Name">{book.name || "—"}</DetailRow>
                  <DetailRow label="Key">
                    <span className="font-mono text-xs">{book.key}</span>
                  </DetailRow>
                  <DetailRow label="Type">
                    <StatusBadge value={book.card_type} />
                  </DetailRow>
                  <DetailRow label="Provider">{book.provider_key || "—"}</DetailRow>
                  <DetailRow label="Currency">{book.currency || "—"}</DetailRow>
                  <DetailRow label="Version">v{book.version}</DetailRow>
                  <DetailRow label="Default">
                    {book.is_default ? "Yes" : "No"}
                  </DetailRow>
                </DetailGrid>
              </Section>

              <RatesSection bookId={book.id} />
            </div>
          )
        }
      </QueryState>
    </div>
  );
}

function RatesSection({ bookId }: { bookId: string }) {
  const [includeHistory, setIncludeHistory] = useState(false);
  const [asOf, setAsOf] = useState("");
  const pager = useRates(bookId, {
    includeHistory,
    asOf: asOf || undefined,
  });
  const del = useDeleteRate(bookId);

  const actions = (
    <div className="flex items-center gap-2">
      <PublishDialog
        bookId={bookId}
        trigger={
          <Button variant="outline" size="sm">
            <Send />
            Publish changes
          </Button>
        }
      />
      <AddRateDialog
        bookId={bookId}
        trigger={
          <Button size="sm">
            <Plus />
            Add rate
          </Button>
        }
      />
    </div>
  );

  return (
    <Section
      title="Rates"
      description="Publishing changes creates a new version; historical rates are never rewritten."
      actions={actions}
    >
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={includeHistory}
            onChange={(e) => {
              setIncludeHistory(e.target.checked);
              pager.reset();
            }}
            className="size-4 accent-foreground"
          />
          Include history (all versions)
        </label>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          As of
          <Input
            type="date"
            value={asOf}
            className="h-8 w-auto"
            onChange={(e) => {
              setAsOf(e.target.value);
              pager.reset();
            }}
          />
        </label>
      </div>

      {pager.isLoading ? (
        <LoadingRows rows={4} />
      ) : pager.isError ? (
        <ErrorInline error={pager.error} onRetry={pager.refetch} />
      ) : pager.items.length === 0 ? (
        <EmptyState
          icon={Layers}
          title="No rates on this card"
          description="Add a provider rate to start pricing usage against this card."
        />
      ) : (
        <div className="space-y-3">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Metric</TableHead>
                <TableHead>Provider / event</TableHead>
                <TableHead>Model</TableHead>
                <TableHead>Price</TableHead>
                <TableHead>Fixed</TableHead>
                <TableHead>Valid</TableHead>
                <TableHead className="w-8" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {pager.items.map((rate) => (
                <TableRow key={rate.id}>
                  <TableCell className="font-medium">{rate.metric_name}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {rate.provider || "—"}
                    {rate.event_type ? ` / ${rate.event_type}` : ""}
                  </TableCell>
                  <TableCell>{humanizeLabel(rate.pricing_model)}</TableCell>
                  <TableCell className="font-mono text-xs">
                    {formatPrice(rate.rate_per_unit_micros, rate.unit_quantity)}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {formatPrice(rate.fixed_micros, 1)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatShortDate(rate.valid_from)}
                    {rate.valid_to ? ` – ${formatShortDate(rate.valid_to)}` : ""}
                  </TableCell>
                  <TableCell>
                    <ConfirmDialog
                      destructive
                      title="Delete this rate?"
                      description="Usage recorded before now keeps its original price. This can't be undone."
                      confirmLabel="Delete rate"
                      onConfirm={async () => {
                        await del.mutateAsync(rate.id);
                      }}
                      trigger={
                        <Button variant="ghost" size="icon-sm" aria-label="Delete rate">
                          <Trash2 />
                        </Button>
                      }
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <CursorPagerControls pager={pager} />
        </div>
      )}
    </Section>
  );
}
