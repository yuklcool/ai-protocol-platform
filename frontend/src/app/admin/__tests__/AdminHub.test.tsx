// Admin hub IA — five task-shaped areas (v6.16.0 Phase 3).
//
// The previous layout had one card per API surface, which mirrored the
// backend's module structure rather than anything an operator asks. These tests
// pin the two properties that matter: the areas are named for questions, and a
// non-admin never sees a platform-only door that would 403 them.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { translate } from "@/lib/i18n";

import AdminHub from "../page";

const auth: { user: unknown; loading: boolean } = {
  user: { email: "u@x.com" },
  loading: false,
};
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth }));

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
  beforeEach(() => {
    auth.user = { email: "u@x.com" };
    auth.loading = false;
    asPlatform();
  });

  it("renders five task-shaped areas for a platform admin", async () => {
    render(<AdminHub />);
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

  it("names the question each area answers, not the API it wraps", () => {
    render(<AdminHub />);
    expect(
      screen.getByText(/who is here, and what may they use/i),
    ).toBeTruthy();
  });

  it("keeps current admin routes reachable", () => {
    render(<AdminHub />);
    const hrefs = Array.from(document.querySelectorAll("a")).map((a) =>
      a.getAttribute("href"),
    );
    for (const route of [

      "/admin/users",

      "/admin/analytics",
      "/admin/audit",
      "/admin/settings",
      "/admin/model-providers",
      "/skills/studio/new",
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
  });

  it("shows 'Admins only' for a genuine non-admin", () => {
    Object.assign(scope, {
      state: "none",
      isAdmin: false,
      isPlatform: false,
    });
    render(<AdminHub />);
    expect(screen.getByText("Admins only")).toBeTruthy();
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
