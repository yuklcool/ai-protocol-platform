// Admin hub IA — five task-shaped areas (v6.16.0 Phase 3).
//
// The previous layout had one card per API surface, which mirrored the
// backend's module structure rather than anything an operator asks. These tests
// pin the two properties that matter: the areas are named for questions, and a
// non-admin never sees a platform-only door that would 403 them.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { translate } from "@/lib/i18n";

import AdminHub from "../page";

const auth: { user: unknown; loading: boolean } = {
  user: { email: "u@x.com" },
  loading: false,
};
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth }));

const fetchMock = vi.fn();
vi.mock("@/lib/apiClient", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchMock(...args),
}));

const recheck = vi.fn(async () => {});
const scope: {
  state: string;
  isAdmin: boolean;
  isPlatform: boolean;
  recheck: () => Promise<void>;
} = {
  state: "platform",
  isAdmin: true,
  isPlatform: true,
  recheck,
};
vi.mock("@/hooks/useAdminScope", () => ({ useAdminScope: () => scope }));

vi.mock("@/components/chat/SignInRequired", () => ({
  SignInRequired: () => <div>sign in required</div>,
}));

function asPlatform() {
  Object.assign(scope, {
    state: "platform",
    isAdmin: true,
    isPlatform: true,
  });
}

describe("AdminHub IA", () => {
  afterEach(() => { vi.unstubAllEnvs(); });

  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv("NEXT_PUBLIC_ENABLE_SKILL_STUDIO", "false");
    fetchMock.mockImplementation(async (url: string) => ({
      ok: true,
      json: async () => url.endsWith("/models") ? [] : {},
    }));
    auth.user = { email: "u@x.com" };
    auth.loading = false;
    asPlatform();
  });

  it("renders five task-shaped areas for a platform admin", async () => {
    render(<AdminHub />);
    await waitFor(() => expect(screen.queryAllByText("Loading live configuration…")).toHaveLength(0));
    for (const title of [
      "Root Agent",
      "People & access",
      "Skills & MCP",
      "Activity & audit",
      "Platform",
    ]) {
      expect(screen.getByText(title)).toBeTruthy();
    }
  });

  it("names the question each area answers, not the API it wraps", async () => {
    render(<AdminHub />);
    await waitFor(() => expect(screen.queryAllByText("Loading live configuration…")).toHaveLength(0));
    expect(
      screen.getByText(/who is here, and what may they use/i),
    ).toBeTruthy();
  });

  it("keeps current admin routes reachable", async () => {
    render(<AdminHub />);
    await waitFor(() => expect(screen.queryAllByText("Loading live configuration…")).toHaveLength(0));
    const hrefs = Array.from(document.querySelectorAll("a")).map((a) =>
      a.getAttribute("href"),
    );
    for (const route of [

      "/admin/users",

      "/admin/analytics",
      "/admin/audit",
      "/admin/settings",
      "/admin/model-providers",
      "/chat/root-agent",
      "/agent",
      "/skills",
      "/admin/mcp-servers",
    ]) {
      expect(hrefs).toContain(route);
    }
  });

  it("shows a distinct error state rather than implying no access", async () => {
    Object.assign(scope, {
      state: "error",
      isAdmin: false,
      isPlatform: false,
    });
    render(<AdminHub />);
    await waitFor(() =>
      expect(
        screen.getByText(translate("en", "admin.accessCheckFailed")),
      ).toBeTruthy(),
    );
    expect(screen.queryByText("Admins only")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /re-check my access/i }));
    expect(recheck).toHaveBeenCalledOnce();
  });

  it("shows 'Admins only' for a genuine non-admin", () => {
    Object.assign(scope, {
      state: "none",
      isAdmin: false,
      isPlatform: false,
    });
    render(<AdminHub />);
    expect(screen.getByText("Admins only")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByText("Agent readiness checklist")).toBeNull();
  });

  it.each(["false", "", "true"])("gates Studio creation with the exact switch value %s", async (enabled) => {
    vi.stubEnv("NEXT_PUBLIC_ENABLE_SKILL_STUDIO", enabled);
    render(<AdminHub />);
    await waitFor(() => expect(screen.queryAllByText("Loading live configuration…")).toHaveLength(0));
    const studio = document.querySelector('a[href="/skills/studio/new"]');
    if (enabled === "true") expect(studio).not.toBeNull();
    else expect(studio).toBeNull();
    expect(document.querySelector('a[href="/skills"]')).not.toBeNull();
  });

  it("does not request readiness while access is loading", () => {
    scope.state = "loading";
    render(<AdminHub />);
    expect(screen.queryByText("Agent readiness checklist")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not request readiness while authentication is loading", () => {
    auth.loading = true;
    render(<AdminHub />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not request readiness for a signed-out user", () => {
    auth.user = null;
    render(<AdminHub />);
    expect(screen.getByText("sign in required")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("offers a token re-check after a just-granted role", () => {
    Object.assign(scope, {
      state: "none",
      isAdmin: false,
      isPlatform: false,
    });
    render(<AdminHub />);
    expect(screen.getByText(/granted access just now/i)).toBeTruthy();
    fireEvent.click(
      screen.getByRole("button", { name: /re-check my access/i }),
    );
    expect(recheck).toHaveBeenCalled();
  });
});
