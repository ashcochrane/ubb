import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
    // Several cases start a Python interpreter, which on Windows takes a
    // second or more by itself.
    testTimeout: 60_000,
    hookTimeout: 60_000,
  },
});
