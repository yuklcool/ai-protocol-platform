import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom doesn't implement ResizeObserver — provide a no-op stub so components
// that use it don't crash in tests. The actual scroll behaviour is a browser
// layout concern and is not meaningful to assert in unit tests.
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// Resource drawers use the browser's media query API; JSDOM has no layout.
window.matchMedia = (media) => ({
  media, matches: false, onchange: null,
  addListener() {}, removeListener() {},
  addEventListener() {}, removeEventListener() {},
  dispatchEvent: () => false,
});

// vitest.config singleFork=true under CI runs every test file in the same
// process; without an explicit cleanup, prior renders leak and
// getByTestId() finds multiple nodes. Local (non-CI) pool=forks masks
// this by giving each file its own jsdom. Register cleanup globally so
// both modes behave identically.
afterEach(() => {
  cleanup();
});
