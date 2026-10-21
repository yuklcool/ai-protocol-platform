import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UserMenu } from "../UserMenu";
import { fetchWithAuth } from "@/lib/apiClient";

// Mutable auth stub — the mocked useAuth reads it at call time, so tests can
// flip user state between cases.
const auth = {
  user: null as {
    uid?: string;
    displayName?: string;
    email?: string;
    photoURL?: string | null;
  } | null,
  loading: false,
  signIn: vi.fn(),
  signOut: vi.fn(),
  getIdToken: vi.fn(),
  signInWithRedirect: vi.fn(),
  signInWithPassword: vi.fn(),
};
const authMode = { localJwt: true, oidc: false };

vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("@/lib/apiClient", () => ({ fetchWithAuth: vi.fn() }));
vi.mock("@/lib/localJwtAuth", () => ({
  isLocalJwtAuthMode: () => authMode.localJwt,
}));
vi.mock("@/lib/oidcAuth", () => ({ isOidcAuthMode: () => authMode.oidc }));

describe("UserMenu", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    auth.user = null;
    auth.loading = false;
    authMode.localJwt = true;
    authMode.oidc = false;
    // Default: the admin probe denies (non-admin). Individual tests override.
    vi.mocked(fetchWithAuth).mockResolvedValue({
      ok: false,
      status: 403,
    } as Response);
  });

  it("未登录时复用共享密码登录弹窗，而非直接调用 signIn", async () => {
    render(<UserMenu />);
    fireEvent.click(screen.getByTestId("sign-in-button"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "owner@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "example-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(auth.signInWithPassword).toHaveBeenCalledWith(
      "owner@example.com", "example-password",
    ));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(auth.signIn).not.toHaveBeenCalled();
    expect(auth.signInWithRedirect).not.toHaveBeenCalled();
    expect(fetchWithAuth).not.toHaveBeenCalled();
  });

  it("OIDC 模式通过共享入口重定向，不直接调用 signIn", async () => {
    authMode.localJwt = false;
    authMode.oidc = true;
    render(<UserMenu />);
    fireEvent.click(screen.getByTestId("sign-in-button"));
    await waitFor(() => expect(auth.signInWithRedirect).toHaveBeenCalledOnce());
    expect(auth.signIn).not.toHaveBeenCalled();
  });

  it("Google 模式保留共享登录行为", async () => {
    authMode.localJwt = false;
    render(<UserMenu />);
    fireEvent.click(screen.getByTestId("sign-in-button"));
    await waitFor(() => expect(auth.signIn).toHaveBeenCalledOnce());
  });

  it("认证加载时不显示登录入口或账号菜单", () => {
    auth.loading = true;
    render(<UserMenu />);
    expect(screen.queryByTestId("sign-in-button")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Account menu")).not.toBeInTheDocument();
  });

  it("shows the avatar menu with name/email and Sign out when logged in", () => {
    auth.user = {
      displayName: "Mark",
      uid: "test-user", email: "owner@yourcompany.com",
      photoURL: null,
    };
    render(<UserMenu />);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(screen.queryByTestId("sign-in-button")).not.toBeInTheDocument();
    expect(fetchWithAuth).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText("Account menu"));
    expect(screen.getByRole("menuitem", { name: "Personal Skills and information" })).toHaveAttribute("href", "/settings/personal");
    expect(screen.getByText("Mark")).toBeTruthy();
    expect(screen.getByText("owner@yourcompany.com")).toBeTruthy();
    fireEvent.click(screen.getByText("Sign out"));
    expect(auth.signOut).toHaveBeenCalledOnce();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("账号菜单支持 Escape、外部点击及个人设置入口关闭", () => {
    auth.user = { uid: "test-user", displayName: "Mark" };
    render(<UserMenu />);
    const trigger = screen.getByLabelText("Account menu");
    fireEvent.click(trigger);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(trigger);
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    fireEvent.click(trigger);
    const personalLink = screen.getByRole("menuitem", { name: "Personal Skills and information" });
    personalLink.addEventListener("click", (event) => event.preventDefault(), { once: true });
    fireEvent.click(personalLink);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("有头像时显示用户头像", () => {
    auth.user = { uid: "test-user", displayName: "Mark", photoURL: "/avatar.png" };
    render(<UserMenu />);
    expect(screen.getByRole("img", { name: "Mark" })).toHaveAttribute("src", "/avatar.png");
  });

  it("falls back to an initial chip when there is no photoURL", () => {
    auth.user = { displayName: "Zara", uid: "test-user", email: "z@x.com", photoURL: null };
    render(<UserMenu />);
    // The trigger shows the uppercase initial.
    expect(screen.getByLabelText("Account menu").textContent).toBe("Z");
  });

  it("reveals an Admin link for a platform admin", async () => {
    auth.user = {
      displayName: "Mark",
      uid: "test-user", email: "owner@yourcompany.com",
      photoURL: null,
    };
    vi.mocked(fetchWithAuth).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ scope: "platform" }),
    } as unknown as Response);
    render(<UserMenu />);
    fireEvent.click(screen.getByLabelText("Account menu"));
    const adminLink = await screen.findByText("Admin");
    expect(adminLink.getAttribute("href")).toBe("/admin");
    // v6.16.0: asks the ROLE endpoint, not a platform-only data endpoint.
    expect(fetchWithAuth).toHaveBeenCalledWith("/api/proxy/api/admin/whoami");
  });

  it("hides the Admin link for a non-admin (scope 'none')", async () => {
    auth.user = { displayName: "Zed", uid: "test-user", email: "zed@x.com", photoURL: null };
    vi.mocked(fetchWithAuth).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ scope: "none" }),
    } as unknown as Response);
    render(<UserMenu />);
    fireEvent.click(screen.getByLabelText("Account menu"));
    await waitFor(() => expect(fetchWithAuth).toHaveBeenCalledWith("/api/proxy/api/admin/whoami"));
    expect(screen.queryByText("Admin")).toBeNull();
  });
});
