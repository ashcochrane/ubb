import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { Check, X } from "lucide-react";
import { Section } from "@/components/shared/data-states";
import { StatusBadge } from "@/components/shared/status-badge";
import { humanizeLabel } from "@/lib/format";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { cn } from "@/lib/utils";

type SetupLink = "/settings" | "/webhooks" | "/pricing" | "/customers";

function ChecklistItem({
  done,
  label,
  detail,
  to,
  cta,
}: {
  done: boolean;
  label: string;
  detail: ReactNode;
  to: SetupLink;
  cta: string;
}) {
  return (
    <li className="flex items-start gap-3 py-2.5">
      <span
        className={cn(
          "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full",
          done ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
        )}
        aria-hidden
      >
        {done ? <Check className="size-3.5" /> : <X className="size-3.5" />}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium">{label}</div>
        <div className="mt-0.5 text-xs text-muted-foreground">{detail}</div>
      </div>
      {!done && (
        <Link
          to={to}
          className="shrink-0 text-xs font-medium text-foreground underline-offset-2 hover:underline"
        >
          {cta}
        </Link>
      )}
    </li>
  );
}

/** Always-shown account readiness checklist, driven purely by tenant config. */
export function SetupChecklistSection() {
  const { stripeConnected, products, billingMode, tenantName } = useAuth();
  const hasProducts = products.length > 0;
  const allDone = stripeConnected && hasProducts;

  return (
    <Section
      title="Get set up"
      description={
        allDone
          ? `${tenantName ?? "Your account"} is ready to go.`
          : "A few steps left before your account is fully operational."
      }
    >
      <ul className="divide-y divide-border">
        <ChecklistItem
          done={stripeConnected}
          label="Connect Stripe"
          detail={
            stripeConnected
              ? "A connected account is linked for payment collection."
              : "Link a Stripe connected account to collect payments."
          }
          to="/settings"
          cta="Connect"
        />
        <ChecklistItem
          done={hasProducts}
          label="Enable products"
          detail={
            hasProducts ? (
              <span className="flex flex-wrap gap-1.5">
                {products.map((p) => (
                  <StatusBadge key={p} value={p} tone="muted" />
                ))}
              </span>
            ) : (
              "No products enabled yet. Turn on metering, billing, subscriptions, or referrals."
            )
          }
          to="/settings"
          cta="Enable"
        />
        <li className="flex items-start gap-3 py-2.5">
          <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground" aria-hidden>
            <Check className="size-3.5" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium">Billing mode</div>
            <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
              {billingMode ? (
                <StatusBadge value={humanizeLabel(billingMode)} tone="neutral" />
              ) : (
                <span>Not configured</span>
              )}
            </div>
          </div>
          <Link
            to="/settings"
            className="shrink-0 text-xs font-medium text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
          >
            Manage
          </Link>
        </li>
      </ul>
      {!allDone && (
        <p className="mt-3 border-t border-border pt-3 text-xs text-muted-foreground">
          Next, review your{" "}
          <Link to="/pricing" className="text-foreground underline underline-offset-2">
            pricing
          </Link>
          , map{" "}
          <Link to="/customers" className="text-foreground underline underline-offset-2">
            customers
          </Link>
          , and set up{" "}
          <Link to="/webhooks" className="text-foreground underline underline-offset-2">
            webhooks
          </Link>
          .
        </p>
      )}
    </Section>
  );
}
