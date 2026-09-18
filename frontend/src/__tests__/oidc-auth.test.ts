import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  OIDC_SESSION_STORAGE_KEY,
  completeOidcSignIn,
  getOidcToken,
  isOidcAuthMode,
  readOidcSession,
  validateOidcSession,
  writeOidcSession,
} from "@/lib/oidcAuth";

const USER = {
  uid: "oidc-user-1",
  email: "owner@example.com",
  domain: "example.com",
  tenantId: "tenant-a",
  groupTags: ["tenant-admin:tenant-a"],
  authMode: "oidc",
};

describe("OIDC browser session", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  it("detects OIDC deployment mode", () => {
    vi.stubEnv("NEXT_PUBLIC_AUTH_MODE", "oidc");
    expect(isOidcAuthMode()).toBe(true);
    vi.stubEnv("NEXT_PUBLIC_AUTH_MODE", "local-jwt");
    expect(isOidcAuthMode()).toBe(false);
  });

  it("stores the verified callback token and safe return path", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          access_token: "verified-id-token",
          token_type: "bearer",
          expires_in: 300,
          return_to: "/skills?tab=mine",
          user: USER,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await completeOidcSignIn("authorization-code", "opaque-state");

    expect(result.returnTo).toBe("/skills?tab=mine");
    expect(result.session.user.tenantId).toBe("tenant-a");
    expect(getOidcToken()).toBe("verified-id-token");
    expect(window.sessionStorage.getItem(OIDC_SESSION_STORAGE_KEY)).toContain(
      "verified-id-token",
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/proxy/api/auth/oidc/callback",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          code: "authorization-code",
          state: "opaque-state",
        }),
      }),
    );
  });

  it.each([
    "https://evil.example/steal",
    "//evil.example/steal",
    "/\\evil.example/steal",
  ])("never follows an unsafe return URL from the callback response: %s", async (returnTo) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            access_token: "verified-id-token",
            token_type: "bearer",
            expires_in: 300,
            return_to: returnTo,
            user: USER,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    const result = await completeOidcSignIn("authorization-code", "opaque-state");
    expect(result.returnTo).toBe("/");
  });

  it("drops expired OIDC sessions", () => {
    window.sessionStorage.setItem(
      OIDC_SESSION_STORAGE_KEY,
      JSON.stringify({
        token: "expired",
        expiresAt: Date.now() - 1000,
        user: USER,
      }),
    );

    expect(readOidcSession()).toBeNull();
    expect(window.sessionStorage.getItem(OIDC_SESSION_STORAGE_KEY)).toBeNull();
  });

  it("re-resolves authorization metadata through whoami", async () => {
    const session = {
      token: "verified-id-token",
      expiresAt: Date.now() + 60_000,
      user: USER,
    };
    writeOidcSession(session);

    const updated = { ...USER, groupTags: ["ops"] };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify(updated), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    const refreshed = await validateOidcSession(session);
    expect(refreshed?.user.groupTags).toEqual(["ops"]);
    expect(readOidcSession()?.user.groupTags).toEqual(["ops"]);
  });
});
