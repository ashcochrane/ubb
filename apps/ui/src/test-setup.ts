import "@testing-library/jest-dom/vitest";
import { configure } from "@testing-library/react";
import { vi } from "vitest";

// waitFor/findBy default to a 1s timeout — under full-suite parallelism the
// mock provider's simulated latency plus slow jsdom renders (Windows CI)
// exceed it and produce load-order flakes. Tests pass alone; give the async
// utils real headroom instead.
configure({ asyncUtilTimeout: 8_000 });

// Recharts' ResponsiveContainer relies on ResizeObserver and
// getBoundingClientRect() to measure its parent. jsdom provides neither
// out of the box, so stub both globally for any chart-rendering test.
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal("ResizeObserver", ResizeObserverMock);

Element.prototype.getBoundingClientRect = function () {
  return {
    x: 0,
    y: 0,
    top: 0,
    left: 0,
    right: 200,
    bottom: 32,
    width: 200,
    height: 32,
    toJSON: () => ({}),
  } as DOMRect;
};
