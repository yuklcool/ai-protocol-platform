import { renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/apiClient", () => ({
  fetchWithAuth: vi.fn(),
}));

import { fetchWithAuth } from "@/lib/apiClient";
import { useUserSkills } from "@/hooks/useUserSkills";
import type { Skill } from "@/types/skill";

const mockFetch = fetchWithAuth as ReturnType<typeof vi.fn>;

function makeResponse(body: unknown, ok = true) {
  return Promise.resolve({
    ok,
    json: () => Promise.resolve(body),
  } as Response);
}

const SKILL: Skill = {
  name: "research",
  description: "",
  instructions: "",
  skillMetadata: {
    author: "test",
    version: "1.0",
    model: "gemini-2.5-flash",
    tools: [],
    toolConfigs: {},
    subSkills: [],
  },
  references: {},
  assets: {},
  skillId: "skill-1",
  displayName: "Research",
  avatar: "",
  ownerEmail: "u@example.com",
  ownerId: "uid-1",
  accessControl: { type: "private" },
  protocols: {
    mcp: { enabled: false },
    a2a: { enabled: false },
    agui: { enabled: true },
    a2ui: { enabled: false },
    mcpApps: { enabled: false },
  },
  initialMessage: "",
  tags: [],
  featured: false,
  usageCount: 0,
  createdAt: 0,
  updatedAt: 0,
};

beforeEach(() => {
  mockFetch.mockReset();
});

function ownSkill(overrides: Partial<Skill> = {}): Skill {
  return { ...SKILL, ownerId: "uid-1", skillId: "own-1", name: "own", ...overrides };
}

function platformSkill(overrides: Partial<Skill> = {}): Skill {
  return {
    ...SKILL,
    ownerId: "aitana-platform",
    skillId: "plat-1",
    name: "general-assistant",
    accessControl: { type: "public" },
    ...overrides,
  };
}

function makeRouter(skills: Skill[]) {
  return (input: string) => {
    if (input === "/api/proxy/api/skills") return makeResponse(skills);
    return makeResponse([], false);
  };
}

describe("useUserSkills", () => {
  it("returns empty list and does not fetch when uid is null", () => {
    const { result } = renderHook(() => useUserSkills(null));
    expect(result.current.skills).toEqual([]);
    expect(result.current.isLoading).toBe(false);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("fetches the backend-computed effective skill set", async () => {
    const own = [ownSkill({ skillId: "own-1" })];
    const platform = [
      platformSkill({ skillId: "plat-1", name: "general-assistant" }),
      platformSkill({ skillId: "plat-2", name: "code-assistant" }),
    ];
    mockFetch.mockImplementation(makeRouter([...own, ...platform]));

    const { result } = renderHook(() => useUserSkills("uid-1"));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/proxy/api/skills",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    // Own skills come first, platform skills last.
    expect(result.current.skills.map((s) => s.skillId)).toEqual([
      "own-1",
      "plat-1",
      "plat-2",
    ]);
  });

  it("merges platform skills even when the user has none of their own", async () => {
    const platform = [platformSkill({ skillId: "plat-1" })];
    mockFetch.mockImplementation(makeRouter(platform));

    const { result } = renderHook(() => useUserSkills("uid-1"));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.skills.map((s) => s.skillId)).toEqual(["plat-1"]);
  });

  it("preserves shared domain/tagged skills returned by the backend", async () => {
    const shared = ownSkill({ skillId: "shared", name: "shared-skill", ownerId: "other-user" });
    mockFetch.mockImplementation(makeRouter([shared]));

    const { result } = renderHook(() => useUserSkills("uid-1"));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.skills.map((s) => s.skillId)).toEqual(["shared"]);
  });

  it("sets error and clears skills when either fetch fails", async () => {
    mockFetch.mockImplementation(() => makeResponse({}, false));

    const { result } = renderHook(() => useUserSkills("uid-1"));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.error).toBe("Could not load skills.");
    expect(result.current.skills).toEqual([]);
  });

  it("aborts in-flight request when uid changes", async () => {
    mockFetch.mockReturnValue(new Promise(() => {})); // never resolves
    const { rerender, unmount } = renderHook(({ uid }) => useUserSkills(uid), {
      initialProps: { uid: "uid-1" as string | null },
    });
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const firstSignal = (mockFetch.mock.calls[0][1] as { signal: AbortSignal }).signal;
    expect(firstSignal.aborted).toBe(false);

    rerender({ uid: "uid-2" });
    expect(firstSignal.aborted).toBe(true);
    expect(mockFetch).toHaveBeenCalledTimes(2);

    unmount();
  });
});
