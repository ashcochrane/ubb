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
import { useCostBooks, usePricingBooks } from "../api/queries";
import type { CostBook, PricingBook } from "../api/types";
import { CreateBookDialog } from "./create-book-dialog";

/**
 * The books list.
 *
 * ⚠ **TWO TABS, AND THERE IS NO "ALL" (#368).** The container split into two
 * separately shaped entities: a Pricing Book is a catalogue of what this
 * tenant charges and names neither a supplier nor a currency; a cost book
 * records what one supplier charges and names both. A combined tab would have
 * to render a table with columns half its rows do not have — which is the
 * conflation the split removed, arriving back as a layout problem. So the two
 * lists are two lists, with the columns each entity actually has.
 */
export function BooksTable({ onOpenBook }: { onOpenBook: (bookId: string) => void }) {
  const [tab, setTab] = React.useState<"pricing" | "cost">("pricing");
  const [createOpen, setCreateOpen] = React.useState(false);
  const isAdmin = useHasRole("admin");
  const pricingBooks = usePricingBooks();
  const costBooks = useCostBooks();
  const books = tab === "pricing" ? pricingBooks : costBooks;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Tabs value={tab} onValueChange={(value) => setTab(value as "pricing" | "cost")}>
          <TabsList>
            <TabsTrigger value="pricing">Pricing books</TabsTrigger>
            <TabsTrigger value="cost">Cost books</TabsTrigger>
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
          title={
            tab === "pricing"
              ? "Couldn't load pricing books"
              : "Couldn't load cost books"
          }
        />
      ) : books.rows.length === 0 ? (
        <EmptyState
          icon={BookOpen}
          title={tab === "pricing" ? "No pricing books yet" : "No cost books yet"}
          description={
            tab === "pricing"
              ? "A pricing book sets what customers are billed. Until one exists, billed cost falls back to your default markup."
              : "A cost book records what one supplier charges you. Declare one, then publish rules for each usage measurement."
          }
          action={
            isAdmin ? { label: "Declare a book", onClick: () => setCreateOpen(true) } : undefined
          }
        />
      ) : (
        <Card size="sm" className="gap-0 py-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Book</TableHead>
                  {tab === "cost" && <TableHead>Supplier</TableHead>}
                  {tab === "cost" && <TableHead>Currency</TableHead>}
                  <TableHead>Version</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {tab === "cost"
                  ? (books.rows as CostBook[]).map((book) => (
                      <CostBookRow
                        key={book.id}
                        book={book}
                        onOpen={() => onOpenBook(book.id)}
                      />
                    ))
                  : (books.rows as PricingBook[]).map((book) => (
                      <PricingBookRow
                        key={book.id}
                        book={book}
                        onOpen={() => onOpenBook(book.id)}
                      />
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

/** The identity cell, which is the half both entities share. */
function BookIdentity({ book }: { book: { key: string; name: string } }) {
  return (
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
  );
}

function rowProps(book: { id: string; key: string; name: string }, onOpen: () => void) {
  return {
    onClick: onOpen,
    onKeyDown: (event: React.KeyboardEvent) => {
      if (event.key === "Enter") onOpen();
    },
    tabIndex: 0,
    role: "link",
    "aria-label": `Open ${book.name || book.key}`,
    className: "cursor-pointer",
  };
}

function PricingBookRow({ book, onOpen }: { book: PricingBook; onOpen: () => void }) {
  return (
    <TableRow {...rowProps(book, onOpen)}>
      <BookIdentity book={book} />
      <TableCell className="text-[12px]">v{book.version}</TableCell>
      <TableCell>
        {book.is_default && <Badge variant="secondary">Default</Badge>}
      </TableCell>
    </TableRow>
  );
}

function CostBookRow({ book, onOpen }: { book: CostBook; onOpen: () => void }) {
  return (
    <TableRow {...rowProps(book, onOpen)}>
      <BookIdentity book={book} />
      <TableCell className="font-mono text-[12px]">
        {book.provider_key || "Any supplier"}
      </TableCell>
      <TableCell className="text-[12px] uppercase">{book.currency}</TableCell>
      <TableCell className="text-[12px]">v{book.version}</TableCell>
      <TableCell>
        {book.is_default && <Badge variant="secondary">Default</Badge>}
      </TableCell>
    </TableRow>
  );
}
