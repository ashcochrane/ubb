import * as React from "react";
import { BookOpen } from "lucide-react";

import { DisabledHint } from "@/components/shared/disabled-hint";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { LoadMore } from "@/components/shared/load-more";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useHasRole } from "@/hooks/use-current-role";
import { cardTypeLabel } from "@/lib/labels";
import { useBooks } from "../api/queries";
import type { Book } from "../api/types";
import { CreateBookDialog } from "./create-book-dialog";

const TABS = [
  { value: "all", label: "All", cardType: undefined },
  { value: "cost", label: "Cost cards", cardType: "cost" },
  { value: "price", label: "Price cards", cardType: "price" },
] as const;

/** Rate-card books list: tab filter by card type, create dialog, row → detail. */
export function BooksTable({ onOpenBook }: { onOpenBook: (bookId: string) => void }) {
  const [tab, setTab] = React.useState<string>("all");
  const [createOpen, setCreateOpen] = React.useState(false);
  const isAdmin = useHasRole("admin");
  const cardType = TABS.find((candidate) => candidate.value === tab)?.cardType;
  const books = useBooks(cardType);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Tabs value={tab} onValueChange={(value) => setTab(String(value))}>
          <TabsList>
            {TABS.map((candidate) => (
              <TabsTrigger key={candidate.value} value={candidate.value}>
                {candidate.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <DisabledHint disabled={!isAdmin} hint="Requires the Admin role.">
          <Button size="sm" onClick={() => setCreateOpen(true)} disabled={!isAdmin}>
            New book
          </Button>
        </DisabledHint>
      </div>

      {books.isInitialLoading ? (
        <Card size="sm" className="p-3">
          <div className="space-y-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        </Card>
      ) : books.isError ? (
        <ErrorCard
          error={books.error}
          onRetry={() => void books.refetch()}
          title="Couldn't load rate-card books"
        />
      ) : books.rows.length === 0 ? (
        <EmptyState
          icon={BookOpen}
          title={
            cardType === undefined
              ? "No rate-card books yet"
              : `No ${cardTypeLabel(cardType).toLowerCase()}s yet`
          }
          description={
            cardType === "price"
              ? "Price books set what customers are billed. Until one exists, billed cost falls back to your default markup."
              : "Books hold your rates — create one, then add rates for each usage measurement."
          }
          action={
            isAdmin ? { label: "Create a book", onClick: () => setCreateOpen(true) } : undefined
          }
        />
      ) : (
        <Card size="sm" className="gap-0 py-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Book</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Provider</TableHead>
                  <TableHead>Currency</TableHead>
                  <TableHead>Version</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {books.rows.map((book) => (
                  <BookRow key={book.id} book={book} onOpen={() => onOpenBook(book.id)} />
                ))}
              </TableBody>
            </Table>
          </div>
          <LoadMore
            shownCount={books.rows.length}
            hasMore={books.hasMore}
            isFetchingNextPage={books.isFetchingNextPage}
            onLoadMore={books.fetchNextPage}
            noun="books"
          />
        </Card>
      )}

      <CreateBookDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={(book) => onOpenBook(book.id)}
      />
    </div>
  );
}

function BookRow({ book, onOpen }: { book: Book; onOpen: () => void }) {
  return (
    <TableRow
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === "Enter") onOpen();
      }}
      tabIndex={0}
      role="link"
      aria-label={`Open ${book.name || book.key}`}
      className="cursor-pointer"
    >
      <TableCell>
        <div className="min-w-0">
          <p className="truncate text-[13px] font-medium text-text-primary">
            {book.name || book.key}
          </p>
          <p className="truncate font-mono text-[11px] text-text-muted" title={book.key}>
            {book.key}
          </p>
        </div>
      </TableCell>
      <TableCell>
        <Badge variant="outline">{cardTypeLabel(book.card_type)}</Badge>
      </TableCell>
      <TableCell className="font-mono text-[12px]">
        {book.provider_key || "—"}
      </TableCell>
      <TableCell className="text-[12px] uppercase">{book.currency}</TableCell>
      <TableCell className="text-[12px]">v{book.version}</TableCell>
      <TableCell>
        {book.is_default && <Badge variant="secondary">Default</Badge>}
      </TableCell>
    </TableRow>
  );
}
