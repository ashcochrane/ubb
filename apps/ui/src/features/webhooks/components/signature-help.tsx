import { CodeBlock } from "@/components/shared/code-block";

const ENVELOPE_EXAMPLE = `{
  "event_type": "wallet.balance_low",
  "event_id": "9c1f4b82-6a3d-4e7f-b510-27d8e9a6c143",
  "created_at": "2026-07-24T12:00:00Z",
  "data": { ... }
}`;

const VERIFY_PSEUDOCODE = `# On each incoming request:
header = request.headers["X-UBB-Signature-V2"]   # "t=1753358400,v1=abc...,v1=def..."
ts     = value after "t="
sigs   = every value after "v1="                 # >1 during a secret rotation

expected = hmac_sha256(secret, ts + "." + raw_body_bytes)
valid    = any(constant_time_equals(expected, s) for s in sigs)
fresh    = abs(now_unix() - ts) < 300            # reject stale timestamps

accept only if valid and fresh`;

/** Static receiver-side documentation for the outbound delivery contract. */
export function SignatureHelp() {
  return (
    <div className="max-w-2xl space-y-4 text-sm">
      <p className="text-muted-foreground">
        Every delivery is an HTTPS POST signed with this endpoint's secret. Verify the
        signature before trusting the payload.
      </p>

      <div className="space-y-1.5">
        <h3 className="font-medium">Headers</h3>
        <ul className="space-y-1.5 text-muted-foreground">
          <li>
            <span className="font-mono text-xs text-foreground">X-UBB-Signature-V2</span> —{" "}
            <span className="font-mono text-xs">
              t=&lt;unix-seconds&gt;,v1=&lt;hex&gt;
            </span>
            : HMAC-SHA256 over{" "}
            <span className="font-mono text-xs">{"{t}.{body}"}</span> with your secret.
            During a secret-rotation window the header carries multiple{" "}
            <span className="font-mono text-xs">v1=</span> candidates — accept if ANY
            matches.
          </li>
          <li>
            <span className="font-mono text-xs text-foreground">X-UBB-Signature</span> —
            legacy HMAC-SHA256 over the raw body only. Deprecated; kept while old
            verifiers migrate to V2.
          </li>
          <li>
            <span className="font-mono text-xs text-foreground">X-UBB-Event-Type</span> —
            the event type, duplicated from the body.
          </li>
        </ul>
      </div>

      <div className="space-y-1.5">
        <h3 className="font-medium">Envelope</h3>
        <CodeBlock value={ENVELOPE_EXAMPLE} />
        <p className="text-xs text-muted-foreground">
          Payloads are additive-only: new fields may appear over time, existing fields
          never change meaning. Ignore fields you don't recognize.
        </p>
      </div>

      <div className="space-y-1.5">
        <h3 className="font-medium">Verifying (pseudo-code)</h3>
        <CodeBlock value={VERIFY_PSEUDOCODE} />
      </div>
    </div>
  );
}
