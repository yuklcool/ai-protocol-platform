import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

import {
  useResizableWorkspaceRatio,
  readStoredRatio,
  RATIO_MIN,
  RATIO_MAX,
  RATIO_DEFAULT,
  DEFAULT_RATIOS,
} from "../useResizableWorkspaceRatio";

beforeEach(() => {
  window.sessionStorage.clear();
});

describe("useResizableWorkspaceRatio", () => {
  it("initialises with the per-skill default when no stored value", () => {
    const { result } = renderHook(() => useResizableWorkspaceRatio("one-doc-compare"));
    expect(result.current.ratio).toBe(DEFAULT_RATIOS["one-doc-compare"]);
  });

  it("falls back to RATIO_DEFAULT for unlisted skillIds (slim chat-led default)", () => {
    const { result } = renderHook(() => useResizableWorkspaceRatio("some-unknown-skill"));
    expect(result.current.ratio).toBe(RATIO_DEFAULT);
  });

  it("restores a previously stored ratio (per-skill)", () => {
    window.sessionStorage.setItem("aitana.workspaceRatio:skill-a", "0.7");
    const { result } = renderHook(() => useResizableWorkspaceRatio("skill-a"));
    expect(result.current.ratio).toBe(0.7);
  });

  it("setRatio clamps to [RATIO_MIN, RATIO_MAX] and persists", () => {
    const { result } = renderHook(() => useResizableWorkspaceRatio("skill-b"));
    act(() => result.current.setRatio(2.0));
    expect(result.current.ratio).toBe(RATIO_MAX);
    act(() => result.current.setRatio(0.0));
    expect(result.current.ratio).toBe(RATIO_MIN);
    expect(window.sessionStorage.getItem("aitana.workspaceRatio:skill-b")).toBe(String(RATIO_MIN));
  });

  it("readStoredRatio returns null for malformed values", () => {
    window.sessionStorage.setItem("aitana.workspaceRatio:x", "not-a-number");
    expect(readStoredRatio("x")).toBeNull();
  });

  it("readStoredRatio returns null for out-of-range values", () => {
    window.sessionStorage.setItem("aitana.workspaceRatio:x", "1.5");
    expect(readStoredRatio("x")).toBeNull();
    window.sessionStorage.setItem("aitana.workspaceRatio:x", "0.1");
    expect(readStoredRatio("x")).toBeNull();
  });

  it("stored value on one skill does not leak into another", () => {
    window.sessionStorage.setItem("aitana.workspaceRatio:skill-c", "0.9");
    const { result } = renderHook(() => useResizableWorkspaceRatio("skill-d"));
    expect(result.current.ratio).toBe(RATIO_DEFAULT);
  });
});

