import { TriangleAlert } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { CodeBlock } from "@/components/shared/code-block";

/**
 * Client-side echo of a secret the user just typed or generated, with the
 * hard warning. This is NOT a server reveal — the API never returns webhook
 * secrets; we can only show the value because it's still in this session.
 */
export function SecretReveal({
  secret,
  context,
}: {
  secret: string;
  context?: string;
}) {
  return (
    <div className="space-y-2">
      <CodeBlock value={secret} wrap />
      <Alert>
        <TriangleAlert aria-hidden="true" />
        <AlertTitle>Store this now. UBB never displays webhook secrets.</AlertTitle>
        <AlertDescription>
          {context ??
            "Save it in your secret manager before you continue — once you leave this dialog it can't be shown again."}
        </AlertDescription>
      </Alert>
    </div>
  );
}
