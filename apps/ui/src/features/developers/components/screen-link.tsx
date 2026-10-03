// A link to the console screen that owns something the Code Builder points at
// (#579, §11). Same tab, on purpose: the builder's selections live in its URL,
// so the browser's Back returns to exactly the builder that was left, and the
// Blueprint resolves again on arrival.

import { Link } from "@tanstack/react-router";

import { tenantDefinedLabel } from "@/lib/localisation";

import type { ConsoleScreen } from "../lib/blueprint";

const LINK = "text-[12px] underline underline-offset-2 hover:text-text-primary";

export function ScreenLink({ screen }: { screen: ConsoleScreen }) {
  switch (screen.to) {
    case "/tasks/kinds/$key":
      return (
        <Link to="/tasks/kinds/$key" params={{ key: screen.params.key }} className={LINK}>
          {`Open the kind of work ${tenantDefinedLabel(screen.params.key)}`}
        </Link>
      );
    case "/tasks":
      return (
        <Link to="/tasks" className={LINK}>
          Kinds of work and workspace defaults
        </Link>
      );
    case "/pricing":
      return (
        <Link to="/pricing" className={LINK}>
          Cost Rates
        </Link>
      );
    case "/webhooks":
      return (
        <Link to="/webhooks" className={LINK}>
          Webhooks
        </Link>
      );
  }
}
