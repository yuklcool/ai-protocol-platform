import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  LOCAL_JWT_SESSION_STORAGE_KEY,
  getLocalJwtToken,
  isLocalJwtAuthMode,
  loginWithLocalJwt,
  readLocalJwtSession,
  validateLocalJwtSession,
  writeLocalJwtSession,
} from "@/lib/localJwtAuth";

const USER = {
  uid: "user-1",
  email: "admin@example.com",
  domain: "example.com",
  groupTags: ["aitana-admin"],
  authMode: "local-jwt",
};

describe("local JWT browser session", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
  });

  it("detects the local-jwt deployment mode", () => {
    vi.stubEnv("NEXT_PUBLIC_AUTH_MODE", "local-jwt");
    expect(isLocalJwtAuthMode()).toBe(true);
    vi.stubEnv("NEXT_PUBLIC_AUTH_MODE", "firebase");
    expect(isLocalJwtAuthMode()).toBe(false);
  });

  it("stores a successful login and exposes the active bearer token", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            access_token: "signed-token",
            token_type: "bearer",
            expires_in: 3600,
            user: USER,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    const session = await loginWithLocalJwt("admin@example.com", "strong-password-value");
    expect(session.user.email).toBe("admin@example.com");
    expect(getLocalJwtToken()).toBe("signed-token");
    expect(window.sessionStorage.getItem(LOCAL_JWT_SESSION_STORAGE_KEY)).toContain("signed-token");
  });

  it("drops expired sessions instead of sending a stale bearer token", () => {
    window.sessionStorage.setItem(
      LOCAL_JWT_SESSION_STORAGE_KEY,
      JSON.stringify({ token: "expired", expiresAt: Date.now() - 1000, user: USER }),
    );
    expect(readLocalJwtSession()).toBeNull();
    expect(window.sessionStorage.getItem(LOCAL_JWT_SESSION_STORAGE_KEY)).toBeNull();
  });

  it("re-resolves user metadata from whoami", async () => {
    const session = {
      token: "signed-token",
      expiresAt: Date.now() + 60_000,
      user: USER,
    };
    writeLocalJwtSession(session);

    const updated = { ...USER, groupTags: ["tenant-admin:example.com"] };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify(updated), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    const refreshed = await validateLocalJwtSession(session);
    expect(refreshed?.user.groupTags).toEqual(["tenant-admin:example.com"]);
    expect(readLocalJwtSession()?.user.groupTags).toEqual(["tenant-admin:example.com"]);
  });

  it("clears the browser session when whoami rejects the token", async () => {
    const session = {
      token: "signed-token",
      expiresAt: Date.now() + 60_000,
      user: USER,
    };
    writeLocalJwtSession(session);
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 401 })));

    expect(await validateLocalJwtSession(session)).toBeNull();
    expect(readLocalJwtSession()).toBeNull();
  });
});
