// API basics: the base URL, the bearer auth shape (placeholder — never a
// real key), and one-liners for pagination + problem+json, with links into
// the webhook and audit surfaces.

import { Link } from "@tanstack/react-router";

import { CodeBlock } from "@/components/shared/code-block";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import { AUTH_HEADER_EXAMPLE, apiOrigin } from "../lib/test-event";

export function ApiBasicsCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>API basics</CardTitle>
        <CardDescription>
          Everything speaks JSON over one versioned base URL.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <p className="text-[12px] font-medium text-text-primary">Base URL</p>
          <CodeBlock value={`${apiOrigin()}/api/v1`} />
        </div>
        <div className="space-y-1.5">
          <p className="text-[12px] font-medium text-text-primary">
            Authentication
          </p>
          <CodeBlock value={AUTH_HEADER_EXAMPLE} wrap />
          <p className="text-[12px] text-text-secondary">
            Send your API key as a bearer token. The value above is a
            placeholder — mint a real key under API keys.
          </p>
        </div>
        <div className="space-y-2 text-[12px] text-text-secondary">
          <p>
            <span className="font-medium text-text-primary">Pagination:</span>{" "}
            lists return{" "}
            <span className="font-mono">
              {"{ data, has_more, next_cursor }"}
            </span>{" "}
            — pass <span className="font-mono">next_cursor</span> back as{" "}
            <span className="font-mono">cursor</span> to page (limit up to 100,
            newest first, no total counts).
          </p>
          <p>
            <span className="font-medium text-text-primary">Errors:</span> any
            non-2xx response is an RFC 9457{" "}
            <span className="font-mono">problem+json</span> body with a stable{" "}
            <span className="font-mono">code</span> — branch on the code, not
            the wording.
          </p>
        </div>
        <p className="text-[12px] text-text-secondary">
          See also{" "}
          <Link to="/webhooks" className="underline hover:text-text-primary">
            Webhooks
          </Link>{" "}
          for outbound events and{" "}
          <Link
            to="/settings/audit"
            className="underline hover:text-text-primary"
          >
            the audit ledger
          </Link>{" "}
          for who changed what.
        </p>
      </CardContent>
    </Card>
  );
}
