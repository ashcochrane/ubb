import { describe, expect, it } from "vitest";

import { sandboxResetCurl } from "./sandbox-reset";

describe("the sandbox reset command", () => {
  it("builds a sandbox-key reset curl with keep_config", () => {
    const curl = sandboxResetCurl("https://api.example.com");
    expect(curl).toContain("https://api.example.com/api/v1/sandbox/reset");
    // The key's variable, never a key or a key-shaped placeholder (#579).
    expect(curl).toContain('-H "Authorization: Bearer $UBB_API_KEY"');
    expect(curl).toContain('"keep_config": true');
  });
});
