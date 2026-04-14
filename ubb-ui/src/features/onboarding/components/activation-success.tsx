// src/features/onboarding/components/activation-success.tsx
import { useEffect } from "react";
import { CheckCircle } from "lucide-react";
import { Link, useNavigate } from "@tanstack/react-router";
import type { OnboardingMode } from "../api/types";

interface ActivationSuccessProps {
  mode: OnboardingMode;
}

export function ActivationSuccess({ mode }: ActivationSuccessProps) {
  const navigate = useNavigate();

  useEffect(() => {
    const timer = setTimeout(() => {
      void navigate({ to: "/" });
    }, 1500);
    return () => clearTimeout(timer);
  }, [navigate]);

  const title = mode === "track"
    ? "You're all set"
    : mode === "revenue"
      ? "Stripe integration is live"
      : "Billing integration is live";

  const subtitle = mode === "track"
    ? "Create your first pricing card to start tracking costs."
    : "Revenue data is syncing now. Historical backfill will complete within the hour.";

  return (
    <div className="space-y-5 text-center">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30">
        <CheckCircle className="h-6 w-6 text-green-600" />
      </div>
      <h2 className="text-[16px] font-semibold">{title}</h2>
      <p className="text-[12px] text-muted-foreground">{subtitle}</p>

      <div className="rounded-xl border border-border px-4 py-3.5 text-left">
        <div className="mb-2 text-[12px] font-medium">What happens next</div>
        <ol className="space-y-2">
          <li className="flex items-start gap-2.5">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-50 text-muted font-semibold text-blue-700 dark:bg-blue-900/20 dark:text-blue-400">1</span>
            <span className="text-label text-muted-foreground">Create your first pricing card — pick a template, verify prices, activate.</span>
          </li>
          <li className="flex items-start gap-2.5">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-50 text-muted font-semibold text-blue-700 dark:bg-blue-900/20 dark:text-blue-400">2</span>
            <span className="text-label text-muted-foreground">Paste the SDK code into your app wherever you make API calls.</span>
          </li>
          <li className="flex items-start gap-2.5">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-50 text-muted font-semibold text-blue-700 dark:bg-blue-900/20 dark:text-blue-400">3</span>
            <span className="text-label text-muted-foreground">Deploy — your dashboard shows live data within minutes.</span>
          </li>
        </ol>
      </div>

      <div className="flex justify-center gap-3">
        <Link
          to="/"
          className="rounded-lg border border-border px-4 py-2 text-[12px] text-muted-foreground hover:bg-accent"
        >
          Go to dashboard
        </Link>
        <Link
          to="/pricing-cards/new"
          className="rounded-lg bg-foreground px-4 py-2 text-[12px] font-medium text-background hover:opacity-90"
        >
          Create my first pricing card
        </Link>
      </div>
    </div>
  );
}
