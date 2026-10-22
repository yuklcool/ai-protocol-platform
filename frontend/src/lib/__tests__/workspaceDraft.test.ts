import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  consumeWorkspaceDraft,
  stageWorkspaceDraft,
  WORKSPACE_DRAFT_LIMIT,
} from "../workspaceDraft";

beforeEach(() => {
  window.sessionStorage.clear();
  vi.spyOn(Date, "now").mockReturnValue(1_000_000);
});

afterEach(() => {
  vi.restoreAllMocks();
  window.sessionStorage.clear();
});

describe("Issue #141: workspace draft handoff", () => {
  it("keeps an owned draft for one read, without an API request", () => {
    expect(stageWorkspaceDraft("  分析合同风险  ", "u1")).toBe(true);
    expect(consumeWorkspaceDraft("u1")).toBe("分析合同风险");
    expect(consumeWorkspaceDraft("u1")).toBeNull();
  });

  it("does not leak a draft to a different account", () => {
    expect(stageWorkspaceDraft("secret", "u1")).toBe(true);
    expect(consumeWorkspaceDraft("u2")).toBeNull();
    expect(consumeWorkspaceDraft("u1")).toBeNull();
  });

  it("refuses empty and oversized values", () => {
    expect(stageWorkspaceDraft("   ", "u1")).toBe(false);
    expect(stageWorkspaceDraft("x", "")).toBe(false);
    expect(stageWorkspaceDraft("x".repeat(WORKSPACE_DRAFT_LIMIT + 1), "u1")).toBe(false);
    expect(consumeWorkspaceDraft("u1")).toBeNull();
  });

  it("expires stale drafts and clears them", () => {
    expect(stageWorkspaceDraft("stale", "u1")).toBe(true);
    vi.mocked(Date.now).mockReturnValue(1_000_000 + 5 * 60 * 1000 + 1);
    expect(consumeWorkspaceDraft("u1")).toBeNull();
    expect(consumeWorkspaceDraft("u1")).toBeNull();
  });

  it("rejects a draft timestamp from the future", () => {
    expect(stageWorkspaceDraft("future", "u1")).toBe(true);
    vi.mocked(Date.now).mockReturnValue(999_999);
    expect(consumeWorkspaceDraft("u1")).toBeNull();
  });

  it("ignores corrupt persisted data", () => {
    window.sessionStorage.setItem("ai-protocol-platform:workspace-draft:v1", "{bad json");
    expect(consumeWorkspaceDraft("u1")).toBeNull();
  });
});
