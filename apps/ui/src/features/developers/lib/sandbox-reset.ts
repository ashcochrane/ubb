// The sandbox reset panel's copyable command. Moved here from the test-event
// console's helpers when #581 deleted that console: the sandbox panel was its
// one other reader.

import { ENVIRONMENT } from "ubb-codegen";

/**
 * Copyable sandbox-reset command. The endpoint only accepts a sandbox
 * (ubb_test_) key — the console's live credentials get 403 — so this runs
 * from the user's terminal, never from a console button.
 *
 * ⚠ IT NAMES THE KEY'S VARIABLE, NEVER A KEY (#579). This used to carry a
 * key-shaped placeholder, a second convention beside the API-basics card's
 * own; a developer pastes a real key into a placeholder's shape and the
 * command lands in a shell history. The variable is the one every generated
 * file reads (`ubb-codegen`'s catalogue), so the shell that runs the
 * integration runs this unchanged.
 */
export function sandboxResetCurl(origin: string): string {
  return [
    `curl -X POST ${origin}/api/v1/sandbox/reset \\`,
    `  -H "Authorization: Bearer $${ENVIRONMENT.apiKey}" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '{"keep_config": true}'`,
  ].join("\n");
}
