import { Link } from "@tanstack/react-router";
import { ArrowRight, CheckCircle2, Circle } from "lucide-react";
import type { UseQueryResult } from "@tanstack/react-query";

import { problemMessage } from "@/api/problem";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import {
  useApiKeysCheck,
  useConnectStatus,
  usePricingBooksCheck,
} from "../api/queries";

type CheckState = "loading" | "done" | "todo" | "unknown";

type StepTo = "/developers" | "/pricing" | "/settings";

interface Step {
  key: string;
  title: string;
  description: string;
  to: StepTo;
  linkLabel: string;
  state: CheckState;
  /** Set when state === "unknown" (the check itself failed). */
  errorText?: string;
  retry?: () => void;
}

function checkState<T>(
  query: UseQueryResult<T>,
  isDone: (data: T) => boolean,
): CheckState {
  if (query.isPending) return "loading";
  if (query.isError) return "unknown";
  return isDone(query.data) ? "done" : "todo";
}

/**
 * Shown only when the workspace has never recorded an event. Every checkmark
 * is driven by real state (keys, pricing books, events, Stripe) — no fake
 * progress. `needsStripe` is true for tenants with the billing product.
 */
export function GettingStartedCard({ needsStripe }: { needsStripe: boolean }) {
  const keys = useApiKeysCheck();
  const books = usePricingBooksCheck();
  const connect = useConnectStatus(needsStripe);

  const steps: Step[] = [
    {
      key: "api-key",
      title: "Create an API key",
      description: "Your backend authenticates with a key to record usage.",
      to: "/developers",
      linkLabel: "Open developers",
      state: checkState(keys, (page) => page.data.length > 0),
      errorText: keys.isError ? problemMessage(keys.error) : undefined,
      retry: () => void keys.refetch(),
    },
    {
      key: "pricing-book",
      title: "Set up pricing",
      description: "Create a pricing book so every event gets priced.",
      to: "/pricing",
      linkLabel: "Open pricing",
      state: checkState(books, (page) => page.data.length > 0),
      errorText: books.isError ? problemMessage(books.error) : undefined,
      retry: () => void books.refetch(),
    },
    {
      // This card only renders while the workspace has zero recorded events,
      // so the recording step is always still to do.
      key: "first-event",
      title: "Record your first usage event",
      description: "Send a test event from the developers page to see live numbers here.",
      to: "/developers",
      linkLabel: "Send a test event",
      state: "todo",
    },
    ...(needsStripe
      ? [
          {
            key: "stripe",
            title: "Connect Stripe",
            description: "Billing needs a connected Stripe account to move money.",
            to: "/settings",
            linkLabel: "Open settings",
            state: checkState(connect, (status) => status.onboarded),
            errorText: connect.isError ? problemMessage(connect.error) : undefined,
            retry: () => void connect.refetch(),
          } satisfies Step,
        ]
      : []),
  ];

  const anyLoading = steps.some((step) => step.state === "loading");
  const doneCount = steps.filter((step) => step.state === "done").length;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Get started with UBB</CardTitle>
        <CardDescription>
          This workspace hasn't recorded any usage yet. Work through these steps
          to see revenue, cost, and margin land on this page.
          {!anyLoading && (
            <span className="ml-1 font-medium text-text-primary">
              {doneCount} of {steps.length} complete.
            </span>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="space-y-3">
          {steps.map((step) => (
            <StepRow key={step.key} step={step} />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function StepRow({ step }: { step: Step }) {
  return (
    <li className="flex items-start gap-3" data-state={step.state}>
      {step.state === "loading" ? (
        <Skeleton className="mt-0.5 h-4 w-4 rounded-full" />
      ) : step.state === "done" ? (
        <CheckCircle2
          className="mt-0.5 h-4 w-4 shrink-0 text-text-primary"
          strokeWidth={1.5}
          aria-label="Done"
        />
      ) : (
        <Circle
          className="mt-0.5 h-4 w-4 shrink-0 text-border-strong"
          strokeWidth={1.5}
          aria-hidden="true"
        />
      )}
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-medium text-text-primary">{step.title}</p>
        <p className="text-[12px] text-text-muted">
          {step.state === "unknown" && step.errorText
            ? `Couldn't check this step — ${step.errorText}`
            : step.description}
        </p>
        {step.state === "unknown" && step.retry && (
          <button
            type="button"
            onClick={step.retry}
            className="mt-0.5 text-[11px] font-medium text-text-secondary underline-offset-2 hover:underline"
          >
            Try again
          </button>
        )}
      </div>
      {step.state !== "done" && step.state !== "loading" && (
        <Link
          to={step.to}
          className="inline-flex shrink-0 items-center gap-1 text-[12px] font-medium text-text-secondary transition-colors hover:text-text-primary"
        >
          {step.linkLabel}
          <ArrowRight className="h-3 w-3" strokeWidth={1.5} />
        </Link>
      )}
    </li>
  );
}
