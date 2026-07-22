import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { BookText, Plus, ChevronRight, Percent } from "lucide-react";
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
import { StatusBadge } from "@/components/shared/status-badge";
import {
  LoadingRows,
  ErrorInline,
  ProductUnavailable,
} from "@/components/shared/data-states";
import { EmptyState } from "@/components/shared/empty-state";
import { CursorPagerControls } from "@/components/shared/cursor-pager";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { useBooks } from "../api/queries";
import { BookFormDialog } from "./book-form-dialog";

export function PricingPage() {
  const { hasProduct } = useAuth();
  const [cardType, setCardType] = useState("");
  const pager = useBooks(cardType.trim() || undefined);

  if (!hasProduct("metering")) {
    return (
      <div className="space-y-6">
        <PageHeader title="Pricing" />
        <ProductUnavailable product="Metering" />
      </div>
    );
  }

  const actions = (
    <div className="flex items-center gap-2">
      <Button render={<Link to="/pricing/markup" />} variant="outline" size="sm">
        <Percent />
        Markup
      </Button>
      <BookFormDialog
        trigger={
          <Button size="sm">
            <Plus />
            New rate card
          </Button>
        }
      />
    </div>
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Pricing"
        description="A rate card (a “book”) is a versioned set of provider rates. Manage your cards and the rates inside them here."
        actions={actions}
      />

      <div className="max-w-xs">
        <Input
          placeholder="Filter by card type…"
          value={cardType}
          onChange={(e) => {
            setCardType(e.target.value);
            pager.reset();
          }}
        />
      </div>

      {pager.isLoading ? (
        <LoadingRows />
      ) : pager.isError ? (
        <ErrorInline error={pager.error} onRetry={pager.refetch} />
      ) : pager.items.length === 0 ? (
        <EmptyState
          icon={BookText}
          title="No rate cards yet"
          description="Create a rate card to hold your provider rates. Each card is versioned, so publishing changes never rewrites history."
        />
      ) : (
        <div className="space-y-3">
          <div className="rounded-xl bg-card ring-1 ring-foreground/10">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name / key</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Provider</TableHead>
                  <TableHead>Currency</TableHead>
                  <TableHead>Version</TableHead>
                  <TableHead>Default</TableHead>
                  <TableHead className="w-8" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {pager.items.map((book) => (
                  <TableRow key={book.id} className="cursor-pointer">
                    <TableCell>
                      <Link
                        to="/pricing/$bookId"
                        params={{ bookId: book.id }}
                        className="hover:underline"
                      >
                        <div className="font-medium">{book.name || book.key}</div>
                        <div className="font-mono text-xs text-muted-foreground">
                          {book.key}
                        </div>
                      </Link>
                    </TableCell>
                    <TableCell>
                      <StatusBadge value={book.card_type} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {book.provider_key || "—"}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {book.currency || "—"}
                    </TableCell>
                    <TableCell className="font-mono text-xs">v{book.version}</TableCell>
                    <TableCell>
                      {book.is_default ? (
                        <StatusBadge value="Default" tone="solid" />
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Link to="/pricing/$bookId" params={{ bookId: book.id }}>
                        <ChevronRight className="size-4 text-muted-foreground" />
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <CursorPagerControls pager={pager} />
        </div>
      )}
    </div>
  );
}
